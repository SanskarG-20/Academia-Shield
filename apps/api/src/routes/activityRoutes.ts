import { Router } from 'express';
import { getStudentActivity, getStudentActivitySummary, getStudentAttention } from '../controllers/activityController';
import { protect, authorize } from '../middleware/auth';

const router = Router();

router.get('/student/:studentId', protect, authorize('professor'), getStudentActivity);
router.get('/student/:studentId/summary', protect, authorize('professor'), getStudentActivitySummary);
router.get('/student/:studentId/attention', protect, authorize('professor'), getStudentAttention);

export default router;
