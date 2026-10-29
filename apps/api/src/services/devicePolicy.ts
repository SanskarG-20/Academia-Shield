import mongoose from 'mongoose';
import Device, { IDevice } from '../models/Device';
import Student from '../models/Student';
import Session from '../models/Session';
import Rule from '../models/Rule';
import { reconcileSessions } from './sessionClock';

export async function eligibleSessions(studentId: mongoose.Types.ObjectId, now = new Date()) {
  const student = await Student.findById(studentId).select('joinedBatches');
  const joined = student?.joinedBatches || [];
  if (!joined.length) return [];
  return Session.find({
    status: 'Active', startTime: { $lte: now }, endTime: { $gt: now },
    batchIds: { $in: joined },
    $or: [
      { joinMode: 'auto' },
      { joinMode: { $ne: 'auto' }, joinedStudentIds: studentId },
    ],
  }).select('_id title startTime endTime professorId ruleSetId batchIds joinMode');
}

export async function policyForDevice(device: IDevice, now = new Date()) {
  if (device.revokedAt) throw new Error('Device revoked');
  await reconcileSessions(now);
  const sessions = await eligibleSessions(device.studentId, now);
  const domains = new Set<string>();
  const apps = new Set<string>();
  const authorized = [];
  for (const session of sessions) {
    if (!session.ruleSetId) continue;
    const rule = await Rule.findOne({ _id: session.ruleSetId, professorId: session.professorId, mode: 'Blocklist' });
    if (!rule) continue;
    authorized.push(session);
    (rule.websites || []).forEach(value => { if (value.trim()) domains.add(value.trim().toLowerCase()); });
    (rule.applications || []).forEach(value => { if (value.trim()) apps.add(value.trim().toLowerCase()); });
  }
  const expiry = authorized.length
    ? Math.min(now.getTime() + 5 * 60_000, ...authorized.map(s => s.endTime.getTime()))
    : now.getTime();
  return {
    active: authorized.length > 0,
    deviceId: String(device._id),
    issuedAt: now.toISOString(),
    expiresAt: new Date(expiry).toISOString(),
    blockedDomains: [...domains],
    blockedApps: [...apps],
    active_sessions: authorized.map(s => ({ id: String(s._id), title: s.title, ends_at: s.endTime.toISOString() })),
  };
}
