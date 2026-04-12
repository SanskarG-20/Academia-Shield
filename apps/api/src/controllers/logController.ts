import { Request, Response } from 'express';
import Log from '../models/Log';

// @desc    Save Logs (Usage or Event)
// @route   POST /api/logs
export const createLog = async (req: Request | any, res: Response) => {
  const { sessionId, type, resource, details, duration, engagementScore, isViolation } = req.body;

  const log = await Log.create({
    sessionId,
    studentId: req.user.id,
    studentName: req.user.name || 'Unknown', // Ideally fetched from DB
    type,
    resource,
    details,
    duration,
    engagementScore,
    isViolation
  });

  res.status(201).json(log);
};

// @desc    Get Logs for Session
// @route   GET /api/logs/:sessionId
export const getSessionLogs = async (req: Request | any, res: Response) => {
  const logs = await Log.find({ sessionId: req.params.sessionId }).sort({ timestamp: -1 });
  res.json(logs);
};