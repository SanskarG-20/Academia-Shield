import { Request, Response } from 'express';
import Session from '../models/Session';
import Rule from '../models/Rule';
import { sendError, sendSuccess } from '../utils/apiResponse';

const parseBoolean = (value: string | undefined, fallback = false) => {
  if (typeof value !== 'string') {
    return fallback;
  }

  return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
};

const TEST_MODE = parseBoolean(process.env.TEST_MODE, false);
const ALLOWED_DEVICE_IDS = new Set(
  (process.env.AGENT_ALLOWED_DEVICE_IDS || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
);

const normalizeDomain = (value: string) => value.trim().toLowerCase();

// @desc    Get active blocking config for desktop agent (NO AUTH)
// @route   GET /api/agent/config
export const getAgentConfig = async (req: Request, res: Response) => {
  try {
    const now = new Date();
    const deviceId = String(req.query.deviceId || req.headers['x-device-id'] || '').trim();
    const requiresDeviceCheck = ALLOWED_DEVICE_IDS.size > 0;
    const deviceAuthorized =
      TEST_MODE || !requiresDeviceCheck || (deviceId ? ALLOWED_DEVICE_IDS.has(deviceId) : false);

    if (!deviceAuthorized) {
      console.warn(`[agent-config] denied device=${deviceId || 'unknown'} testMode=${TEST_MODE}`);

      return sendSuccess(
        res,
        {
          active: false,
          blockedDomains: [],
          blockedApps: [],
          blocking_active: false,
          domains: [],
          apps: [],
          server_time: now.toISOString(),
          active_sessions: [],
          test_mode: TEST_MODE,
          device_authorized: false,
        },
        'Agent device is not authorised'
      );
    }

    // 1. Fetch only currently active-in-window sessions.
    const currentSessions = await Session.find({
      status: 'Active',
      startTime: { $lte: now },
      endTime: { $gte: now },
    }).select('_id title endTime ruleSetId');

    // 2. Fetch rules for matching sessions.
    const ruleIds = currentSessions
      .map((s) => s.ruleSetId)
      .filter(Boolean);

    const rules = await Rule.find({ _id: { $in: ruleIds } });
    const blockingRules = rules.filter(
      (rule) => String(rule.mode || '').toLowerCase() === 'blocklist'
    );

    // 3. Merge & deduplicate domains and apps.
    const allDomains = new Set<string>();
    const allApps = new Set<string>();

    for (const rule of blockingRules) {
      rule.websites
        .map(normalizeDomain)
        .filter(Boolean)
        .forEach((website) => allDomains.add(website));
      rule.applications
        .map((app) => app.trim())
        .filter(Boolean)
        .forEach((app) => allApps.add(app));
    }

    const blockedDomains = [...allDomains];
    const blockedApps = [...allApps];
    const isActive = currentSessions.length > 0;

    console.log(
      `[agent-config] testMode=${TEST_MODE} device=${deviceId || 'n/a'} sessions=${currentSessions.length} blockedDomains=${blockedDomains.length}`
    );

    // 4. Build response.
    return sendSuccess(
      res,
      {
        // New keys for one-machine demo/testing workflows.
        active: isActive,
        blockedDomains,
        blockedApps,

        // Backward-compatible keys used by existing clients.
        blocking_active: isActive,
        domains: blockedDomains,
        apps: blockedApps,

        server_time: now.toISOString(),
        active_sessions: currentSessions.map((s) => ({
          id: s._id,
          title: s.title,
          ends_at: s.endTime,
        })),
        test_mode: TEST_MODE,
        device_authorized: true,
      },
      'Agent config fetched successfully'
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch agent config', 500);
  }
};
