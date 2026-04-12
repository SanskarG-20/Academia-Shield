import { Request, Response } from 'express';
import Session from '../models/Session';
import Rule from '../models/Rule';

// @desc    Get active blocking config for desktop agent (NO AUTH)
// @route   GET /api/agent/config
export const getAgentConfig = async (req: Request, res: Response) => {
  try {
    const now = new Date();

    // 1. Find all sessions with status "Active"
    const activeSessions = await Session.find({ status: 'Active' });

    // 2. Filter sessions where current time is between startTime and endTime
    const currentSessions = activeSessions.filter(
      (s) => s.startTime <= now && s.endTime >= now
    );

    // 3. Fetch rules for matching sessions
    const ruleIds = currentSessions
      .map((s) => s.ruleSetId)
      .filter(Boolean);

    const rules = await Rule.find({ _id: { $in: ruleIds } });

    // 4. Merge & deduplicate domains and apps
    const allDomains = new Set<string>();
    const allApps = new Set<string>();

    for (const rule of rules) {
      rule.websites.forEach((w) => allDomains.add(w));
      rule.applications.forEach((a) => allApps.add(a));
    }

    // 5. Build response
    res.json({
      blocking_active: currentSessions.length > 0,
      domains: [...allDomains],
      apps: [...allApps],
      server_time: now.toISOString(),
      active_sessions: currentSessions.map((s) => ({
        id: s._id,
        title: s.title,
        ends_at: s.endTime,
      })),
    });
  } catch (err: any) {
    res.status(500).json({ message: err.message });
  }
};
