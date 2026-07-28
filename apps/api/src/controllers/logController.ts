import { Request, Response } from 'express';
import Log from '../models/Log';
import Session from '../models/Session';
import Student from '../models/Student';
import { sendError, sendSuccess } from '../utils/apiResponse';
import { emitLogEntry } from '../services/socketService';
import mongoose from 'mongoose';

// @desc    Save Logs (Usage or Event)
// @route   POST /api/logs
export const createLog = async (req: Request | any, res: Response) => {
  try {
    const { sessionId, type, resource, details, duration, engagementScore, isViolation } = req.body;

    if (!sessionId || !type) {
      return sendError(res, 'sessionId and type are required', 400);
    }

    const student = await Student.findById(req.user.id).select('name').catch(() => null);
    if (!student && req.user.role === 'student_temp') {
      // For temp students, use sapId from token as fallback
      return sendError(res, 'Please complete your profile setup before logging activity', 403);
    }

    const log = await Log.create({
      sessionId,
      studentId: req.user.id,
      studentName: student?.name || req.user.name || 'Unknown',
      type,
      resource,
      details,
      duration,
      engagementScore,
      isViolation: Boolean(isViolation),
    });

    // Broadcast to connected WebSocket clients.
    emitLogEntry(log);

    return sendSuccess(res, log, 'Log created successfully', 201);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to create log', 500);
  }
};

// @desc    Get Logs (role-aware)
// @route   GET /api/logs
export const getLogs = async (req: Request | any, res: Response) => {
  try {
    const sessionId = req.query.sessionId as string | undefined;

    // Validate sessionId format if provided
    if (sessionId && !mongoose.Types.ObjectId.isValid(sessionId)) {
      return sendSuccess(res, [], 'No logs found');
    }

    if (req.user.role === 'professor') {
      const professorSessions = await Session.find({ professorId: req.user.id }).select('_id');
      const sessionIds = professorSessions.map((s) => s._id);

      const query: any = { sessionId: { $in: sessionIds } };
      if (sessionId) {
        // Narrow to specific session (must still belong to this professor)
        const requestedIdStr = String(sessionId);
        const ownsSession = sessionIds.some((id) => String(id) === requestedIdStr);
        if (ownsSession) {
          query.sessionId = new mongoose.Types.ObjectId(sessionId);
        } else {
          return sendSuccess(res, [], 'No logs found for this session');
        }
      }

      const logs = await Log.find(query).sort({ timestamp: -1 }).limit(500);
      return sendSuccess(res, logs, 'Logs fetched successfully');
    }

    if (req.user.role === 'student' || req.user.role === 'student_temp') {
      const query: any = { studentId: req.user.id };
      if (sessionId) {
        query.sessionId = new mongoose.Types.ObjectId(sessionId);
      }

      const logs = await Log.find(query).sort({ timestamp: -1 }).limit(500);
      return sendSuccess(res, logs, 'Logs fetched successfully');
    }

    return sendError(res, 'Unsupported role for logs', 403);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch logs', 500);
  }
};

// @desc    Get Logs for Session
// @route   GET /api/logs/:sessionId
export const getSessionLogs = async (req: Request | any, res: Response) => {
  try {
    const logs = await Log.find({ sessionId: req.params.sessionId }).sort({ timestamp: -1 });
    return sendSuccess(res, logs, 'Session logs fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch session logs', 500);
  }
};