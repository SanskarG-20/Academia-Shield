import { Request, Response } from 'express';
import Session from '../models/Session';
import Rule from '../models/Rule';
import Student from '../models/Student';
import Log from '../models/Log';
import Device from '../models/Device';
import { eligibleSessions, policyForDevice } from '../services/devicePolicy';
import { reconcileSessions } from '../services/sessionClock';
import { emitLogEntries, emitStudentTelemetry } from '../services/socketService';
import { sendError, sendSuccess } from '../utils/apiResponse';

export const getAgentConfig = async (req: Request, res: Response) => {
  try {
    const device = (req as any).device;
    const seen = await Device.updateOne({ _id: device._id, revokedAt: null }, { $set: { lastSeenAt: new Date() } });
    if (!seen.matchedCount) return sendError(res, 'Device revoked', 401);
    const policy = await policyForDevice(device);
    return sendSuccess(res, policy, 'Device policy fetched');
  } catch {
    return sendError(res, 'Unable to fetch device policy', 500);
  }
};

// Browser-only view. This endpoint never authenticates an agent or issues an enforceable policy.
export const getAgentOverview = async (req: Request | any, res: Response) => {
  await reconcileSessions();
  const now = new Date();
  const role = req.user?.role;
  let sessions: any[] = [];
  if (role === 'professor') {
    sessions = await Session.find({ professorId: req.user.id, status: 'Active', startTime: { $lte: now }, endTime: { $gt: now } });
  } else if (role === 'student') {
    sessions = await eligibleSessions(req.user.id, now);
  } else {
    return sendError(res, 'Unauthorized role', 403);
  }
  const domains = new Set<string>();
  const apps = new Set<string>();
  for (const session of sessions) {
    const rule = session.ruleSetId && await Rule.findOne({ _id: session.ruleSetId, professorId: session.professorId, mode: 'Blocklist' });
    if (rule) {
      rule.websites.forEach((domain: string) => domains.add(domain));
      rule.applications.forEach((app: string) => apps.add(app));
    }
  }
  return sendSuccess(res, {
    active: sessions.length > 0,
    blocking_active: sessions.length > 0,
    blockedDomains: [...domains], blockedApps: [...apps],
    server_time: now.toISOString(),
    active_sessions: sessions.map(s => ({ id: String(s._id), title: s.title, ends_at: s.endTime })),
  }, 'Overview fetched');
};

export const reportAgentActivity = async (req: Request, res: Response) => {
  const device = (req as any).device;
  const student = await Student.findById(device.studentId);
  if (!student) return sendError(res, 'Enrolled student not found', 403);
  const sessions = await eligibleSessions(device.studentId);
  if (!sessions.length) return sendSuccess(res, { logged: 0 }, 'No eligible active session');
  const action = String(req.body?.action || 'AGENT_EVENT').slice(0, 50);
  const resources = Array.isArray(req.body?.domains) ? req.body.domains.slice(0, 50) : [];
  const entries = sessions.flatMap(session => (resources.length ? resources : ['system']).map((resource: unknown) => ({
    sessionId: session._id, studentId: student._id, studentName: student.name,
    type: 'EVENT', resource: String(resource).slice(0, 200),
    details: `Agent ${action.toLowerCase().replace(/_/g, ' ')}`,
    isViolation: action === 'DOMAIN_BLOCKED' || action === 'APP_BLOCKED' || action === 'APP_CLOSE_REQUESTED', timestamp: new Date(),
  })));
  const inserted = await Log.insertMany(entries);
  emitLogEntries(inserted);
  return sendSuccess(res, { logged: inserted.length }, 'Agent report accepted', 201);
};

export const reportAgentHeartbeat = async (req: Request, res: Response) => {
  const device = (req as any).device;
  const student = await Student.findById(device.studentId);
  if (!student) return sendError(res, 'Enrolled student not found', 403);
  const sessions = await eligibleSessions(device.studentId);
  const activeApp = String(req.body?.activeApp || 'Unknown').slice(0, 200);
  const status = ['online', 'idle', 'offline'].includes(req.body?.status) ? req.body.status : 'online';
  await Device.updateOne({ _id: device._id, revokedAt: null }, { $set: { lastSeenAt: new Date() } });
  if (sessions.length) emitStudentTelemetry(sessions.map(s => String(s._id)), {
    studentId: String(student._id), studentName: student.name, sapId: student.sapId,
    activeApp, status, engagementScore: status === 'online' ? 85 : 50,
    isViolation: false, lastSeen: new Date().toISOString(),
  });
  return sendSuccess(res, { acknowledged: true, sessions: sessions.length }, 'Heartbeat received');
};
