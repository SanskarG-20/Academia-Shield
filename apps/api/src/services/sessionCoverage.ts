import crypto from 'crypto';
import { Server } from 'socket.io';
import Batch from '../models/Batch';
import Student from '../models/Student';
import Device from '../models/Device';
import Session from '../models/Session';

// The installed agent sends a heartbeat every 15 seconds (agent.py).
export const AGENT_HEARTBEAT_MS = 15_000;
export const FRESH_MS = 3 * AGENT_HEARTBEAT_MS;

type SessionRecord = { _id: unknown; batchIds: unknown[]; joinedStudentIds: unknown[] };
type BatchRecord = { students: unknown[] };
type StudentRecord = { _id: unknown; name?: string; sapId?: string };
type DeviceRecord = { studentId: unknown; lastSeenAt?: Date | null };

export function classifyCoverage(session: SessionRecord, batches: BatchRecord[], students: StudentRecord[], devices: DeviceRecord[], now = new Date()) {
  const memberIds = new Set(batches.flatMap(batch => batch.students.map(String)));
  const joinedIds = new Set((session.joinedStudentIds || []).map(String));
  const deviceByStudent = new Map<string, DeviceRecord[]>();
  for (const device of devices) {
    const id = String(device.studentId);
    deviceByStudent.set(id, [...(deviceByStudent.get(id) || []), device]);
  }
  const cutoff = now.getTime() - FRESH_MS;
  const entries = students.filter(student => memberIds.has(String(student._id)))
    .map(student => {
      const id = String(student._id);
      const owned = deviceByStudent.get(id) || [];
      const status = !owned.length ? 'not_enrolled'
        : owned.some(device => device.lastSeenAt && new Date(device.lastSeenAt).getTime() >= cutoff)
          ? 'active' : 'enrolled_silent';
      return { studentId: id, name: student.name || '', sapId: student.sapId || '', joined: joinedIds.has(id), status };
    }).sort((a, b) => a.studentId.localeCompare(b.studentId));
  const summary = {
    total: entries.length,
    active: entries.filter(entry => entry.status === 'active').length,
    enrolled_silent: entries.filter(entry => entry.status === 'enrolled_silent').length,
    not_enrolled: entries.filter(entry => entry.status === 'not_enrolled').length,
    joined: entries.filter(entry => entry.joined).length,
  };
  return { sessionId: String(session._id), freshMs: FRESH_MS, summary, students: entries };
}

export async function loadCoverages(sessions: SessionRecord[], now = new Date()) {
  if (!sessions.length) return [];
  const batchIds = [...new Set(sessions.flatMap(session => (session.batchIds || []).map(String)))];
  const batches = await Batch.find({ _id: { $in: batchIds } }).select('students').lean();
  const studentIds = [...new Set(batches.flatMap(batch => batch.students.map(String)))];
  if (!studentIds.length) return sessions.map(session => classifyCoverage(session, [], [], [], now));
  const [students, devices] = await Promise.all([
    Student.find({ _id: { $in: studentIds } }).select('_id name sapId').lean(),
    Device.find({ studentId: { $in: studentIds }, revokedAt: null }).select('studentId lastSeenAt').lean(),
  ]);
  const batchMap = new Map(batches.map(batch => [String(batch._id), batch]));
  return sessions.map(session => classifyCoverage(
    session,
    (session.batchIds || []).map(id => batchMap.get(String(id))).filter((batch): batch is NonNullable<typeof batch> => Boolean(batch)),
    students, devices, now,
  ));
}

export function startCoverageBroadcast(io: Server) {
  const lastHash = new Map<string, string>();
  let running = false;
  const tick = async () => {
    if (running) return;
    running = true;
    try {
      const now = new Date();
      const sessions = await Session.find({ status: 'Active', startTime: { $lte: now }, endTime: { $gt: now } })
        .select('_id batchIds joinedStudentIds professorId').lean();
      const activeIds = new Set(sessions.map(session => String(session._id)));
      for (const id of lastHash.keys()) if (!activeIds.has(id)) lastHash.delete(id);
      const coverages = await loadCoverages(sessions, now);
      for (const coverage of coverages) {
        const hash = crypto.createHash('sha256').update(JSON.stringify(coverage.summary)).digest('hex');
        if (lastHash.get(coverage.sessionId) !== hash) {
          // join_session uses authorizeSessionRoom; only the owning professor can enter this room.
          io.to(coverage.sessionId).emit('session_coverage', coverage);
          lastHash.set(coverage.sessionId, hash);
        }
      }
    } catch (error) {
      console.error('[session-coverage] update failed', error);
    } finally {
      running = false;
    }
  };
  const interval = setInterval(() => { void tick(); }, 15_000);
  return () => { clearInterval(interval); lastHash.clear(); };
}
