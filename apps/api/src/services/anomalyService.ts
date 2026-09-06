import mongoose from 'mongoose';
import ActivityEvent from '../models/ActivityEvent';
import Session from '../models/Session';
import { getIO } from './socketService';
import {
  detectAnomalies,
  calculateAnomalyMetrics,
  StudentBlockedStats,
} from '../utils/anomalyDetection';

export interface AnomalyCheckResult {
  flagged: string[];
  classAverage: number;
  threshold: number;
}

/**
 * Runs statistical anomaly detection for a specific session over the last 5 minutes.
 * Identifies students with unusually high blocked domain/app attempts.
 *
 * Emits "anomaly_detected" Socket.IO events to the session room for flagged students.
 */
export async function runAnomalyCheck(sessionId: string): Promise<AnomalyCheckResult> {
  if (!mongoose.isValidObjectId(sessionId)) {
    return { flagged: [], classAverage: 0, threshold: 0 };
  }

  const sessionObjId = new mongoose.Types.ObjectId(sessionId);
  const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);

  // 1. Fetch the session to include all joined students in the baseline
  const session = await Session.findById(sessionObjId).select('joinedStudentIds');
  const studentMap = new Map<string, number>();

  if (session?.joinedStudentIds && Array.isArray(session.joinedStudentIds)) {
    for (const sId of session.joinedStudentIds) {
      studentMap.set(sId.toString(), 0);
    }
  }

  // Include any student who had any activity in this session in the last 5 minutes
  const activeStudents = await ActivityEvent.distinct('studentId', {
    sessionId: sessionObjId,
    startedAt: { $gte: fiveMinutesAgo },
  });
  for (const sId of activeStudents) {
    if (!studentMap.has(sId.toString())) {
      studentMap.set(sId.toString(), 0);
    }
  }

  // Aggregate ActivityEvent: group by studentId, count where status="BLOCKED" in last 5 minutes
  const blockedAggregation = await ActivityEvent.aggregate([
    {
      $match: {
        sessionId: sessionObjId,
        status: 'BLOCKED',
        startedAt: { $gte: fiveMinutesAgo },
      },
    },
    {
      $group: {
        _id: '$studentId',
        blockedAttempts: { $sum: 1 },
      },
    },
  ]);

  for (const item of blockedAggregation) {
    studentMap.set(item._id.toString(), item.blockedAttempts);
  }

  const studentStats: StudentBlockedStats[] = Array.from(studentMap.entries()).map(
    ([studentId, blockedAttempts]) => ({
      studentId,
      blockedAttempts,
    })
  );

  // 2. Call detectAnomalies(studentStats)
  const flagged = detectAnomalies(studentStats);
  const { mean, threshold } = calculateAnomalyMetrics(studentStats);
  const classAverage = Number(mean.toFixed(2));
  const roundedThreshold = Number(threshold.toFixed(2));

  // 3. For each flagged studentId, emit via Socket.IO and log to console
  const io = getIO();
  const detectedAt = new Date().toISOString();

  for (const studentId of flagged) {
    const blockedAttempts = studentMap.get(studentId) || 0;
    const severity = blockedAttempts > threshold * 1.5 ? 'HIGH' : 'MEDIUM';

    if (io) {
      io.to(sessionId).emit('anomaly_detected', {
        studentId,
        blockedAttempts,
        classAverage,
        threshold: roundedThreshold,
        detectedAt,
        severity,
      });
    }

    // 4. Log to console: "[ANOMALY] Student {id} flagged — {attempts} attempts vs avg {mean}"
    console.log(
      `[ANOMALY] Student ${studentId} flagged — ${blockedAttempts} attempts vs avg ${classAverage}`
    );
  }

  return {
    flagged,
    classAverage,
    threshold: roundedThreshold,
  };
}
