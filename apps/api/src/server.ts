import 'dotenv/config';
import http from 'http';
import app from './app';
import { Server } from 'socket.io';
import { connectDB } from './config/db';
import { setupSocket } from './services/socketService';

const PORT = process.env.PORT || 5000;

const server = http.createServer(app);

// Setup Socket.io
const socketAllowedOrigins = [
  'http://localhost:3000',
  'http://localhost:5173',
  'https://academia-shield.vercel.app',
  process.env.FRONTEND_URL || '',
].filter(Boolean);

const io = new Server(server, {
  cors: {
    origin: process.env.NODE_ENV === 'production' ? socketAllowedOrigins : true,
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
  } catch (error: any) {
    console.error(`❌ Unable to start server: ${error.message}`);
    process.exit(1);
  }
};

void startServer();