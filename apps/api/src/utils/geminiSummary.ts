import { GoogleGenerativeAI } from '@google/generative-ai';

export interface SessionSummaryInput {
  sessionTitle: string;
  duration: number; // minutes
  totalStudents: number;
  observedStudents: number;
  unobservedStudents: number;
  focusedCount: number; // avg score >= 70
  moderateCount: number; // avg score 40-69
  distractedCount: number; // avg score < 40
  totalBlockedAttempts: number;
  topBlockedDomains: { domain: string; attempts: number }[]; // top 3
  topBlockedApps: { app: string; count: number }[]; // top 3
  peakDistractionWindow: string; // e.g. "10:23 AM - 10:31 AM"
  anomalousStudents: number;
}

/**
 * Fallback summary when Gemini API is unreachable or key is missing.
 */
function generateFallbackSummary(data: SessionSummaryInput): string {
  if (data.observedStudents === 0) {
    return `During the ${data.duration}-minute session "${data.sessionTitle}", no agent activity was recorded for the ${data.totalStudents} enrolled or attending student(s). No conclusions about student focus can be drawn from this session. Verify device enrollment and connectivity before interpreting the activity report.`;
  }
  const topDomains =
    data.topBlockedDomains.length > 0
      ? data.topBlockedDomains.map((d) => d.domain).join(', ')
      : 'none recorded';

  const anomalyText =
    data.anomalousStudents > 0
      ? ` Note that ${data.anomalousStudents} student(s) exhibited anomalous distraction levels requiring proactive review.`
      : '';

  const blockedText = data.totalBlockedAttempts > 0
    ? `A total of ${data.totalBlockedAttempts} blocked attempts were recorded, primarily involving ${topDomains}, with the peak around ${data.peakDistractionWindow}.`
    : 'No blocked attempts were recorded.';
  return `During the ${data.duration}-minute session "${data.sessionTitle}", agent activity was recorded for ${data.observedStudents} of ${data.totalStudents} student(s); ${data.unobservedStudents} had no activity data. Among observed students, ${data.focusedCount} had high attention scores, ${data.moderateCount} moderate scores, and ${data.distractedCount} low scores. ${blockedText}${anomalyText} Review device coverage before drawing conclusions about students without activity data.`;
}

/**
 * Generates an AI-powered post-session summary using the configured Gemini model.
 * Returns a concise 3-4 sentence professional summary.
 */
export async function generateSessionSummary(data: SessionSummaryInput): Promise<string> {
  // With no telemetry, a factual coverage statement is safer than a model inference.
  if (data.observedStudents === 0) return generateFallbackSummary(data);
  const topDomainsStr =
    data.topBlockedDomains.length > 0
      ? data.topBlockedDomains.map((d) => `${d.domain} (${d.attempts} attempts)`).join(', ')
      : 'None';

  const prompt = `You are an academic analytics assistant for a classroom focus management system.
Generate a concise, professional post-session report for a professor.

Session: ${data.sessionTitle}
Duration: ${data.duration} minutes
Students: ${data.totalStudents} enrolled or attending; ${data.observedStudents} with agent activity; ${data.unobservedStudents} without activity data
Among observed students only: ${data.focusedCount} high attention scores, ${data.moderateCount} moderate, ${data.distractedCount} low
Blocked attempts: ${data.totalBlockedAttempts} total
Top distractions: ${topDomainsStr}
Peak distraction window: ${data.peakDistractionWindow || 'None recorded'}
Flagged students: ${data.anomalousStudents}

Write a 3-4 sentence summary that:
1. Clearly states how many students had activity data and that students without activity data cannot be assessed
2. Describes attention scores only for observed students; these scores are proxies, not proof of focus
3. Mentions a peak time or top distraction only if one was recorded
4. Notes flagged students if any, without naming them, and gives one actionable recommendation

If zero students had activity data, explicitly say no focus conclusion can be drawn. Do not invent events, blocked attempts, or distractions.

Be direct and professional. No bullet points. Plain paragraph only.`;

  try {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.warn('[Gemini] GEMINI_API_KEY not configured. Generating rule-based summary.');
      return generateFallbackSummary(data);
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: process.env.GEMINI_MODEL || 'gemini-3.5-flash-lite' });

    const result = await model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();

    return text && text.trim().length > 0 ? text.trim() : generateFallbackSummary(data);
  } catch {
    // SDK errors can contain request URLs; do not risk logging the API key.
    console.error('[Gemini] Summary generation failed; using rule-based fallback.');
    return generateFallbackSummary(data);
  }
}
