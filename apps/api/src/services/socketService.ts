import { Server, Socket } from 'socket.io';

let ioInstance: Server | null = null;

export const getIO = (): Server | null => ioInstance;

export const setupSocket = (io: Server) => {
  ioInstance = io;

  io.on('connection', (socket: Socket) => {
    console.log('[socket] client connected:', socket.id);

    // Join Session Room (Professor or Student)
    socket.on('join_session', (sessionId: string) => {
      if (sessionId) {
        socket.join(sessionId);
        console.log(`[socket] ${socket.id} joined session room ${sessionId}`);
      }
    });

    // Join a broadcast room for all live logs (professors monitor all active sessions)
    socket.on('join_live_logs', () => {
      socket.join('live_logs');
      console.log(`[socket] ${socket.id} joined live_logs room`);
    });

    // Handle Student Activity Event
    socket.on('student_activity', (data) => {
      // Data: { sessionId, studentName, action, website, status, engagement }
      // Broadcast to everyone in room (mainly Professor)
      if (data?.sessionId) {
        io.to(data.sessionId).emit('live_log_update', data);
      }
      // Also broadcast to the live_logs room
      io.to('live_logs').emit('live_log_update', data);
    });

    // Handle Disconnect
    socket.on('disconnect', () => {
      console.log('[socket] client disconnected:', socket.id);
    });
  });
};

/**
 * Emit a new log entry to all relevant rooms.
 * Called from controllers when logs are created.
 */
export const emitLogEntry = (log: {
  _id?: any;
  sessionId?: any;
  studentId?: any;
  studentName?: string;
  type?: string;
  resource?: string;
  details?: string;
  duration?: number;
  engagementScore?: number;
  isViolation?: boolean;
  timestamp?: any;
}) => {
  const io = getIO();
  if (!io) return;

  const payload = {
    _id: String(log._id || ''),
    sessionId: String(log.sessionId || ''),
    studentId: String(log.studentId || ''),
    studentName: log.studentName || 'Unknown',
    type: log.type || 'EVENT',
    resource: log.resource || '',
    details: log.details || '',
    duration: log.duration,
    engagementScore: log.engagementScore,
    isViolation: Boolean(log.isViolation),
    timestamp: log.timestamp || new Date().toISOString(),
  };

  // Emit to the specific session room
  if (payload.sessionId) {
    io.to(payload.sessionId).emit('live_log_update', payload);
  }

  // Emit to the global live_logs room (for the professor's LiveLogs page)
  io.to('live_logs').emit('live_log_update', payload);
};

/**
 * Emit multiple log entries (e.g. from agent bulk reports).
 */
export const emitLogEntries = (logs: any[]) => {
  for (const log of logs) {
    emitLogEntry(log);
  }
};