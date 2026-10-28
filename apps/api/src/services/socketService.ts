import { Server, Socket } from 'socket.io';
import jwt from 'jsonwebtoken';
import mongoose from 'mongoose';
import Professor from '../models/Professor';
import Student from '../models/Student';
import Session from '../models/Session';
import { authenticateDevice } from '../middleware/deviceAuth';

let ioInstance: Server | null = null;
export const getIO = () => ioInstance;

export async function authorizeSessionRoom(identity: { role: string; id: string }, sessionId: string): Promise<boolean> {
  if (!mongoose.isValidObjectId(sessionId)) return false;
  const session = await Session.findById(sessionId).select('professorId');
  if (!session) return false;
  if (identity.role === 'professor') return String(session.professorId) === identity.id;
  // Session rooms carry every student's logs and telemetry. Students use REST
  // for their own data, so only the owning professor may join these rooms.
  return false;
}

export const setupSocket = (io: Server) => {
  ioInstance = io;
  io.use(async (socket, next) => {
    try {
      const token = String(socket.handshake.auth?.token || '');
      if (token.startsWith('Device ')) {
        const device = await authenticateDevice(token);
        if (!device) return next(new Error('Device authentication failed'));
        socket.data.identity = { role: 'agent', id: String(device._id), studentId: String(device.studentId) };
        return next();
      }
      const decoded = jwt.verify(token.replace(/^Bearer /, ''), process.env.JWT_SECRET as string) as { id: string; role: string; exp: number };
      if (decoded.role === 'professor' && await Professor.exists({ _id: decoded.id })) {
        socket.data.identity = { role: 'professor', id: decoded.id, exp: decoded.exp };
      } else if (decoded.role === 'student' && await Student.exists({ _id: decoded.id })) {
        socket.data.identity = { role: 'student', id: decoded.id, exp: decoded.exp };
      } else return next(new Error('Invalid socket identity'));
      return next();
    } catch { return next(new Error('Socket authentication required')); }
  });

  io.on('connection', (socket: Socket) => {
    const identity = socket.data.identity as { role: string; id: string; exp?: number };
    if (identity.role === 'agent') socket.join(`device_${identity.id}`);
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;
    if (identity.exp) expiryTimer = setTimeout(() => socket.disconnect(true), Math.max(0, identity.exp * 1000 - Date.now()));
    const revocationTimer = identity.role === 'agent' ? setInterval(async () => {
      if (!await authenticateDevice(String(socket.handshake.auth?.token || ''))) socket.disconnect(true);
    }, 5000) : undefined;

    socket.on('join_session', async (sessionId: string) => {
      if (await authorizeSessionRoom(identity, String(sessionId))) socket.join(String(sessionId));
      else socket.emit('authorization_error', { room: 'session' });
    });
    socket.on('join_live_logs', () => {
      if (identity.role === 'professor') socket.join(`professor_${identity.id}`);
      else socket.emit('authorization_error', { room: 'live_logs' });
    });
    socket.on('join_agent', () => {
      if (identity.role !== 'agent') socket.emit('authorization_error', { room: 'agent' });
    });
    socket.on('disconnect', () => {
      if (expiryTimer) clearTimeout(expiryTimer);
      if (revocationTimer) clearInterval(revocationTimer);
    });
  });
};

export const emitLogEntry = (log: any) => {
  const io = getIO();
  if (!io) return;
  const payload = {
    _id: String(log._id || ''), sessionId: String(log.sessionId || ''),
    studentId: String(log.studentId || ''), studentName: log.studentName || 'Unknown',
    type: log.type || 'EVENT', resource: log.resource || '', details: log.details || '',
    duration: log.duration, engagementScore: log.engagementScore,
    isViolation: Boolean(log.isViolation), timestamp: log.timestamp || new Date().toISOString(),
  };
  if (!payload.sessionId) return;
  io.to(payload.sessionId).emit('live_log_update', payload);
  void Session.findById(payload.sessionId).select('professorId').then(session => {
    if (session) io.to(`professor_${session.professorId}`).emit('live_log_update', payload);
  }).catch(() => undefined);
};

export const emitLogEntries = (logs: any[]) => logs.forEach(emitLogEntry);

export const emitStudentTelemetry = (sessionIds: string[], telemetry: any) => {
  const io = getIO();
  if (io) sessionIds.forEach(sessionId => io.to(sessionId).emit('student_telemetry', { sessionId, ...telemetry }));
};

export const emitStudentActivityUpdate = (sessionIds: string[], data: any) => {
  const io = getIO();
  if (io) sessionIds.forEach(sessionId => io.to(sessionId).emit('student_activity_update', { sessionId, ...data }));
};
