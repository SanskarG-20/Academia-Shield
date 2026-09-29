import express from 'express';
import { createLog, getLogs, getSessionLogs } from '../controllers/logController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

// B5 FIX: Restrict creating student activity logs to student role only.
router.post('/', protect, authorize('student'), createLog);
router.get('/', protect, getLogs);
router.get('/:sessionId', protect, authorize('professor'), getSessionLogs);

export default router;