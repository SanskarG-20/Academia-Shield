import { Router } from 'express';
import { getStudentActivity, getStudentActivitySummary } from '../controllers/activityController';
import { protect, authorize } from '../middleware/auth';

const router = Router();

router.get('/student/:studentId', protect, authorize('professor'), getStudentActivity);
router.get('/student/:studentId/summary', protect, authorize('professor'), getStudentActivitySummary);

export default router;
