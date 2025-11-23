import http from 'http';
import app from './app';
import { Server } from 'socket.io';
import { connectDB } from './config/db';
import { setupSocket } from './services/socketService';
import dotenv from 'dotenv';

dotenv.config();

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

server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});