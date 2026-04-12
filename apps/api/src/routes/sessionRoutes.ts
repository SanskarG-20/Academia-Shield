import express from 'express';
import { createSession, getSessions, updateSessionStatus } from '../controllers/sessionController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createSession)
  .get(protect, getSessions);

router.patch('/:id/status', protect, authorize('professor'), updateSessionStatus);

export default router;