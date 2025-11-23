import express from 'express';
import { createSession, getSessions } from '../controllers/sessionController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createSession)
  .get(protect, getSessions);

export default router;