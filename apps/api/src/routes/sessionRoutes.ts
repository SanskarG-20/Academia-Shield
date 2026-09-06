import express from 'express';
import {
  createSession,
  getSessions,
  updateSessionStatus,
  joinSession,
  deleteSession,
  checkSessionAnomalies,
  getSessionSummary,
} from '../controllers/sessionController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createSession)
  .get(protect, getSessions);

router.patch('/:id/status', protect, authorize('professor'), updateSessionStatus);
router.post('/:id/join', protect, authorize('student'), joinSession);
router.delete('/:id', protect, authorize('professor'), deleteSession);
router.post('/:id/check-anomalies', protect, authorize('professor'), checkSessionAnomalies);
router.get('/:id/summary', protect, authorize('professor'), getSessionSummary);

export default router;