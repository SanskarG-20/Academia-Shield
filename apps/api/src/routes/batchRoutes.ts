import express from 'express';
import {
  createBatch,
  getBatches,
  joinBatch,
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
router.get('/:id', protect, getBatchById);

export default router;