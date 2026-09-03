import express from 'express';
import { getAgentConfig, reportAgentActivity, reportAgentHeartbeat } from '../controllers/agentController';
import { ingestActivityBatch } from '../controllers/activityController';
import { agentAuth } from '../middleware/agentAuth';

const router = express.Router();

// Callers present either the shared agent secret or a signed-in user's JWT.
// See middleware/agentAuth.ts — enforcement activates once AGENT_SHARED_SECRET is set.
router.use(agentAuth);

router.get('/config', getAgentConfig);
router.post('/report', reportAgentActivity);
router.post('/heartbeat', reportAgentHeartbeat);
router.post('/activity', ingestActivityBatch);

export default router;
