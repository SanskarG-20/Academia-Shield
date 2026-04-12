import express from 'express';
import { createLog, getSessionLogs } from '../controllers/logController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.post('/', protect, createLog);
router.get('/:sessionId', protect, authorize('professor'), getSessionLogs);

export default router;