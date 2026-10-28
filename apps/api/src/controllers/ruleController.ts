import { Request, Response } from 'express';
import Rule from '../models/Rule';
import Session from '../models/Session';
import { sendError, sendSuccess } from '../utils/apiResponse';

const safeList = (value: unknown, maxItems: number, maxLength: number) =>
  Array.isArray(value) && value.length <= maxItems &&
  value.every(item => typeof item === 'string' && item.trim().length > 0 && item.length <= maxLength);

export const createRule = async (req: Request | any, res: Response) => {
  try {
    const { name, mode, websites, applications } = req.body;

    if (!name) {
      return sendError(res, 'Rule name is required', 400);
    }
    if (!safeList(websites ?? [], 200, 253) || !safeList(applications ?? [], 50, 128)) {
      return sendError(res, 'Rule lists exceed safe limits or contain invalid entries', 400);
    }

    const rule = await Rule.create({
      name,
      mode,
      websites: Array.isArray(websites) ? websites : [],
      applications: Array.isArray(applications) ? applications : [],
      professorId: req.user.id,
    });

    return sendSuccess(res, rule, 'Rule created successfully', 201);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to create rule', 500);
  }
};

export const getRules = async (req: Request | any, res: Response) => {
  try {
    const rules = await Rule.find({ professorId: req.user.id }).sort({ createdAt: -1 });
    return sendSuccess(res, rules, 'Rules fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch rules', 500);
  }
};

export const updateRule = async (req: Request | any, res: Response) => {
  try {
    const { name, mode, websites, applications } = req.body;

    const rule = await Rule.findById(req.params.id);
    if (!rule) {
      return sendError(res, 'Rule not found', 404);
    }

    if (rule.professorId.toString() !== req.user.id) {
      return sendError(res, 'Not authorised to update this rule', 403);
    }
    if ((websites !== undefined && !safeList(websites, 200, 253)) ||
        (applications !== undefined && !safeList(applications, 50, 128))) {
      return sendError(res, 'Rule lists exceed safe limits or contain invalid entries', 400);
    }

    if (mode === 'Whitelist' && rule.mode !== 'Whitelist' && await Session.exists({
      ruleSetId: rule._id, status: { $in: ['Upcoming', 'Active'] }, endTime: { $gt: new Date() },
    })) return sendError(res, 'Cannot switch a scheduled blocklist to whitelist', 409);

    if (name) rule.name = name;
    if (mode) rule.mode = mode;
    if (Array.isArray(websites)) rule.websites = websites;
    if (Array.isArray(applications)) rule.applications = applications;

    await rule.save();
    return sendSuccess(res, rule, 'Rule updated successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to update rule', 500);
  }
};

export const deleteRule = async (req: Request | any, res: Response) => {
  try {
    const rule = await Rule.findById(req.params.id);

    if (!rule) {
      return sendError(res, 'Rule not found', 404);
    }

    if (rule.professorId.toString() !== req.user.id) {
      return sendError(res, 'Not authorised to delete this rule', 403);
    }

    const scheduledSession = await Session.findOne({ ruleSetId: rule._id, status: { $in: ['Upcoming', 'Active'] }, endTime: { $gt: new Date() } }).select('title');
    if (scheduledSession) {
      return sendError(
        res,
        `Cannot delete rule: it is attached to scheduled session "${scheduledSession.title}"`,
        400
      );
    }

    await rule.deleteOne();
    return sendSuccess(res, null, 'Rule deleted successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to delete rule', 500);
  }
};
