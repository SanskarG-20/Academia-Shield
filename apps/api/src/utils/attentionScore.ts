import { IActivityEvent } from '../models/ActivityEvent';

/**
 * Academic / productivity applications that do NOT penalize the score.
 * Matched case-insensitively against the `application` field.
 */
const ACADEMIC_APPS = [
  'chrome', 'firefox', 'edge', 'brave', 'opera',
  'code', 'visual studio',
  'word', 'excel', 'powerpoint', 'onenote',
  'notepad', 'notepad++', 'sublime',
  'teams', 'zoom', 'meet',
  'terminal', 'cmd', 'powershell',
  'explorer', 'file explorer',
];

/**
 * Calculate a real-time attention score (0–100) for a single student
 * based on their recent activity window (typically the last 60 seconds).
 *
 * Deductions:
 *   -15  per BLOCKED event (attempted violation)
 *   -10  per non-academic app focus switch
 *    -5  per idle gap > 2 minutes between consecutive events
 */
export function calculateAttentionScore(
  recentEvents: Pick<IActivityEvent, 'status' | 'application' | 'startedAt'>[],
  _sessionRuleSet: { blockedDomains: string[]; blockedApps: string[] } = { blockedDomains: [], blockedApps: [] },
): number {
  if (recentEvents.length === 0) return 100;

  let score = 100;

  // --- Blocked-attempt penalty ---
  const blockedAttempts = recentEvents.filter((e) => e.status === 'BLOCKED').length;
  score -= blockedAttempts * 15;

  // --- Non-academic app switches penalty ---
  const nonAcademicSwitches = recentEvents.filter((e) => {
    if (!e.application) return false;
    const appLower = e.application.toLowerCase();
    return !ACADEMIC_APPS.some((a) => appLower.includes(a));
  }).length;
  score -= nonAcademicSwitches * 10;

  // --- Idle-gap penalty (gaps > 120 s between events) ---
  const sorted = [...recentEvents].sort(
    (a, b) => new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime(),
  );

  for (let i = 1; i < sorted.length; i++) {
    const prev = new Date(sorted[i - 1].startedAt).getTime();
    const curr = new Date(sorted[i].startedAt).getTime();
    if (curr - prev > 120_000) {
      score -= 5;
    }
  }

  return Math.max(0, Math.min(100, score));
}

/**
 * Human-readable label for a given attention score.
 */
export function getScoreLabel(score: number): 'Focused' | 'Moderate' | 'Distracted' {
  if (score >= 70) return 'Focused';
  if (score >= 40) return 'Moderate';
  return 'Distracted';
}

/**
 * Hex color mapped to attention score tier.
 */
export function getScoreColor(score: number): string {
  if (score >= 70) return '#10b981'; // green
  if (score >= 40) return '#f59e0b'; // amber
  return '#ef4444';                  // red
}
