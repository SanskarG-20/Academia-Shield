import 'dotenv/config';
import dns from 'dns';

// Force Google DNS — fixes SRV lookup failures on hotspot/restricted networks
dns.setServers(['8.8.8.8', '8.8.4.4', '1.1.1.1']);
import http from 'http';
import app from './app';
import { Server } from 'socket.io';
import { connectDB } from './config/db';
import { setupSocket } from './services/socketService';

const PORT = process.env.PORT || 5000;

// Connect to Database
connectDB();

const server = http.createServer(app);

// Setup Socket.io
const io = new Server(server, {
  cors: {
    origin: process.env.CLIENT_URL || "*",
    methods: ["GET", "POST"]
  }
});

// Initialize Socket Service
setupSocket(io);

server.listen(Number(PORT), '0.0.0.0', () => {
  console.log(`🚀 Server running on 0.0.0.0:${PORT}`);
});