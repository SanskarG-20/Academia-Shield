import express from 'express';
import { getAgentConfig, reportAgentActivity } from '../controllers/agentController';

const router = express.Router();

// No auth — open endpoints for desktop agent polling and reporting
router.get('/config', getAgentConfig);
router.post('/report', reportAgentActivity);

export default router;
