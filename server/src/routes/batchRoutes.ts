import express from 'express';
import { createBatch, getBatches, joinBatch } from '../controllers/batchController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createBatch)
  .get(protect, authorize('professor'), getBatches);

router.post('/join', protect, authorize('student'), joinBatch);

export default router;