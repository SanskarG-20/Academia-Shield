import { Request, Response } from 'express';
import mongoose from 'mongoose';
import Session from '../models/Session';
import Rule from '../models/Rule';
import Batch from '../models/Batch';
import { reconcileSessions } from '../services/sessionClock';
import Student from '../models/Student';
import { sendError, sendSuccess } from '../utils/apiResponse';
import { getIO } from '../services/socketService';
import { runAnomalyCheck } from '../services/anomalyService';
import { aggregateSessionData } from '../utils/sessionAnalytics';
import { generateSessionSummary } from '../utils/geminiSummary';

const VALID_STATUSES = ['Upcoming', 'Active', 'Completed', 'Cancelled'];

const canStudentAccessSession = (session: any, joinedBatchIds: string[]) => {
  if (!session.batchIds || session.batchIds.length === 0) {
    return false;
  }

  const joinedSet = new Set(joinedBatchIds);
  return session.batchIds.some((batchId: any) => joinedSet.has(batchId.toString()));
};

// @desc    Create Session
// @route   POST /api/sessions
export const createSession = async (req: Request | any, res: Response) => {
  try {
    const { title, course, type, startTime, endTime, ruleSetId, batchIds } = req.body;

    if (!title || !course || !type || !startTime || !endTime || !ruleSetId) {
      return sendError(res, 'title, course, type, startTime, endTime and ruleSetId are required', 400);
    }

    if (!Number.isFinite(Date.parse(startTime)) || !Number.isFinite(Date.parse(endTime)) || new Date(startTime) >= new Date(endTime)) {
      return sendError(res, 'startTime must be strictly before endTime', 400);
    }

    if (!Array.isArray(batchIds) || batchIds.length === 0 || !batchIds.every((id: unknown) => mongoose.isValidObjectId(id))) {
      return sendError(res, 'Select at least one valid batch', 400);
    }
    const ownedCount = await Batch.countDocuments({ _id: { $in: batchIds }, professorId: req.user.id });
    if (ownedCount !== new Set(batchIds.map(String)).size) return sendError(res, 'You do not own every selected batch', 403);
    if (!mongoose.isValidObjectId(ruleSetId) || !await Rule.exists({ _id: ruleSetId, professorId: req.user.id, mode: 'Blocklist' })) {
      return sendError(res, 'Select one of your blocklist rule sets', 403);
    }
    const session = await Session.create({
      title,
      course,
      type,
      startTime,
      endTime,
      ruleSetId,
      batchIds,
      professorId: req.user.id,
    });

    return sendSuccess(res, session, 'Session created successfully', 201);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to create session', 500);
  }
};

// @desc    Get All Sessions (with role filtering)
// @route   GET /api/sessions
export const getSessions = async (req: Request | any, res: Response) => {
  try {
    await reconcileSessions();
    if (req.user.role === 'professor') {
      const sessions = await Session.find({ professorId: req.user.id })
        .sort({ startTime: -1 });
      return sendSuccess(res, sessions, 'Sessions fetched successfully');
    }

    if (req.user.role === 'student') {
      const student = await Student.findById(req.user.id).select('joinedBatches');
      if (!student) {
        return sendError(res, 'Student not found', 404);
      }

      const joinedBatchIds = (student.joinedBatches || []).map((batchId) => batchId.toString());

      const sessions = await Session.find({ batchIds: { $in: joinedBatchIds } }).sort({ startTime: 1 });

      return sendSuccess(res, sessions, 'Sessions fetched successfully');
    }

    return sendError(res, 'Unsupported role for sessions', 403);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch sessions', 500);
  }
};

// @desc    Update Session Status
// @route   PATCH /api/sessions/:id/status
export const updateSessionStatus = async (req: Request | any, res: Response) => {
  try {
    const { status } = req.body;
    const normalizedStatus = VALID_STATUSES.find(
      (validStatus) => validStatus.toLowerCase() === String(status).toLowerCase()
    );

    if (!normalizedStatus) {
      return sendError(
        res,
        `Invalid status. Must be one of: ${VALID_STATUSES.join(', ')}`,
        400
      );
    }

    const session = await Session.findById(req.params.id);
    if (!session) {
      return sendError(res, 'Session not found', 404);
    }

    if (session.professorId.toString() !== req.user.id) {
      return sendError(res, 'Not authorised to update this session', 403);
    }

    const previousStatus = session.status;

    if (previousStatus === normalizedStatus) {
      return sendError(res, `Session is already ${normalizedStatus}`, 400);
    }

    if (['Completed', 'Cancelled'].includes(previousStatus)) {
      return sendError(res, `Cannot change status of a ${previousStatus.toLowerCase()} session`, 400);
    }

    if (previousStatus === 'Upcoming' && !['Active', 'Cancelled'].includes(normalizedStatus)) {
      return sendError(res, `Upcoming sessions can only be changed to Active or Cancelled`, 400);
    }

    if (previousStatus === 'Active' && !['Completed', 'Cancelled'].includes(normalizedStatus)) {
       return sendError(res, `Active sessions can only be changed to Completed or Cancelled`, 400);
    }

    session.status = normalizedStatus as any;

    if (normalizedStatus === 'Active') {
      const clock = new Date();
      if (session.startTime > clock || session.endTime <= clock) {
        return sendError(res, 'Session can only start within its scheduled time window', 400);
      }
      // B2 FIX: Block activation if another session is already active for any overlapping batch.
      if (session.batchIds && session.batchIds.length > 0) {
        const conflicting = await Session.findOne({
          _id: { $ne: session._id },
          status: 'Active',
          batchIds: { $in: session.batchIds },
        }).select('_id title');
        if (conflicting) {
          return sendError(
            res,
            `Cannot activate: session "${conflicting.title}" is already active for an overlapping batch`,
            409
          );
        }
      }

    } else if (normalizedStatus === 'Upcoming' || normalizedStatus === 'Cancelled' || normalizedStatus === 'Completed') {
        if (req.body.startTime && req.body.endTime) {
             if (new Date(req.body.startTime) >= new Date(req.body.endTime)) {
                  return sendError(res, 'startTime must be strictly before endTime', 400);
             }
        }
    }

    await session.save();

    console.log(
      `[session-status] id=${session._id} title="${session.title}" ${previousStatus} -> ${session.status}`
    );

    // -------------------------------------------------------------------
    // Socket.IO: Emit session lifecycle events for connected agents
    // -------------------------------------------------------------------
    const io = getIO();
    if (io) {
      if (normalizedStatus === 'Active') {
        // Fetch the blocked domains from the associated rule set
        let blockedDomains: string[] = [];
        let blockedApps: string[] = [];
        if (session.ruleSetId) {
          try {
            const rule = await Rule.findById(session.ruleSetId);
            if (rule && rule.mode === 'Blocklist') {
              blockedDomains = rule.websites || [];
              blockedApps = rule.applications || [];
            }
          } catch (ruleErr) {
            console.warn('[session-status] Failed to fetch rule for socket emit:', ruleErr);
          }
        }

        io.to(String(session._id)).emit('session_started', {
          sessionId: String(session._id),
          title: session.title,
          course: session.course,
          startTime: session.startTime,
          endTime: session.endTime,
          blockedDomains,
          blockedApps,
        });
        console.log(`[socket] Emitted session_started for ${session._id}`);
      }

      if (['Completed', 'Cancelled'].includes(normalizedStatus)) {
        io.to(String(session._id)).emit('session_ended', {
          sessionId: String(session._id),
          title: session.title,
          previousStatus,
          newStatus: normalizedStatus,
        });
        console.log(`[socket] Emitted session_ended for ${session._id}`);
      }
    }

    // When status changes to "Completed", generate AI summary asynchronously (non-blocking)
    if (normalizedStatus === 'Completed') {
      const sessionIdStr = session._id.toString();
      aggregateSessionData(sessionIdStr)
        .then((aggData) => generateSessionSummary(aggData))
        .then(async (summary) => {
          await Session.findByIdAndUpdate(sessionIdStr, {
            aiSummary: summary,
            summaryGeneratedAt: new Date(),
          });
          console.log(`[AI-Summary] Saved post-session summary for session ${sessionIdStr}`);
        })
        .catch((err) => {
          console.error(`[AI-Summary] Error generating session summary for ${sessionIdStr}:`, err);
        });
    }

    return sendSuccess(res, session, 'Session status updated successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to update session status', 500);
  }
};

// @desc    Join a Session (Student)
// @route   POST /api/sessions/:id/join
export const joinSession = async (req: Request | any, res: Response) => {
  try {
    const session = await Session.findById(req.params.id).select(
      '_id title status startTime endTime batchIds joinedStudentIds'
    );

    if (!session) {
      return sendError(res, 'Session not found', 404);
    }

    // B3 FIX: Only allow joining Active sessions (not Upcoming).
    if (String(session.status) !== 'Active' || session.startTime > new Date() || session.endTime <= new Date()) {
      return sendError(res, `Cannot join a ${String(session.status).toLowerCase()} session. The session must be active.`, 400);
    }

    const student = await Student.findById(req.user.id).select('joinedBatches');
    if (!student) {
      return sendError(res, 'Student not found', 404);
    }

    const joinedBatchIds = (student.joinedBatches || []).map((batchId) => batchId.toString());
    const isAllowed = canStudentAccessSession(session, joinedBatchIds);

    if (!isAllowed) {
      return sendError(res, 'Join the mapped batch first to access this session', 403);
    }

    await Session.findByIdAndUpdate(session._id, {
      $addToSet: { joinedStudentIds: req.user.id },
    });

    console.log(
      `[session-join] student=${req.user.id} joined session=${session._id} status=${session.status}`
    );

    const io = getIO();
    if (io) {
      // Fetch student name for the socket payload
      const studentDoc = await Student.findById(req.user.id).select('name sapId');
      io.to(String(session._id)).emit('student_joined', {
        sessionId: String(session._id),
        studentId: req.user.id,
        studentName: studentDoc?.name || 'Student',
        sapId: studentDoc?.sapId || '',
      });
    }

    return sendSuccess(
      res,
      {
        sessionId: String(session._id),
        status: session.status,
        joined: true,
      },
      'Session joined successfully'
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to join session', 500);
  }
};

// @desc    Delete Session
// @route   DELETE /api/sessions/:id
export const deleteSession = async (req: Request | any, res: Response) => {
  try {
    const session = await Session.findById(req.params.id);

    if (!session) {
      return sendError(res, 'Session not found', 404);
    }

    if (session.professorId.toString() !== req.user.id) {
      return sendError(res, 'Not authorised to delete this session', 403);
    }

    if (session.status === 'Active') return sendError(res, 'Complete or cancel the active session before deleting it', 409);
    await session.deleteOne();
    return sendSuccess(res, null, 'Session deleted successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to delete session', 500);
  }
};

// @desc    Trigger statistical anomaly check for a session
// @route   POST /api/sessions/:id/check-anomalies
export const checkSessionAnomalies = async (req: Request | any, res: Response) => {
  try {
    const { id } = req.params;

    if (!mongoose.isValidObjectId(id)) {
      return sendError(res, 'Invalid session ID format', 400);
    }

    const session = await Session.findById(id);
    if (!session) {
      return sendError(res, 'Session not found', 404);
    }

    if (session.professorId.toString() !== req.user.id) {
      return sendError(res, 'Not authorized for this session', 403);
    }

    const result = await runAnomalyCheck(id);
    return sendSuccess(res, result, 'Anomaly check completed successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to check anomalies', 500);
  }
};

// @desc    Get AI-generated session summary
// @route   GET /api/sessions/:id/summary
export const getSessionSummary = async (req: Request | any, res: Response) => {
  try {
    const { id } = req.params;

    if (!mongoose.isValidObjectId(id)) {
      return sendError(res, 'Invalid session ID format', 400);
    }

    const session = await Session.findById(id).select('professorId aiSummary summaryGeneratedAt');
    if (!session) {
      return sendError(res, 'Session not found', 404);
    }

    if (session.professorId.toString() !== req.user.id) {
      return sendError(res, 'Not authorized to view this summary', 403);
    }

    let stats = null;
    try {
      const aggData = await aggregateSessionData(id);
      stats = {
        totalStudents: aggData.totalStudents,
        totalBlockedAttempts: aggData.totalBlockedAttempts,
        peakDistractionWindow: aggData.peakDistractionWindow,
        anomalousStudents: aggData.anomalousStudents,
      };
    } catch (aggErr) {
      console.warn('[session-summary] Failed to aggregate session stats:', aggErr);
    }

    return sendSuccess(
      res,
      {
        aiSummary: session.aiSummary || null,
        generatedAt: session.summaryGeneratedAt || null,
        stats,
      },
      'Session summary fetched successfully'
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch session summary', 500);
  }
};
