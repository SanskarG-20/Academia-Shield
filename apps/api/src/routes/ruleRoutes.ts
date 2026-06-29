import express from 'express';
import { createRule, getRules, updateRule, deleteRule } from '../controllers/ruleController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.route('/')
  .post(protect, authorize('professor'), createRule)
  .get(protect, authorize('professor'), getRules);

router.put('/:id', protect, authorize('professor'), updateRule);
router.delete('/:id', protect, authorize('professor'), deleteRule);

export default router;