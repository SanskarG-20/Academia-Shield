import { Request, Response } from 'express';
import Session from '../models/Session';
import Rule from '../models/Rule';
import Student from '../models/Student';
import { sendError, sendSuccess } from '../utils/apiResponse';
import { getIO } from '../services/socketService';

const VALID_STATUSES = ['Upcoming', 'Active', 'Completed', 'Cancelled'];

const canStudentAccessSession = (session: any, joinedBatchIds: string[]) => {
  if (!session.batchIds || session.batchIds.length === 0) {
    return true;
  }

  const joinedSet = new Set(joinedBatchIds);
  return session.batchIds.some((batchId: any) => joinedSet.has(batchId.toString()));
};

// @desc    Create Session
// @route   POST /api/sessions
export const createSession = async (req: Request | any, res: Response) => {
  try {
    const { title, course, type, startTime, endTime, ruleSetId, batchIds } = req.body;

    if (!title || !course || !type || !startTime || !endTime) {
      return sendError(res, 'title, course, type, startTime and endTime are required', 400);
    }

    const session = await Session.create({
      title,
      course,
      type,
      startTime,
      endTime,
      ruleSetId,
      batchIds: Array.isArray(batchIds) ? batchIds : [],
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

      const sessions = await Session.find({
        $or: [
          { batchIds: { $in: joinedBatchIds } },
          { batchIds: { $exists: false } },
          { batchIds: { $size: 0 } },
        ],
      }).sort({ startTime: 1 });

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

    session.status = normalizedStatus as any;

    if (normalizedStatus === 'Active') {
      const now = new Date();

      // Manual activation should always make the session active in the current window.
      if (!session.startTime || session.startTime > now) {
        session.startTime = now;
      }

      if (!session.endTime || session.endTime <= now || session.endTime <= session.startTime) {
        session.endTime = new Date(now.getTime() + 60 * 60 * 1000);
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

        io.emit('session_started', {
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
        io.emit('session_ended', {
          sessionId: String(session._id),
          title: session.title,
          previousStatus,
          newStatus: normalizedStatus,
        });
        console.log(`[socket] Emitted session_ended for ${session._id}`);
      }
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
      '_id title status batchIds joinedStudentIds'
    );

    if (!session) {
      return sendError(res, 'Session not found', 404);
    }

    if (['Completed', 'Cancelled'].includes(String(session.status))) {
      return sendError(res, `Cannot join a ${session.status.toLowerCase()} session`, 400);
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

    await session.deleteOne();
    return sendSuccess(res, null, 'Session deleted successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to delete session', 500);
  }
};