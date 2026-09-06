export interface StudentBlockedStats {
  studentId: string;
  blockedAttempts: number;
}

export interface AnomalyMetrics {
  mean: number;
  variance: number;
  std: number;
  threshold: number;
}

/**
 * Calculates mean, variance, standard deviation, and threshold (mean + 2*std)
 * for a list of student blocked attempt counts.
 */
export function calculateAnomalyMetrics(studentStats: StudentBlockedStats[]): AnomalyMetrics {
  if (studentStats.length === 0) {
    return { mean: 0, variance: 0, std: 0, threshold: 0 };
  }

  const values = studentStats.map((s) => s.blockedAttempts);
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
  const variance =
    values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
  const std = Math.sqrt(variance);
  const threshold = mean + 2 * std;

  return { mean, variance, std, threshold };
}

/**
 * Detects anomalous students whose blocked attempts exceed (mean + 2*std)
 * with a minimum sample size of 3 and a minimum blocked count of 3.
 *
 * @param studentStats Array of student objects with studentId and blockedAttempts
 * @returns Array of anomalous studentIds
 */
export function detectAnomalies(
  studentStats: { studentId: string; blockedAttempts: number }[]
): string[] {
  if (studentStats.length < 3) return []; // need minimum sample size

  const values = studentStats.map((s) => s.blockedAttempts);
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
  const variance =
    values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
  const std = Math.sqrt(variance);

  const threshold = mean + 2 * std;

  return studentStats
    .filter((s) => s.blockedAttempts > threshold && s.blockedAttempts > 3)
    .map((s) => s.studentId);
}
