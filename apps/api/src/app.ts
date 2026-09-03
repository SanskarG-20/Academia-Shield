import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import authRoutes from './routes/authRoutes';
import batchRoutes from './routes/batchRoutes';
import sessionRoutes from './routes/sessionRoutes';
import ruleRoutes from './routes/ruleRoutes';
import logRoutes from './routes/logRoutes';
import agentRoutes from './routes/agentRoutes';
import activityRoutes from './routes/activityRoutes';
import { errorHandler } from './middleware/error';

const app = express();

// Middleware
const allowedOrigins = [
  'http://localhost:3000',
  'http://localhost:5173',
  'https://academia-shield.vercel.app',
  process.env.FRONTEND_URL || '',
].filter(Boolean);

app.use(cors({
  origin: (origin, callback) => {
    // Allow requests with no origin (like mobile apps, curl, server-to-server)
    if (!origin) return callback(null, true);
    if (process.env.NODE_ENV !== 'production' || allowedOrigins.includes(origin) || origin.endsWith('.vercel.app')) {
      return callback(null, true);
    }
    return callback(new Error('CORS not allowed for this origin'));
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(helmet());
app.use(morgan('dev'));
app.use(express.json());

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/batches', batchRoutes);
app.use('/api/sessions', sessionRoutes);
app.use('/api/rules', ruleRoutes);
app.use('/api/logs', logRoutes);
app.use('/api/agent', agentRoutes);
app.use('/api/activity', activityRoutes);

// Health Check
app.get('/', (req, res) => {
  res.send('Academia Shield API is running...');
});

// Error Handling
app.use(errorHandler);

export default app;