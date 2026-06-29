import { Request, Response } from 'express';
import mongoose from 'mongoose';
import Session from '../models/Session';
import Rule from '../models/Rule';
import Log from '../models/Log';
import Student from '../models/Student';
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

// @desc    Receive blocking activity reports from the desktop agent (NO AUTH)
// @route   POST /api/agent/report
export const reportAgentActivity = async (req: Request, res: Response) => {
  try {
    const {
      agentId,
      sapId,
      action,
      domains,
    } = req.body || {};

    const agentName = String(agentId || 'unknown-agent').trim();
    const reportAction = String(action || 'BLOCK_APPLIED').trim();
    const reportedDomains: string[] = Array.isArray(domains)
      ? domains.map((d: any) => String(d).trim().toLowerCase()).filter(Boolean)
      : [];

    // Resolve student if sapId was provided.
    let studentId: mongoose.Types.ObjectId | null = null;
    let studentName = agentName;

    if (sapId) {
      const student = await Student.findOne({ sapId: String(sapId).trim() }).select('_id name');
      if (student) {
        studentId = student._id as mongoose.Types.ObjectId;
        studentName = student.name || agentName;
      }
    }

    // If no student was resolved, use a deterministic placeholder ObjectId derived from agentId.
    if (!studentId) {
      const hex = Buffer.from(agentName.padEnd(12, '0').slice(0, 12)).toString('hex').slice(0, 24);
      studentId = new mongoose.Types.ObjectId(hex);
    }

    // Find active sessions (same criteria as getAgentConfig).
    const now = new Date();
    const activeSessions = await Session.find({
      status: 'Active',
      startTime: { $lte: now },
      endTime: { $gte: now },
    }).select('_id title');

    if (activeSessions.length === 0) {
      return sendSuccess(res, { logged: 0 }, 'No active sessions; report acknowledged');
    }

    // Determine log type and violation flag based on the action.
    const isBlock = reportAction === 'BLOCK_APPLIED';
    const logType: 'EVENT' | 'USAGE' | 'ANOMALY' = isBlock ? 'EVENT' : 'EVENT';
    const isViolation = isBlock;

    // Create one log entry per domain per active session.
    const logEntries: any[] = [];

    for (const session of activeSessions) {
      if (reportedDomains.length === 0) {
        // Action with no specific domains (e.g. BLOCK_REMOVED, standby).
        logEntries.push({
          sessionId: session._id,
          studentId,
          studentName,
          type: 'EVENT',
          resource: 'system',
          details: `Agent ${reportAction.toLowerCase().replace(/_/g, ' ')} (${agentName})`,
          engagementScore: isBlock ? 0 : 100,
          isViolation: false,
          timestamp: now,
        });
      } else {
        for (const domain of reportedDomains) {
          logEntries.push({
            sessionId: session._id,
            studentId,
            studentName,
            type: logType,
            resource: domain,
            details: `Agent blocked access to ${domain} (${agentName})`,
            engagementScore: isBlock ? 10 : 90,
            isViolation,
            timestamp: now,
          });
        }
      }
    }

    const inserted = await Log.insertMany(logEntries);

    console.log(
      `[agent-report] agent=${agentName} action=${reportAction} domains=${reportedDomains.length} sessions=${activeSessions.length} logs=${inserted.length}`
    );

    return sendSuccess(
      res,
      {
        logged: inserted.length,
        sessions: activeSessions.length,
        action: reportAction,
      },
      'Agent activity logged successfully',
      201
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to log agent activity', 500);
  }
};
