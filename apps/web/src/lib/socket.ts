import { io, Socket } from 'socket.io-client';
import { BASE_URL } from './api';

let socket: Socket | null = null;

/**
 * Get or create the shared Socket.IO client connection.
 */
export function getSocket(): Socket {
  if (!socket) {
    socket = io(BASE_URL, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 10,
    });

    socket.on('connect', () => {
      console.log('[socket] connected:', socket?.id);
    });

    socket.on('disconnect', (reason) => {
      console.log('[socket] disconnected:', reason);
    });

    socket.on('connect_error', (err) => {
      console.warn('[socket] connection error:', err.message);
    });
  }

  return socket;
}

/**
 * Join the live_logs broadcast room (for professors monitoring all sessions).
 */
export function joinLiveLogs(): void {
  const s = getSocket();
  s.emit('join_live_logs');
}

/**
 * Join a specific session room (for targeted session monitoring).
 */
export function joinSession(sessionId: string): void {
  const s = getSocket();
  s.emit('join_session', sessionId);
}

/**
 * Disconnect the socket (call on logout or cleanup).
 */
export function disconnectSocket(): void {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}
