import mongoose from 'mongoose';
import Session from '../models/Session';
import Batch from '../models/Batch';
import ActivityEvent from '../models/ActivityEvent';
import { calculateAttentionScore } from './attentionScore';
import { detectAnomalies } from './anomalyDetection';
import { SessionSummaryInput } from './geminiSummary';

function formatWindowTime(d: Date): string {
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Aggregates post-session telemetry data from ActivityEvent and Session models
 * to provide statistical context for AI summary generation.
 */
export async function aggregateSessionData(sessionId: string): Promise<SessionSummaryInput> {
  const sessionObjId = new mongoose.Types.ObjectId(sessionId);

  // 1. Fetch Session details
  const session = await Session.findById(sessionObjId).select(
    'title startTime endTime batchIds joinedStudentIds'
  );

  const sessionTitle = session?.title || 'Classroom Session';
  let duration = 60;
  if (session?.startTime && session?.endTime) {
    const diffMin = Math.round(
      (new Date(session.endTime).getTime() - new Date(session.startTime).getTime()) / 60000
    );
    duration = Math.max(1, diffMin);
  }

  // 2. Per-student attention score proxy & classification
  const studentAgg = await ActivityEvent.aggregate([
    { $match: { sessionId: sessionObjId } },
    {
      $group: {
        _id: '$studentId',
        totalEvents: { $sum: 1 },
        blockedAttempts: {
          $sum: { $cond: [{ $eq: ['$status', 'BLOCKED'] }, 1, 0] },
        },
        events: {
          $push: {
            status: '$status',
            application: '$application',
            startedAt: '$startedAt',
          },
        },
      },
    },
  ]);

  const studentMap = new Map<
    string,
    { blockedAttempts: number; events: any[]; score: number }
  >();

  // Attendance and enrollment do not imply that the agent observed activity.
  const rosterIds = new Set<string>((session?.joinedStudentIds || []).map((id) => id.toString()));
  if (session?.batchIds?.length) {
    const batches = await Batch.find({ _id: { $in: session.batchIds } }).select('students').lean();
    for (const batch of batches) {
      for (const studentId of batch.students || []) rosterIds.add(studentId.toString());
    }
  }

  for (const s of studentAgg) {
    const sId = s._id.toString();
    rosterIds.add(sId);
    const score = calculateAttentionScore(s.events);
    studentMap.set(sId, {
      blockedAttempts: s.blockedAttempts || 0,
      events: s.events,
      score,
    });
  }

  let focusedCount = 0;
  let moderateCount = 0;
  let distractedCount = 0;
  let totalBlockedAttempts = 0;

  for (const [, s] of studentMap.entries()) {
    totalBlockedAttempts += s.blockedAttempts;
    if (s.score >= 70) {
      focusedCount++;
    } else if (s.score >= 40) {
      moderateCount++;
    } else {
      distractedCount++;
    }
  }

  const observedStudents = studentMap.size;
  const totalStudents = rosterIds.size;
  const unobservedStudents = Math.max(0, totalStudents - observedStudents);

  // 3. Top blocked domains (limit 3)
  const topBlockedDomainsAgg = await ActivityEvent.aggregate([
    {
      $match: {
        sessionId: sessionObjId,
        status: 'BLOCKED',
        domain: { $exists: true, $ne: null },
      },
    },
    {
      $group: {
        _id: '$domain',
        attempts: { $sum: 1 },
      },
    },
    { $sort: { attempts: -1 } },
    { $limit: 3 },
    {
      $project: {
        _id: 0,
        domain: '$_id',
        attempts: 1,
      },
    },
  ]);

  const topBlockedDomains: { domain: string; attempts: number }[] = topBlockedDomainsAgg.map(
    (d: any) => ({
      domain: String(d.domain),
      attempts: Number(d.attempts),
    })
  );

  // 4. Top blocked apps (limit 3)
  const topBlockedAppsAgg = await ActivityEvent.aggregate([
    {
      $match: {
        sessionId: sessionObjId,
        status: 'BLOCKED',
        application: { $exists: true, $ne: null },
      },
    },
    {
      $group: {
        _id: '$application',
        count: { $sum: 1 },
      },
    },
    { $sort: { count: -1 } },
    { $limit: 3 },
    {
      $project: {
        _id: 0,
        app: '$_id',
        count: 1,
      },
    },
  ]);

  const topBlockedApps: { app: string; count: number }[] = topBlockedAppsAgg.map((a: any) => ({
    app: String(a.app),
    count: Number(a.count),
  }));

  // 5. Peak distraction window (5-minute time bucket with most blocked events)
  let peakDistractionWindow = 'None recorded';
  const blockedBuckets = await ActivityEvent.aggregate([
    {
      $match: {
        sessionId: sessionObjId,
        status: 'BLOCKED',
      },
    },
    {
      $group: {
        _id: {
          $toDate: {
            $subtract: [
              { $toLong: '$startedAt' },
              { $mod: [{ $toLong: '$startedAt' }, 5 * 60 * 1000] },
            ],
          },
        },
        count: { $sum: 1 },
      },
    },
    { $sort: { count: -1 } },
    { $limit: 1 },
  ]);

  if (blockedBuckets.length > 0 && blockedBuckets[0]._id) {
    const bucketStart = new Date(blockedBuckets[0]._id);
    const bucketEnd = new Date(bucketStart.getTime() + 5 * 60 * 1000);
    peakDistractionWindow = `${formatWindowTime(bucketStart)} - ${formatWindowTime(bucketEnd)}`;
  }

  // 6. Anomalous students calculation
  const studentBlockedStats = Array.from(studentMap.entries()).map(([studentId, data]) => ({
    studentId,
    blockedAttempts: data.blockedAttempts,
  }));

  const flagged = detectAnomalies(studentBlockedStats);
  const anomalousStudents = flagged.length;

  return {
    sessionTitle,
    duration,
    totalStudents,
    observedStudents,
    unobservedStudents,
    focusedCount,
    moderateCount,
    distractedCount,
    totalBlockedAttempts,
    topBlockedDomains,
    topBlockedApps,
    peakDistractionWindow,
    anomalousStudents,
  };
}
