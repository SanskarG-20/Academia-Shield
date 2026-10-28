import express from 'express';
import { getLogs, getSessionLogs } from '../controllers/logController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.get('/', protect, getLogs);
router.get('/:sessionId', protect, authorize('professor'), getSessionLogs);

export default router;
