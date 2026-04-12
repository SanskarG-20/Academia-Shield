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
import { errorHandler } from './middleware/error';

const app = express();

// Middleware
app.use(cors({ origin: '*', credentials: false }));
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

// Health Check
app.get('/', (req, res) => {
  res.send('Academia Shield API is running...');
});

// Error Handling
app.use(errorHandler);

export default app;