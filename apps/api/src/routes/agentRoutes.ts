import express from 'express';
import { getAgentConfig, reportAgentActivity, reportAgentHeartbeat } from '../controllers/agentController';

const router = express.Router();

// No auth — open endpoints for desktop agent polling and reporting
router.get('/config', getAgentConfig);
router.post('/report', reportAgentActivity);
router.post('/heartbeat', reportAgentHeartbeat);

export default router;
