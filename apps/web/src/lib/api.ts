import { Batch, LogEntry, RuleSet, Session, UserProfile, ActivityEvent, ActivitySummary } from '../types';

// Get API URL from environment or use localhost for development
const API_URL = import.meta.env.VITE_API_URL;
export const BASE_URL = API_URL || 'http://localhost:5000';

if (!API_URL && typeof window !== 'undefined') {
  console.warn('[api] VITE_API_URL not set, using localhost');
}

type ApiEnvelope<T> = {
  success: boolean;
  data: T;
  message: string;
};

type StudentVerifyResponse = {
  requiresProfileSetup?: boolean;
  sapId?: string;
  email?: string;
  user?: UserProfile;
  token: string;
};

type AgentConfig = {
  active: boolean;
  blockedDomains: string[];
  blockedApps: string[];
  blocking_active: boolean;
  domains: string[];
  apps: string[];
  server_time: string;
  active_sessions: { id: string; title: string; ends_at: string }[];
  test_mode?: boolean;
  device_authorized?: boolean;
};

function normalizeAgentConfig(config: any): AgentConfig {
  const active = Boolean(config?.active ?? config?.blocking_active ?? false);
  const blockedDomains = Array.isArray(config?.blockedDomains)
    ? config.blockedDomains.map(String)
    : Array.isArray(config?.domains)
      ? config.domains.map(String)
      : [];
  const blockedApps = Array.isArray(config?.blockedApps)
    ? config.blockedApps.map(String)
    : Array.isArray(config?.apps)
      ? config.apps.map(String)
      : [];

  return {
    active,
    blockedDomains,
    blockedApps,
    blocking_active: active,
    domains: blockedDomains,
    apps: blockedApps,
    server_time: String(config?.server_time || ''),
    active_sessions: Array.isArray(config?.active_sessions)
      ? config.active_sessions.map((item: any) => ({
          id: String(item?.id || item?._id || ''),
          title: String(item?.title || 'Active Session'),
          ends_at: String(item?.ends_at || ''),
        }))
      : [],
    test_mode: Boolean(config?.test_mode),
    device_authorized: config?.device_authorized ?? true,
  };
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function normalizeId<T extends { _id?: string; id?: string }>(item: T): T & { _id: string } {
  return {
    ...item,
    _id: String(item._id || item.id),
  } as T & { _id: string };
}

function normalizeSession(session: any): Session {
  return {
    ...normalizeId(session),
    batchIds: Array.isArray(session.batchIds) ? session.batchIds.map(String) : [],
  } as Session;
}

function normalizeRule(rule: any): RuleSet {
  return normalizeId(rule) as RuleSet;
}

function normalizeBatch(batch: any): Batch {
  return {
    ...normalizeId(batch),
    students: Array.isArray(batch.students)
      ? batch.students.map((student: any) => normalizeId(student))
      : [],
  } as Batch;
}

function normalizeLog(log: any): LogEntry {
  return normalizeId(log) as LogEntry;
}

function setAuthState(
  token: string,
  role: 'student' | 'student_temp' | 'professor',
  profile?: Partial<UserProfile>
) {
  localStorage.setItem('token', token);
  localStorage.setItem('isAuthenticated', 'true');
  localStorage.setItem('userRole', role === 'professor' ? 'professor' : 'student');

  if (profile?.name) {
    localStorage.setItem('userName', profile.name);
  }

  if (profile?.email) {
    localStorage.setItem('userEmail', profile.email);
  }

  if (role === 'professor' && profile) {
    localStorage.setItem('professorProfile', JSON.stringify(profile));
  }

  if (role !== 'professor' && profile) {
    localStorage.setItem('studentProfile', JSON.stringify(profile));
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    localStorage.clear();
    window.location.hash = '/select-user';
    throw new Error('Session expired. Please log in again.');
  }

  const body = await res.json().catch(() => null);

  if (!res.ok) {
    const message = body?.message || `HTTP ${res.status}`;
    throw new Error(message);
  }

  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const envelope = body as ApiEnvelope<T>;
    if (!envelope.success) {
      throw new Error(envelope.message || 'Request failed');
    }
    return envelope.data;
  }

  return body as T;
}

// AUTH
export async function professorLogin(email: string, password: string) {
  const data = await handleResponse<{ requiresProfileSetup?: boolean; user: UserProfile; token: string }>(
    await fetch(`${BASE_URL}/api/auth/professor/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  );

  setAuthState(data.token, 'professor', data.user);
  return data;
}

export async function requestStudentOtp(sapId: string) {
  return handleResponse<{ sapId: string; mockOtp?: string; otpMode?: 'email' | 'mock' }>(
    await fetch(`${BASE_URL}/api/auth/student/request-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sapId }),
    })
  );
}

export async function verifyStudentOtp(sapId: string, otp: string) {
  const data = await handleResponse<StudentVerifyResponse>(
    await fetch(`${BASE_URL}/api/auth/student/verify-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sapId, otp }),
    })
  );

  if (data.requiresProfileSetup) {
    setAuthState(data.token, 'student_temp', {
      name: 'Student User',
      email: data.email || '',
    });
    localStorage.setItem('tempSapId', sapId);
    return data;
  }

  if (data.user) {
    setAuthState(data.token, 'student', data.user);
  }

  return data;
}

export async function createStudentProfile(payload: {
  sapId: string;
  name: string;
  department: string;
  rollNumber: string;
  year: string;
}) {
  const data = await handleResponse<{ user: UserProfile; token: string }>(
    await fetch(`${BASE_URL}/api/auth/student/profile`, {
      method: 'POST',
      // Carries the `student_temp` token from verifyStudentOtp — the API derives the
      // SAP ID from it rather than trusting the body.
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );

  setAuthState(data.token, 'student', data.user);
  localStorage.removeItem('tempSapId');
  localStorage.removeItem('tempPhoneNumber');
  localStorage.removeItem('tempMockOtp');
  return data;
}

export async function getMe(): Promise<UserProfile> {
  const profile = await handleResponse<UserProfile>(
    await fetch(`${BASE_URL}/api/auth/me`, {
      headers: authHeaders(),
    })
  );

  return normalizeId(profile) as UserProfile;
}

export async function updateMe(payload: Record<string, any>): Promise<UserProfile> {
  const profile = await handleResponse<UserProfile>(
    await fetch(`${BASE_URL}/api/auth/me`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );

  const normalizedProfile = normalizeId(profile) as UserProfile;

  if (normalizedProfile.role === 'professor') {
    localStorage.setItem('professorProfile', JSON.stringify(normalizedProfile));
  } else {
    localStorage.setItem('studentProfile', JSON.stringify(normalizedProfile));
  }

  localStorage.setItem('userName', normalizedProfile.name);
  localStorage.setItem('userEmail', normalizedProfile.email);

  return normalizedProfile;
}

// RULES
export async function getRules(): Promise<RuleSet[]> {
  const rules = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/rules`, { headers: authHeaders() })
  );
  return rules.map(normalizeRule);
}

export async function createRule(
  name: string,
  mode: string,
  websites: string[],
  applications: string[]
) {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/rules`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ name, mode, websites, applications }),
    })
  );
  return normalizeRule(rule);
}

export async function updateRule(
  id: string,
  payload: { name: string; mode: string; websites: string[]; applications: string[] }
) {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/rules/${id}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  return normalizeRule(rule);
}

export async function deleteRule(id: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/rules/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

// BATCHES
export async function getBatches(): Promise<Batch[]> {
  const batches = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/batches`, {
      headers: authHeaders(),
    })
  );
  return batches.map(normalizeBatch);
}

export async function getMyBatches(): Promise<Batch[]> {
  const batches = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/batches/student/my`, {
      headers: authHeaders(),
    })
  );
  return batches.map(normalizeBatch);
}

export async function getBatchById(id: string): Promise<Batch> {
  const batch = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/batches/${id}`, {
      headers: authHeaders(),
    })
  );
  return normalizeBatch(batch);
}

export async function createBatch(payload: {
  name: string;
  code: string;
  department: string;
  year: string;
}): Promise<Batch> {
  const batch = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/batches`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  return normalizeBatch(batch);
}

export async function joinBatch(code: string): Promise<Batch> {
  const batch = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/batches/join`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ code }),
    })
  );
  return normalizeBatch(batch);
}

// SESSIONS
export async function getSessions(): Promise<Session[]> {
  const sessions = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/sessions`, { headers: authHeaders() })
  );
  return sessions.map(normalizeSession);
}

export async function createSession(data: {
  title: string;
  course: string;
  type: string;
  startTime: string;
  endTime: string;
  ruleSetId: string;
  batchIds: string[];
  joinMode: 'auto' | 'opt-in';
}) {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/sessions`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    })
  );

  return normalizeSession(session);
}

export async function updateSessionStatus(id: string, status: string) {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/sessions/${id}/status`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ status }),
    })
  );

  return normalizeSession(session);
}

export async function joinSession(id: string) {
  return handleResponse<{ sessionId: string; status: string; joined: boolean }>(
    await fetch(`${BASE_URL}/api/sessions/${id}/join`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export type SessionCoverage = {
  sessionId: string;
  freshMs: number;
  summary: { total: number; active: number; enrolled_silent: number; not_enrolled: number; joined: number };
  students: { studentId: string; name: string; sapId: string; joined: boolean; status: 'active' | 'enrolled_silent' | 'not_enrolled' }[];
};

export async function getSessionCoverage(id: string): Promise<SessionCoverage> {
  return handleResponse<SessionCoverage>(
    await fetch(`${BASE_URL}/api/sessions/${encodeURIComponent(id)}/coverage`, { headers: authHeaders() })
  );
}

export async function deleteSession(id: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/sessions/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

// LOGS
export async function getLogs(sessionId?: string): Promise<LogEntry[]> {
  const suffix = sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : '';
  const logs = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/logs${suffix}`, {
      headers: authHeaders(),
    })
  );
  return logs.map(normalizeLog);
}

export async function getSessionLogs(sessionId: string): Promise<LogEntry[]> {
  const logs = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/logs/${sessionId}`, {
      headers: authHeaders(),
    })
  );
  return logs.map(normalizeLog);
}

// AGENT CONFIG
export async function getAgentConfig() {
  // Browser overview; device policy is only available to authenticated local agents.
  const config = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/agent/overview`, {
      headers: authHeaders(),
    })
  );
  return normalizeAgentConfig(config);
}

export async function issueEnrollmentClaim(): Promise<{ claim: string; expiresAt: string }> {
  return handleResponse(
    await fetch(`${BASE_URL}/api/agent/enrollment-claims`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export type EnrolledDevice = { _id: string; createdAt: string; lastSeenAt?: string; revokedAt?: string };

export async function getEnrolledDevices(): Promise<EnrolledDevice[]> {
  return handleResponse(await fetch(`${BASE_URL}/api/agent/devices`, { headers: authHeaders() }));
}

export async function revokeEnrolledDevice(id: string): Promise<void> {
  await handleResponse(await fetch(`${BASE_URL}/api/agent/devices/${id}`, { method: 'DELETE', headers: authHeaders() }));
}

// STUDENT ACTIVITY
export async function getStudentActivity(
  studentId: string,
  sessionId?: string,
  limit = 200,
  offset = 0
): Promise<ActivityEvent[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (sessionId) params.set('sessionId', sessionId);
  return handleResponse<ActivityEvent[]>(
    await fetch(`${BASE_URL}/api/activity/student/${studentId}?${params}`, {
      headers: authHeaders(),
    })
  );
}

export async function getStudentActivitySummary(
  studentId: string,
  sessionId?: string
): Promise<ActivitySummary> {
  const params = sessionId ? `?sessionId=${sessionId}` : '';
  return handleResponse<ActivitySummary>(
    await fetch(`${BASE_URL}/api/activity/student/${studentId}/summary${params}`, {
      headers: authHeaders(),
    })
  );
}

// ANOMALIES
export interface AnomalyCheckResponse {
  flagged: string[];
  classAverage: number;
  threshold: number;
}

export async function checkSessionAnomalies(sessionId: string): Promise<AnomalyCheckResponse> {
  return handleResponse<AnomalyCheckResponse>(
    await fetch(`${BASE_URL}/api/sessions/${sessionId}/check-anomalies`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

// SESSION SUMMARY
export async function getSessionSummary(
  id: string
): Promise<{ aiSummary: string; generatedAt: string; stats?: any }> {
  return handleResponse<{ aiSummary: string; generatedAt: string; stats?: any }>(
    await fetch(`${BASE_URL}/api/sessions/${id}/summary`, {
      headers: authHeaders(),
    })
  );
}


