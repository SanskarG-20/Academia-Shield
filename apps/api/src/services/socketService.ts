import { Server, Socket } from 'socket.io';

export const setupSocket = (io: Server) => {
  io.on('connection', (socket: Socket) => {
    console.log('New client connected:', socket.id);

    // Join Session Room (Professor or Student)
    socket.on('join_session', (sessionId) => {
      socket.join(sessionId);
      console.log(`Socket ${socket.id} joined session ${sessionId}`);
    });

    // Handle Student Activity Event
    socket.on('student_activity', (data) => {
      // Data: { sessionId, studentName, action, website, status, engagement }
      // Broadcast to everyone in room (mainly Professor)
      io.to(data.sessionId).emit('live_log_update', data);
    });

    // Handle Disconnect
    socket.on('disconnect', () => {
      console.log('Client disconnected:', socket.id);
    });
  });
};