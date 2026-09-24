import { Request, Response } from 'express';
import mongoose from 'mongoose';
import Session from '../models/Session';
import Student from '../models/Student';
import ActivityEvent from '../models/ActivityEvent';
import { sendError, sendSuccess } from '../utils/apiResponse';
import { emitStudentActivityUpdate } from '../services/socketService';
import { getIO } from '../services/socketService';
import { calculateAttentionScore, getScoreLabel, getScoreColor } from '../utils/attentionScore';

const findActiveSessionsForStudent = async (
  studentId: mongoose.Types.ObjectId,
  joinedBatchIds: mongoose.Types.ObjectId[] = [],
  projection = '_id title ruleSetId'
) => {
  const batchAccessQueries: any[] = [
    { batchIds: { $exists: false } },
    { batchIds: { $size: 0 } },
  ];

  if (joinedBatchIds.length > 0) {
    batchAccessQueries.push({ batchIds: { $in: joinedBatchIds } });
  }

  return Session.find({
    status: 'Active',
    joinedStudentIds: studentId,
    $or: batchAccessQueries,
  }).select(projection);
};

const parseDate = (val: any): Date => {
  if (val instanceof Date) return val;
  const num = Number(val);
  if (!isNaN(num)) {
    return new Date(num > 1e11 ? num : Math.round(num * 1000));
  }
  const d = new Date(val);
  return isNaN(d.getTime()) ? new Date() : d;
};

export const ingestActivityBatch = async (req: Request, res: Response) => {
  try {
    const { sapId, events } = req.body;

    const normalizedSapId = String(sapId || '').trim();
    if (!normalizedSapId) {
      return sendError(res, 'sapId is required', 400);
    }

    if (!Array.isArray(events)) {
      return sendError(res, 'events must be an array', 400);
    }

    const student = await Student.findOne({ sapId: normalizedSapId }).select('_id name joinedBatches');
    if (!student) {
      return sendError(res, 'Student not found', 404);
    }

    // B1 FIX: When the caller authenticated via a user JWT (student browser),
    // verify their identity matches the sapId they claim to be reporting for.
    // Desktop agents using X-Agent-Secret don't populate req.user, so they pass through.
    const authUser = (req as any).user;
    if (authUser && authUser.role === 'student' && String(student._id) !== String(authUser.id)) {
      return sendError(res, 'Not authorized to report activity for this student', 403);
    }

    const studentId = student._id as mongoose.Types.ObjectId;
    
    const activeSessions = await findActiveSessionsForStudent(
      studentId,
      (student.joinedBatches || []) as mongoose.Types.ObjectId[],
      '_id'
    );

    if (activeSessions.length === 0) {
      return sendSuccess(res, { inserted: 0, sessions: 0 }, 'No active sessions', 201);
    }

    const sessionIds = activeSessions.map((s) => s._id);
    const documentsToInsert: any[] = [];

    for (const event of events) {
      let eventType = 'APP_FOCUS';
      if (event.status === 'BLOCKED') {
        eventType = 'DOMAIN_BLOCKED';
      } else if (event.domain) {
        eventType = 'DOMAIN_VISIT';
      }

      const startedAt = parseDate(event.startedAt);
      const endedAt = parseDate(event.endedAt);
      const durationMs = typeof event.durationMs === 'number' && event.durationMs >= 0 
        ? event.durationMs 
        : Math.max(0, endedAt.getTime() - startedAt.getTime());

      for (const sessionId of sessionIds) {
        documentsToInsert.push({
          sessionId,
          studentId,
          studentName: student.name,
          sapId: normalizedSapId,
          eventType,
          application: String(event.application || 'Unknown').trim(),
          domain: event.domain ? String(event.domain).trim().toLowerCase() : undefined,
          title: event.title ? String(event.title).slice(0, 200) : undefined,
          status: event.status || 'ALLOWED',
          startedAt,
          endedAt,
          durationMs,
        });
      }
    }

    let insertedCount = 0;
    if (documentsToInsert.length > 0) {
      const inserted = await ActivityEvent.insertMany(documentsToInsert);
      insertedCount = inserted.length;
    }
    
    emitStudentActivityUpdate(sessionIds.map(String), {
      sapId: normalizedSapId,
      studentId: String(studentId),
      eventsCount: events.length,
    });

    // --- Compute and broadcast real-time attention score ---
    const io = getIO();
    if (io && sessionIds.length > 0) {
      const sixtySecondsAgo = new Date(Date.now() - 60_000);

      for (const sessionId of sessionIds) {
        const recentEvents = await ActivityEvent.find({
          sessionId,
          studentId,
          startedAt: { $gte: sixtySecondsAgo },
        })
          .sort({ startedAt: -1 })
          .limit(100)
          .lean();

        const score = calculateAttentionScore(recentEvents);
        const label = getScoreLabel(score);
        const color = getScoreColor(score);

        io.to(String(sessionId)).emit('attention_update', {
          studentId: String(studentId),
          sapId: normalizedSapId,
          score,
          label,
          color,
          timestamp: new Date().toISOString(),
        });
      }
    }

    return sendSuccess(res, { inserted: insertedCount, sessions: sessionIds.length }, 'Activity batch ingested successfully', 201);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to ingest activity', 500);
  }
};

export const getStudentActivity = async (req: Request, res: Response) => {
  try {
    const { studentId } = req.params;
    const { sessionId, limit = '200', offset = '0' } = req.query;

    if (!mongoose.isValidObjectId(studentId)) {
      return sendError(res, 'Invalid studentId format', 400);
    }

    const limitNumber = parseInt(limit as string, 10);
    const offsetNumber = parseInt(offset as string, 10);

    const query: any = { studentId: new mongoose.Types.ObjectId(studentId) };

    if (sessionId) {
      if (!mongoose.isValidObjectId(sessionId)) {
        return sendError(res, 'Invalid sessionId format', 400);
      }
      const session = await Session.findById(sessionId);
      if (!session) {
        return sendError(res, 'Session not found', 404);
      }
      if (String(session.professorId) !== String((req as any).user.id)) {
        return sendError(res, 'Not authorized for this session', 403);
      }
      query.sessionId = new mongoose.Types.ObjectId(sessionId as string);
    } else {
      const professorSessions = await Session.find({ professorId: (req as any).user.id, joinedStudentIds: studentId }).select('_id');
      const sessionIds = professorSessions.map(s => s._id);
      if (sessionIds.length === 0) {
        return sendSuccess(res, [], 'No sessions found');
      }
      query.sessionId = { $in: sessionIds };
    }

    const events = await ActivityEvent.find(query)
      .sort({ startedAt: -1 })
      .skip(offsetNumber)
      .limit(limitNumber);

    return sendSuccess(res, events, 'Student activity fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch student activity', 500);
  }
};

export const getStudentActivitySummary = async (req: Request, res: Response) => {
  try {
    const { studentId } = req.params;
    const { sessionId } = req.query;

    if (!mongoose.isValidObjectId(studentId)) {
      return sendError(res, 'Invalid studentId format', 400);
    }

    const query: any = { studentId: new mongoose.Types.ObjectId(studentId) };

    if (sessionId) {
      if (!mongoose.isValidObjectId(sessionId)) {
        return sendError(res, 'Invalid sessionId format', 400);
      }
      const session = await Session.findById(sessionId);
      if (!session) {
        return sendError(res, 'Session not found', 404);
      }
      if (String(session.professorId) !== String((req as any).user.id)) {
        return sendError(res, 'Not authorized for this session', 403);
      }
      query.sessionId = new mongoose.Types.ObjectId(sessionId as string);
    } else {
      const professorSessions = await Session.find({ professorId: (req as any).user.id, joinedStudentIds: studentId }).select('_id');
      const sessionIds = professorSessions.map(s => s._id);
      if (sessionIds.length === 0) {
        return sendSuccess(res, {
          totalActiveMs: 0,
          topApplications: [],
          topDomains: [],
          blockedAttempts: 0,
          allowedDomains: 0,
          uniqueApps: 0
        }, 'No sessions found');
      }
      query.sessionId = { $in: sessionIds };
    }

    const [summary] = await ActivityEvent.aggregate([
      { $match: query },
      {
        $facet: {
          metrics: [
            {
              $group: {
                _id: null,
                totalActiveMs: { $sum: '$durationMs' },
                blockedAttempts: {
                  $sum: { $cond: [{ $eq: ['$status', 'BLOCKED'] }, 1, 0] }
                },
                distinctDomains: { $addToSet: { $cond: [{ $and: [{ $eq: ['$status', 'ALLOWED'] }, { $ne: [{ $type: '$domain' }, 'missing'] }] }, '$domain', null] } },
                distinctApps: { $addToSet: '$application' }
              }
            }
          ],
          topApplications: [
            {
              $group: {
                _id: '$application',
                durationMs: { $sum: '$durationMs' }
              }
            },
            { $sort: { durationMs: -1 } },
            { $limit: 10 }
          ],
          topDomains: [
            { $match: { domain: { $exists: true, $ne: null } } },
            {
              $group: {
                _id: '$domain',
                durationMs: { $sum: '$durationMs' },
                count: { $sum: 1 }
              }
            },
            { $sort: { durationMs: -1 } },
            { $limit: 10 }
          ]
        }
      }
    ]);

    const metrics = summary.metrics[0] || {
      totalActiveMs: 0,
      blockedAttempts: 0,
      distinctDomains: [],
      distinctApps: []
    };

    const allowedDomainsCount = (metrics.distinctDomains || []).filter((d: any) => d !== null).length;
    const uniqueAppsCount = (metrics.distinctApps || []).length;

    return sendSuccess(res, {
      totalActiveMs: metrics.totalActiveMs,
      topApplications: summary.topApplications.map((t: any) => ({ application: t._id, durationMs: t.durationMs })),
      topDomains: summary.topDomains.map((t: any) => ({ domain: t._id, durationMs: t.durationMs, count: t.count })),
      blockedAttempts: metrics.blockedAttempts,
      allowedDomains: allowedDomainsCount,
      uniqueApps: uniqueAppsCount
    }, 'Summary fetched successfully');

  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch student activity summary', 500);
  }
};

/**
 * GET /api/activity/student/:studentId/attention?sessionId=xxx
 * Returns the real-time attention score for a student in a given session.
 * Protected: professor auth required.
 */
export const getStudentAttention = async (req: Request, res: Response) => {
  try {
    const { studentId } = req.params;
    const { sessionId } = req.query;

    if (!mongoose.isValidObjectId(studentId)) {
      return sendError(res, 'Invalid studentId format', 400);
    }

    if (!sessionId || !mongoose.isValidObjectId(sessionId as string)) {
      return sendError(res, 'sessionId query parameter is required and must be a valid ObjectId', 400);
    }

    // Verify professor owns this session
    const session = await Session.findById(sessionId);
    if (!session) {
      return sendError(res, 'Session not found', 404);
    }
    if (String(session.professorId) !== String((req as any).user.id)) {
      return sendError(res, 'Not authorized for this session', 403);
    }

    const sixtySecondsAgo = new Date(Date.now() - 60_000);

    const recentEvents = await ActivityEvent.find({
      sessionId: new mongoose.Types.ObjectId(sessionId as string),
      studentId: new mongoose.Types.ObjectId(studentId),
      startedAt: { $gte: sixtySecondsAgo },
    })
      .sort({ startedAt: -1 })
      .limit(100)
      .lean();

    const score = calculateAttentionScore(recentEvents);
    const recentBlockedAttempts = recentEvents.filter((e) => e.status === 'BLOCKED').length;

    return sendSuccess(res, {
      score,
      label: getScoreLabel(score),
      color: getScoreColor(score),
      recentBlockedAttempts,
      recentEventsCount: recentEvents.length,
      timestamp: new Date().toISOString(),
    }, 'Attention score fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch attention score', 500);
  }
};
