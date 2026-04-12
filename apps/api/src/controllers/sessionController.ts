import { Request, Response } from 'express';
import Session from '../models/Session';

const VALID_STATUSES = ['Upcoming', 'Active', 'Completed', 'Cancelled'];

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
    const sessions = await Session.find({})
      .sort({ startTime: 1 });
    return res.json(sessions);
  }
};

// @desc    Update Session Status
// @route   PATCH /api/sessions/:id/status
export const updateSessionStatus = async (req: Request | any, res: Response) => {
  const { status } = req.body;

  if (!VALID_STATUSES.includes(status)) {
    return res.status(400).json({
      message: `Invalid status. Must be one of: ${VALID_STATUSES.join(', ')}`
    });
  }

  const session = await Session.findById(req.params.id);
  if (!session) {
    return res.status(404).json({ message: 'Session not found' });
  }

  if (session.professorId.toString() !== req.user.id) {
    return res.status(403).json({ message: 'Not authorised to update this session' });
  }

  session.status = status as any;

  // Auto-set startTime when activating if not already set
  if (status === 'Active' && !session.startTime) {
    session.startTime = new Date();
  }

  await session.save();
  res.json(session);
};