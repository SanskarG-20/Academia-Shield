import express from 'express';
import { getAgentConfig } from '../controllers/agentController';

const router = express.Router();

// No auth — open endpoint for desktop agent polling
router.get('/config', getAgentConfig);

export default router;
