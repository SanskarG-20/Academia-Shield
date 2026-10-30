import express from 'express';
import {
  createBatch,
  getBatches,
  joinBatch,
  getAvailableBatches,
  joinAvailableBatch,
  getMyBatches,
  getBatchById,
} from '../controllers/batchController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createBatch)
  .get(protect, authorize('professor'), getBatches);

router.post('/join', protect, authorize('student'), joinBatch);
router.get('/student/my', protect, authorize('student'), getMyBatches);
router.get('/student/available', protect, authorize('student'), getAvailableBatches);
router.post('/student/available/:id/join', protect, authorize('student'), joinAvailableBatch);
router.get('/:id', protect, getBatchById);

export default router;
