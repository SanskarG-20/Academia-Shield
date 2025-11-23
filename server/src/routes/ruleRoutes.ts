import express from 'express';
import { createRule, getRules } from '../controllers/ruleController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createRule)
  .get(protect, authorize('professor'), getRules);

export default router;