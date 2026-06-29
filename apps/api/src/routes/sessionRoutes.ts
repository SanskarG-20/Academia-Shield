import express from 'express';
import {
  createSession,
  getSessions,
  updateSessionStatus,
  joinSession,
  deleteSession,
} from '../controllers/sessionController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createSession)
  .get(protect, getSessions);

router.patch('/:id/status', protect, authorize('professor'), updateSessionStatus);
router.post('/:id/join', protect, authorize('student'), joinSession);
router.delete('/:id', protect, authorize('professor'), deleteSession);

export default router;