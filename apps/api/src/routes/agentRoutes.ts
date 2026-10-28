import express from 'express';
import { getAgentConfig, getAgentOverview, reportAgentActivity, reportAgentHeartbeat } from '../controllers/agentController';
import { ingestActivityBatch } from '../controllers/activityController';
import { enrollDevice, issueEnrollmentClaim, listDevices, revokeDevice } from '../controllers/enrollmentController';
import { deviceAuth } from '../middleware/deviceAuth';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();
router.post('/enrollment-claims', protect, authorize('student'), issueEnrollmentClaim);
router.post('/enroll', enrollDevice);
router.get('/devices', protect, authorize('student'), listDevices);
router.delete('/devices/:id', protect, authorize('student'), revokeDevice);
router.get('/overview', protect, getAgentOverview);
router.get('/config', deviceAuth, getAgentConfig);
router.post('/report', deviceAuth, reportAgentActivity);
router.post('/heartbeat', deviceAuth, reportAgentHeartbeat);
router.post('/activity', deviceAuth, ingestActivityBatch);
export default router;
