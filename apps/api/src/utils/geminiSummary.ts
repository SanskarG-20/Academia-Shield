import { GoogleGenerativeAI } from '@google/generative-ai';

export interface SessionSummaryInput {
  sessionTitle: string;
  duration: number; // minutes
  totalStudents: number;
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
  const topDomains =
    data.topBlockedDomains.length > 0
      ? data.topBlockedDomains.map((d) => d.domain).join(', ')
      : 'no major off-task sites';

  const anomalyText =
    data.anomalousStudents > 0
      ? ` Note that ${data.anomalousStudents} student(s) exhibited anomalous distraction levels requiring proactive review.`
      : '';

  return `During the ${data.duration}-minute session "${data.sessionTitle}", ${data.focusedCount} of ${data.totalStudents} students maintained high focus, while ${data.moderateCount} were moderately attentive and ${data.distractedCount} were frequently distracted. A total of ${data.totalBlockedAttempts} blocked attempts were recorded, with peak distractions occurring around ${data.peakDistractionWindow || 'mid-session'} primarily directed towards ${topDomains}.${anomalyText} It is recommended to reinforce activity expectations during peak intervals and review blocked rule lists for emerging distractions.`;
}

/**
 * Generates an AI-powered post-session summary using Gemini 1.5 Flash.
 * Returns a concise 3-4 sentence professional summary.
 */
export async function generateSessionSummary(data: SessionSummaryInput): Promise<string> {
  const topDomainsStr =
    data.topBlockedDomains.length > 0
      ? data.topBlockedDomains.map((d) => `${d.domain} (${d.attempts} attempts)`).join(', ')
      : 'None';

  const prompt = `You are an academic analytics assistant for a classroom focus management system.
Generate a concise, professional post-session report for a professor.

Session: ${data.sessionTitle}
Duration: ${data.duration} minutes
Students: ${data.totalStudents} total — ${data.focusedCount} focused, ${data.moderateCount} moderate, ${data.distractedCount} distracted
Blocked attempts: ${data.totalBlockedAttempts} total
Top distractions: ${topDomainsStr}
Peak distraction window: ${data.peakDistractionWindow || 'None recorded'}
Flagged students: ${data.anomalousStudents}

Write a 3-4 sentence summary that:
1. States overall class focus level
2. Highlights peak distraction time and top distractions
3. Notes any flagged students (without naming them)
4. Gives one actionable recommendation for the professor

Be direct and professional. No bullet points. Plain paragraph only.`;

  try {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.warn('[Gemini] GEMINI_API_KEY not configured. Generating rule-based summary.');
      return generateFallbackSummary(data);
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });

    const result = await model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();

    return text && text.trim().length > 0 ? text.trim() : generateFallbackSummary(data);
  } catch (error: any) {
    console.error('[Gemini] Error generating session summary:', error?.message || error);
    return generateFallbackSummary(data);
  }
}
