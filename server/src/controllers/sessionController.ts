import { Request, Response } from 'express';
import Session from '../models/Session';

// @desc    Create Session
// @route   POST /api/sessions
export const createSession = async (req: Request | any, res: Response) => {
  const { title, course, type, startTime, endTime, ruleSetId, batchIds } = req.body;

  const session = await Session.create({
    title,
    course,
    type,
    startTime,
    endTime,
    ruleSetId,
    batchIds,
    professorId: req.user.id
  });

  res.status(201).json(session);
};

// @desc    Get All Sessions (with role filtering)
// @route   GET /api/sessions
export const getSessions = async (req: Request | any, res: Response) => {
  if (req.user.role === 'professor') {
    const sessions = await Session.find({ professorId: req.user.id })
      .sort({ startTime: -1 });
    return res.json(sessions);
  } else {
    // Student: Get sessions for their batches + public sessions
    // Need to fetch student's batches first. 
    // Simplified: passing logic to client or looking up student first
    const sessions = await Session.find({}) // In production, filter by batchIds
      .sort({ startTime: 1 });
    return res.json(sessions);
  }
};