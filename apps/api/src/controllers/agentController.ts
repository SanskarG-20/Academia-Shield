import { Request, Response } from 'express';
import mongoose from 'mongoose';
import Session from '../models/Session';
import Rule from '../models/Rule';
import Log from '../models/Log';
import Student from '../models/Student';
import { sendError, sendSuccess } from '../utils/apiResponse';
import { emitLogEntries, emitStudentTelemetry } from '../services/socketService';

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

// An empty allowlist waves every device through, which is easy to mistake for an
// active control. Say so once at boot rather than letting it pass silently.
if (ALLOWED_DEVICE_IDS.size === 0) {
  console.warn(
    '[agent-config] AGENT_ALLOWED_DEVICE_IDS is empty — every device is accepted. ' +
      'Authentication is handled by AGENT_SHARED_SECRET; set that if it is unset.'
  );
}
if (TEST_MODE && process.env.NODE_ENV === 'production') {
  console.warn('[agent-config] TEST_MODE=true in production — the device allowlist is bypassed.');
}

const normalizeDomain = (value: string) => value.trim().toLowerCase();

/**
 * A device may only publish telemetry to an active session its configured
 * student has joined and is entitled to access through a mapped batch (or a
 * public session). This prevents one student's agent appearing in every live
 * classroom.
 */
const findActiveSessionsForStudent = async (
  studentId: mongoose.Types.ObjectId,
  joinedBatchIds: mongoose.Types.ObjectId[] = [],
  projection = '_id title ruleSetId'
) => {
  const batchAccessQueries: any[] = [
    { batchIds: { $exists: false } },
    { batchIds: { $size: 0 } },
  ];

  if (joinedBatchIds.length > 0) {
    batchAccessQueries.push({ batchIds: { $in: joinedBatchIds } });
  }

  return Session.find({
    status: 'Active',
    joinedStudentIds: studentId,
    $or: batchAccessQueries,
  }).select(projection);
};

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

    // 1. Fetch active sessions (any session with status 'Active').
    const currentSessions = await Session.find({
      status: 'Active',
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

    const normalizedSapId = String(sapId || '').trim();
    if (!normalizedSapId) {
      return sendError(res, 'A registered student SAP ID is required for agent activity', 400);
    }

    const student = await Student.findOne({ sapId: normalizedSapId }).select('_id name joinedBatches');
    if (!student) {
      return sendError(res, 'No registered student matches this agent SAP ID', 404);
    }

    // B1 FIX: Prevent identity spoofing when caller authenticates via user JWT.
    const authUser = (req as any).user;
    if (authUser && authUser.role === 'student' && String(student._id) !== String(authUser.id)) {
      return sendError(res, 'Not authorized to report activity for this student', 403);
    }

    const studentId = student._id as mongoose.Types.ObjectId;
    const studentName = student.name || agentName;

    // Find only sessions this student has explicitly joined and can access.
    const now = new Date();
    const activeSessions = await findActiveSessionsForStudent(
      studentId,
      (student.joinedBatches || []) as mongoose.Types.ObjectId[],
      '_id title'
    );

    if (activeSessions.length === 0) {
      return sendSuccess(res, { logged: 0 }, 'No joined active sessions; report acknowledged');
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

    // Broadcast new logs to connected WebSocket clients (professors watching LiveLogs).
    emitLogEntries(inserted);

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

// @desc    Receive periodic heartbeat/telemetry from the desktop agent (NO AUTH)
// @route   POST /api/agent/heartbeat
export const reportAgentHeartbeat = async (req: Request, res: Response) => {
  try {
    const { sapId, activeApp, status } = req.body || {};

    if (!sapId) {
      return sendError(res, 'sapId is required for heartbeat', 400);
    }

    const student = await Student.findOne({ sapId: String(sapId).trim() }).select(
      '_id name sapId joinedBatches'
    );
    if (!student) {
      return sendSuccess(res, { acknowledged: false }, 'Student not found');
    }

    // Find only sessions this student has explicitly joined and can access.
    const now = new Date();
    const activeSessions = await findActiveSessionsForStudent(
      student._id as mongoose.Types.ObjectId,
      (student.joinedBatches || []) as mongoose.Types.ObjectId[],
      '_id ruleSetId'
    );

    if (activeSessions.length === 0) {
      return sendSuccess(res, { acknowledged: true, sessions: 0 }, 'No active sessions');
    }

    const sessionIds = activeSessions.map((s) => String(s._id));
    const appName = String(activeApp || 'Unknown').trim();
    const agentStatus = ['online', 'idle', 'offline'].includes(status) ? status : 'online';

    // Check if activeApp matches any blocked domains
    const ruleIds = activeSessions.map((s) => s.ruleSetId).filter(Boolean);
    const rules = await Rule.find({ _id: { $in: ruleIds } });
    const blockedDomains = rules.flatMap((r) => r.websites || []).map((w) => w.toLowerCase());
    
    const isViolation = blockedDomains.some((d) => d && appName.toLowerCase().includes(d));
    const engagementScore = isViolation ? 10 : agentStatus === 'online' ? 85 : agentStatus === 'idle' ? 50 : 0;

    emitStudentTelemetry(sessionIds, {
      studentId: String(student._id),
      studentName: student.name || 'Unknown',
      sapId: student.sapId || sapId,
      activeApp: appName,
      status: agentStatus,
      engagementScore,
      isViolation,
      lastSeen: now.toISOString(),
    });

    return sendSuccess(res, {
      acknowledged: true,
      sessions: sessionIds.length,
    }, 'Heartbeat received');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to process heartbeat', 500);
  }
};
