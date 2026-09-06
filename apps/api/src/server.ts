import 'dotenv/config';
import http from 'http';
import app from './app';
import { Server } from 'socket.io';
import { connectDB } from './config/db';
import { setupSocket } from './services/socketService';
import Session from './models/Session';
import { runAnomalyCheck } from './services/anomalyService';

const PORT = process.env.PORT || 5000;

const server = http.createServer(app);

// Setup Socket.io with dynamic CORS origin matching
const socketAllowedOrigins = new Set([
  'http://localhost:3000',
  'http://localhost:5173',
  'https://academia-shield.vercel.app',
  process.env.FRONTEND_URL || '',
].filter(Boolean));

const io = new Server(server, {
  cors: {
    origin: (origin, callback) => {
      // Allow requests with no origin (agents, curl, server-to-server)
      if (!origin) return callback(null, true);
      // In development, allow everything
      if (process.env.NODE_ENV !== 'production') return callback(null, true);
      // Allow exact matches, any .vercel.app subdomain, and localhost
      if (
        socketAllowedOrigins.has(origin) ||
        origin.endsWith('.vercel.app') ||
        origin.startsWith('http://localhost')
      ) {
        return callback(null, true);
      }
      return callback(new Error('Socket.IO CORS rejected'));
    },
    methods: ["GET", "POST", "PATCH", "PUT", "DELETE"],
    credentials: true
  },
  allowEIO3: true,
  transports: ['websocket', 'polling']
});

// Initialize Socket Service
setupSocket(io);

const startServer = async () => {
  try {
    await connectDB();
    server.listen(Number(PORT), '0.0.0.0', () => {
      console.log(`🚀 Server running on 0.0.0.0:${PORT}`);
    });

    // Schedule anomaly checks during active sessions (every 5 minutes)
    setInterval(async () => {
      try {
        const activeSessions = await Session.find({ status: { $in: ['Active', 'active'] } });
        for (const session of activeSessions) {
          await runAnomalyCheck(session._id.toString()).catch(console.error);
        }
      } catch (err) {
        console.error('Error running scheduled anomaly checks:', err);
      }
    }, 5 * 60 * 1000);
  } catch (error: any) {
    console.error(`❌ Unable to start server: ${error.message}`);
    process.exit(1);
  }
};

void startServer();