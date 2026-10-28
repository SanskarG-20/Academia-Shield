import { io, Socket } from 'socket.io-client';
import { BASE_URL } from './api';

let socket: Socket | null = null;
const activeSessionRooms = new Set<string>();
let isLiveLogsActive = false;

/**
 * Get or create the shared Socket.IO client connection.
 */
export function getSocket(): Socket {
  const token = localStorage.getItem('access_token') || localStorage.getItem('token') || '';
  
  if (!socket) {
    socket = io(BASE_URL, {
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 20,
      auth: { token },
      query: { token },
    });

    socket.on('connect', () => {
      console.log('[socket] connected:', socket?.id);
      // Auto-rejoin rooms after initial connect or reconnect
      if (isLiveLogsActive) {
        socket?.emit('join_live_logs');
      }
      activeSessionRooms.forEach((sessId) => {
        socket?.emit('join_session', { session_id: sessId });
      });
    });

    socket.on('disconnect', (reason) => {
      console.log('[socket] disconnected:', reason);
    });

    socket.on('connect_error', (err) => {
      console.warn('[socket] connection error:', err.message);
    });
  } else if (token && (socket.auth as any)?.token !== token) {
    socket.auth = { token };
    (socket.io.opts as any).query = { token };
    socket.disconnect().connect();
  }

  return socket;
}

export function reconnectSocket(): void {
  if (socket) {
    const token = localStorage.getItem('access_token') || localStorage.getItem('token') || '';
    socket.auth = { token };
    (socket.io.opts as any).query = { token };
    socket.disconnect().connect();
  } else {
    getSocket();
  }
}

/**
 * Join the live_logs broadcast room (for professors monitoring all sessions).
 */
export function joinLiveLogs(): void {
  isLiveLogsActive = true;
  const s = getSocket();
  if (s.connected) {
    s.emit('join_live_logs');
  }
}

export function leaveLiveLogs(): void {
  isLiveLogsActive = false;
}

/**
 * Join a specific session room for targeted monitoring and presence tracking.
 */
export function joinSession(sessionId: string): void {
  if (!sessionId) return;
  activeSessionRooms.add(sessionId);
  const s = getSocket();
  if (s.connected) {
    s.emit('join_session', { session_id: sessionId });
  }
}

export function joinSessionRoom(sessionId: string): void {
  joinSession(sessionId);
}

/**
 * Subscribe professor to real-time engagement updates for a session.
 */
export function subscribeEngagement(sessionId: string): void {
  if (!sessionId) return;
  const s = getSocket();
  if (s.connected) {
    s.emit('subscribe_engagement_session', { session_id: sessionId });
  } else {
    s.once('connect', () => {
      s.emit('subscribe_engagement_session', { session_id: sessionId });
    });
  }
}

/**
 * Send 20s presence heartbeat from student browser.
 */
export function sendPresenceHeartbeat(sessionId: string): void {
  const s = getSocket();
  s.emit('session_presence_heartbeat', { session_id: sessionId });
}

/**
 * Notify server when student manually leaves or navigates away.
 */
export function leaveSessionRoom(sessionId: string): void {
  if (sessionId) {
    activeSessionRooms.delete(sessionId);
  }
  if (socket && socket.connected) {
    socket.emit('session_leave', { session_id: sessionId });
  }
}

/**
 * Disconnect the socket (call on logout or cleanup).
 */
export function disconnectSocket(): void {
  activeSessionRooms.clear();
  isLiveLogsActive = false;
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}
