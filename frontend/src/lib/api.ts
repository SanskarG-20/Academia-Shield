import { Batch, LiveMonitorData, LogEntry, RuleSet, Session, UserProfile, WebsiteRule, ApplicationRule, DevicePolicyRequirement } from '../types';

const API_URL = import.meta.env.VITE_API_URL;
export const BASE_URL = API_URL || '';
export const AUTH_STATE_CHANGED_EVENT = 'academia-shield:auth-state-changed';

const AUTH_REQUEST_HEADER = 'X-Academia-Auth-Request';
let refreshRequest: Promise<{ access_token: string; refresh_token: string; user: any }> | null = null;

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('access_token') || localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    // Lets the client retry protected requests after refreshing an expired token.
    [AUTH_REQUEST_HEADER]: 'true',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function normalizeId<T extends { _id?: string; id?: string }>(item: T): T & { _id: string } {
  return {
    ...item,
    _id: String(item._id || item.id),
  } as T & { _id: string };
}

// The FastAPI service returns conventional snake_case payloads while the
// existing React views use the original camelCase model. Keep that translation
// at the API boundary so components have one stable contract.
function normalizeUser(item: any): UserProfile {
  return normalizeId({
    ...item,
    name: item.name ?? item.full_name,
    sapId: item.sapId ?? item.institutional_id,
    department: item.department ?? '',
    createdAt: item.createdAt ?? item.created_at,
  }) as UserProfile;
}

function normalizeBatch(item: any): Batch {
  return normalizeId({
    ...item,
    professorId: item.professorId ?? item.professor_id,
    createdAt: item.createdAt ?? item.created_at,
    students: (item.students ?? []).map((student: any) => normalizeId({
      ...student,
      sapId: student.sapId ?? student.sap_id,
      rollNumber: student.rollNumber ?? student.roll_number,
    })),
  }) as Batch;
}

function parseBatchIds(raw: any): string[] {
  if (Array.isArray(raw)) return raw.map(String);
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      return [raw];
    }
  }
  return [];
}

function normalizeSessionStatus(status: unknown): string {
  switch (String(status ?? '').toLowerCase()) {
    case 'scheduled':
    case 'upcoming':
      return 'Upcoming';
    case 'active':
      return 'Active';
    case 'paused':
    case 'pause':
      return 'Paused';
    case 'ended':
    case 'completed':
      return 'Completed';
    case 'cancelled':
      return 'Cancelled';
    default:
      return String(status ?? 'Upcoming');
  }
}

function normalizeSession(item: any): Session {
  const rawBatchIds = item.batchIds ?? item.batch_ids ?? (item.batch_id ? [item.batch_id] : []);
  return normalizeId({
    ...item,
    description: item.description ?? '',
    startTime: item.startTime ?? item.start_time ?? item.start_at_utc ?? item.start_at,
    endTime: item.endTime ?? item.end_time ?? item.end_at_utc ?? item.end_at,
    startedAt: item.startedAt ?? item.started_at,
    endedAt: item.endedAt ?? item.ended_at,
    course: item.course ?? item.batch_name ?? 'General Class',
    professorName: item.professorName ?? item.professor_name ?? '',
    type: item.type ?? 'Lecture',
    status: normalizeSessionStatus(item.status),
    isJoined: item.isJoined ?? item.is_joined ?? false,
    ruleSetId: item.ruleSetId ?? item.rule_id ?? item.rule_set_id,
    batchIds: parseBatchIds(rawBatchIds),
    professorId: item.professorId ?? item.professor_id,
    violationCount: item.violationCount ?? item.violation_count ?? 0,
    violation_count: item.violationCount ?? item.violation_count ?? 0,
    createdAt: item.createdAt ?? item.created_at,
  }) as Session;
}

function normalizeLog(item: any): LogEntry {
  return normalizeId({
    ...item,
    studentId: item.studentId ?? item.student_id,
    sessionId: item.sessionId ?? item.session_id,
    resource: item.resource ?? item.domain,
    isViolation: item.isViolation ?? item.action === 'Blocked',
  }) as LogEntry;
}

function normalizeRuleSet(item: any): RuleSet {
  const wsRules: WebsiteRule[] = (item.website_rules || []).map((r: any) => ({
    ...r,
    _id: String(r._id || r.id),
    rule_mode: r.rule_mode || (r.is_allowed ? 'allowed' : 'blocked'),
  }));
  const appRules: ApplicationRule[] = (item.application_rules || []).map((r: any) => ({
    ...r,
    _id: String(r._id || r.id),
    rule_mode: r.rule_mode || (r.is_allowed ? 'allowed' : 'blocked'),
  }));
  const devReqs: DevicePolicyRequirement | undefined = item.device_requirements ? {
    ...item.device_requirements,
    _id: String(item.device_requirements._id || item.device_requirements.id || ''),
  } : undefined;

  const allowedWs = item.allowed_websites || wsRules.filter(r => r.rule_mode === 'allowed').map(r => r.domain_pattern);
  const blockedWs = item.blocked_websites || wsRules.filter(r => r.rule_mode === 'blocked').map(r => r.domain_pattern);
  const allowedApps = item.allowed_applications || appRules.filter(r => r.rule_mode === 'allowed').map(r => r.application_name);
  const blockedApps = item.blocked_applications || appRules.filter(r => r.rule_mode === 'blocked').map(r => r.application_name);

  return normalizeId({
    ...item,
    name: item.name || 'Session Policy',
    version: item.version ?? 1,
    status: item.status || 'draft',
    batchId: item.batch_id || item.batchId,
    batch_id: item.batch_id || item.batchId,
    sessionId: item.session_id || item.sessionId,
    session_id: item.session_id || item.sessionId,
    policy_hash: item.policy_hash,
    signature: item.signature,
    allowed_websites: allowedWs,
    blocked_websites: blockedWs,
    allowed_applications: allowedApps,
    blocked_applications: blockedApps,
    websites: blockedWs.length > 0 ? blockedWs : allowedWs,
    applications: blockedApps.length > 0 ? blockedApps : allowedApps,
    mode: item.mode || (allowedWs.length > 0 && blockedWs.length === 0 ? 'Allowlist' : 'Blocklist'),
    website_rules: wsRules,
    application_rules: appRules,
    device_requirements: devReqs,
    createdAt: item.createdAt || item.created_at,
    updatedAt: item.updatedAt || item.updated_at,
  }) as RuleSet;
}

function setAuthState(
  accessToken: string,
  refreshToken: string,
  user?: {
    id?: string;
    email?: string;
    role?: string;
    full_name?: string;
    department?: string;
    institutional_id?: string;
  }
) {
  localStorage.setItem('access_token', accessToken);
  localStorage.setItem('token', accessToken);
  localStorage.setItem('refresh_token', refreshToken);
  localStorage.setItem('isAuthenticated', 'true');
  if (user?.id) localStorage.setItem('userId', user.id);
  if (user?.role) localStorage.setItem('userRole', user.role);
  if (user?.full_name) localStorage.setItem('userName', user.full_name);
  if (user?.email) localStorage.setItem('userEmail', user.email);
  if (user?.department) localStorage.setItem('userDepartment', user.department);
  if (user?.institutional_id) localStorage.setItem('userInstitutionalId', user.institutional_id);
  window.dispatchEvent(new Event(AUTH_STATE_CHANGED_EVENT));
}

export function getCurrentUserId(): string | null {
  const stored = localStorage.getItem('userId');
  if (stored) return stored;
  const token = localStorage.getItem('access_token') || localStorage.getItem('token');
  if (!token) return null;
  try {
    const parts = token.split('.');
    if (parts.length === 3) {
      const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
      return payload.sub || payload.id || null;
    }
  } catch {}
  return null;
}

export function clearAuthState() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('isAuthenticated');
  localStorage.removeItem('userRole');
  localStorage.removeItem('userName');
  localStorage.removeItem('userEmail');
  localStorage.removeItem('userDepartment');
  localStorage.removeItem('userInstitutionalId');
  window.dispatchEvent(new Event(AUTH_STATE_CHANGED_EVENT));
}

function connectionError(): Error {
  return new Error(
    `Unable to reach the API at ${BASE_URL || 'this site'}. Make sure the backend is running and VITE_API_URL is correct.`
  );
}

/**
 * All protected calls in this module use authHeaders(), which marks them here.
 * A 401 is retried once with a rotated access token; concurrent requests share
 * the same refresh operation so one expired token cannot revoke another's
 * refresh token.
 */
async function fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await globalThis.fetch(input, init);
  } catch (error) {
    if (error instanceof TypeError) throw connectionError();
    throw error;
  }

  const headers = new Headers(init?.headers);
  const isProtectedRequest = headers.get(AUTH_REQUEST_HEADER) === 'true';
  if (!isProtectedRequest || response.status !== 401) return response;

  headers.delete(AUTH_REQUEST_HEADER);
  await refreshAuthToken();
  const token = localStorage.getItem('access_token');
  if (!token) throw new Error('Your session has expired. Please sign in again.');
  headers.set('Authorization', `Bearer ${token}`);

  try {
    return await globalThis.fetch(input, { ...init, headers });
  } catch (error) {
    if (error instanceof TypeError) throw connectionError();
    throw error;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);

  if (!res.ok) {
    const detail = body?.detail || body?.message || `Request failed with status ${res.status}`;
    if (typeof detail === 'string') {
      throw new Error(detail);
    } else if (Array.isArray(detail)) {
      throw new Error(detail.map(d => d.msg || d.message || JSON.stringify(d)).join(', '));
    }
    throw new Error(JSON.stringify(detail));
  }

  return body as T;
}

// AUTHENTICATION APIs
export async function registerStudent(payload: {
  full_name: string;
  email: string;
  student_id: string;
  department: string;
  password: string;
  confirm_password: string;
  accept_policy: boolean;
}) {
  const data = await handleResponse<{
    access_token: string;
    refresh_token: string;
    user: any;
  }>(
    await fetch(`${BASE_URL}/api/auth/register/student`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  );

  setAuthState(data.access_token, data.refresh_token, data.user);
  return data;
}

export async function registerProfessor(payload: {
  full_name: string;
  email: string;
  employee_id: string;
  department: string;
  password: string;
  confirm_password: string;
  accept_policy: boolean;
}) {
  const data = await handleResponse<{
    access_token: string;
    refresh_token: string;
    user: any;
  }>(
    await fetch(`${BASE_URL}/api/auth/register/professor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  );

  setAuthState(data.access_token, data.refresh_token, data.user);
  return data;
}

export async function login(email_or_id: string, password: string) {
  const data = await handleResponse<{
    access_token: string;
    refresh_token: string;
    user: any;
  }>(
    await fetch(`${BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_or_id, password }),
    })
  );

  setAuthState(data.access_token, data.refresh_token, data.user);
  return data;
}

export async function logout() {
  const refreshToken = localStorage.getItem('refresh_token');
  try {
    await fetch(`${BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch (e) {
    console.warn('Logout API warning:', e);
  } finally {
    clearAuthState();
  }
}

export async function refreshAuthToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) {
    clearAuthState();
    throw new Error('Your session has expired. Please sign in again.');
  }

  if (!refreshRequest) {
    refreshRequest = (async () => {
      const response = await fetch(`${BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      try {
        const data = await handleResponse<{
          access_token: string;
          refresh_token: string;
          user: any;
        }>(response);
        setAuthState(data.access_token, data.refresh_token, data.user);
        return data;
      } catch (error) {
        clearAuthState();
        throw new Error('Your session has expired. Please sign in again.');
      }
    })().finally(() => {
      refreshRequest = null;
    });
  }

  return refreshRequest;
}

export async function getMe(): Promise<UserProfile> {
  const data = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/auth/me`, {
      headers: authHeaders(),
    })
  );
  return normalizeUser(data);
}

export async function updateMe(payload: Record<string, any>): Promise<UserProfile> {
  const data = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/auth/me`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  if (data?.full_name) localStorage.setItem('userName', data.full_name);
  if (data?.email) localStorage.setItem('userEmail', data.email);
  return normalizeUser(data);
}

export async function createStudentProfile(payload: Record<string, any>): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/auth/me`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}

export async function forgotPassword(email: string) {
  return handleResponse<{ message: string }>(
    await fetch(`${BASE_URL}/api/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
  );
}

export async function resetPassword(payload: {
  token: string;
  new_password: string;
  confirm_password: string;
}) {
  return handleResponse<{ message: string }>(
    await fetch(`${BASE_URL}/api/auth/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  );
}

// BATCHES
export async function getBatches(): Promise<Batch[]> {
  const role = localStorage.getItem('userRole');
  const endpoint = role === 'student' ? `${BASE_URL}/api/v1/student/batches` : `${BASE_URL}/api/v1/batches`;
  try {
    const batches = await handleResponse<any[]>(await fetch(endpoint, { headers: authHeaders() }));
    return (batches || []).map(normalizeBatch);
  } catch {
    const fallback = await handleResponse<any[]>(await fetch(`${BASE_URL}/api/batches`, { headers: authHeaders() }));
    return (fallback || []).map(normalizeBatch);
  }
}

export async function getMyBatches(): Promise<Batch[]> {
  return getBatches();
}

export async function getBatchById(id: string): Promise<Batch> {
  const role = localStorage.getItem('userRole');
  const endpoint = role === 'student' ? `${BASE_URL}/api/v1/student/batches/${id}` : `${BASE_URL}/api/v1/batches/${id}`;
  try {
    const data = await handleResponse<any>(await fetch(endpoint, { headers: authHeaders() }));
    return normalizeBatch(data);
  } catch {
    const fallback = await handleResponse<any>(await fetch(`${BASE_URL}/api/batches/${id}`, { headers: authHeaders() }));
    return normalizeBatch(fallback);
  }
}

export async function createBatch(payload: {
  name: string;
  code?: string;
  description?: string;
  department?: string;
  year?: string;
}): Promise<Batch> {
  const batch = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/batches`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  return normalizeBatch(batch);
}

export async function joinBatch(code: string): Promise<any> {
  try {
    return await handleResponse<any>(
      await fetch(`${BASE_URL}/api/v1/student/batches/join`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ batch_code: code }),
      })
    );
  } catch (e) {
    return handleResponse<any>(
      await fetch(`${BASE_URL}/api/batches/join`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ code }),
      })
    );
  }
}

export async function regenerateBatchCode(batchId: string): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/batches/${batchId}/regenerate-code`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export async function getBatchMembers(batchId: string): Promise<any[]> {
  return handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/batches/${batchId}/members`, {
      headers: authHeaders(),
    })
  );
}

export async function removeBatchMember(batchId: string, studentId: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/v1/batches/${batchId}/members/${studentId}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

// BATCH V1 RULE SETS & SESSION POLICIES
export async function getBatchRuleSets(batchId: string): Promise<RuleSet[]> {
  const rules = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/batches/${batchId}/rule-sets`, { headers: authHeaders() })
  );
  return (rules || []).map(normalizeRuleSet);
}

export async function createBatchRuleSet(
  batchId: string,
  payloadOrName: string | { name: string; description?: string; base_rule_set_id?: string }
): Promise<RuleSet> {
  const body = typeof payloadOrName === 'string' ? { name: payloadOrName } : payloadOrName;
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/batches/${batchId}/rule-sets`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    })
  );
  return normalizeRuleSet(rule);
}

export async function getRuleSet(ruleSetId: string): Promise<RuleSet> {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}`, { headers: authHeaders() })
  );
  return normalizeRuleSet(rule);
}

export async function updateRuleSet(ruleSetId: string, payload: { name?: string; description?: string }): Promise<RuleSet> {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  return normalizeRuleSet(rule);
}

export async function publishRuleSet(ruleSetId: string): Promise<RuleSet> {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}/publish`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
  return normalizeRuleSet(rule);
}

export async function revokeRuleSet(ruleSetId: string): Promise<RuleSet> {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}/revoke`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
  return normalizeRuleSet(rule);
}

export async function assignRuleSetToSession(sessionId: string, ruleSetId: string): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/sessions/${sessionId}/assign-rule-set`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ rule_set_id: ruleSetId }),
    })
  );
}

// RULES (COMPATIBILITY & CRUD)
export async function getRules(batchId?: string): Promise<RuleSet[]> {
  const url = batchId && batchId !== 'all'
    ? `${BASE_URL}/api/v1/batches/${batchId}/rule-sets`
    : `${BASE_URL}/api/rules`;
  const rules = await handleResponse<any[]>(
    await fetch(url, { headers: authHeaders() })
  );
  return (rules || []).map(normalizeRuleSet);
}

export async function createRule(
  nameOrPayload: any,
  mode?: string,
  websites?: string[],
  applications?: string[],
  batchId?: string
): Promise<RuleSet> {
  const body = typeof nameOrPayload === 'string'
    ? {
        name: nameOrPayload,
        mode,
        websites,
        applications,
        batch_id: batchId && batchId !== 'all' ? batchId : undefined,
      }
    : nameOrPayload;

  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/rules`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    })
  );
  return normalizeRuleSet(rule);
}

export async function updateRule(
  id: string,
  payload: any
): Promise<RuleSet> {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/rules/${id}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  return normalizeRuleSet(rule);
}

export async function quickUpdateRule(
  ruleId: string,
  payload: { action: 'add' | 'remove'; type: 'website' | 'application'; item: string }
): Promise<RuleSet> {
  const rule = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/rules/${ruleId}/quick-update`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
  return normalizeRuleSet(rule);
}

export async function deleteRule(id: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/rules/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

// STRUCTURED WEBSITE & APP RULES & DEVICE REQUIREMENTS
export async function addWebsiteRule(ruleSetId: string, payload: {
  domain_pattern: string;
  rule_mode: 'allowed' | 'blocked';
  category?: string;
  priority?: number;
  is_enabled?: boolean;
  reason?: string;
}): Promise<WebsiteRule> {
  return handleResponse<WebsiteRule>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}/website-rules`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}

export async function updateWebsiteRule(ruleId: string, payload: Partial<WebsiteRule>): Promise<WebsiteRule> {
  return handleResponse<WebsiteRule>(
    await fetch(`${BASE_URL}/api/v1/website-rules/${ruleId}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}

export async function deleteWebsiteRule(ruleId: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/v1/website-rules/${ruleId}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

export async function addApplicationRule(ruleSetId: string, payload: {
  application_name: string;
  rule_mode: 'allowed' | 'blocked';
  category?: string;
  action?: 'log' | 'warn' | 'close';
  is_enabled?: boolean;
  reason?: string;
}): Promise<ApplicationRule> {
  return handleResponse<ApplicationRule>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}/application-rules`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}

export async function updateApplicationRule(ruleId: string, payload: Partial<ApplicationRule>): Promise<ApplicationRule> {
  return handleResponse<ApplicationRule>(
    await fetch(`${BASE_URL}/api/v1/application-rules/${ruleId}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}

export async function deleteApplicationRule(ruleId: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/v1/application-rules/${ruleId}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

export async function updateDeviceRequirements(ruleSetId: string, payload: Partial<DevicePolicyRequirement>): Promise<DevicePolicyRequirement> {
  return handleResponse<DevicePolicyRequirement>(
    await fetch(`${BASE_URL}/api/v1/rule-sets/${ruleSetId}/device-requirements`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}


// STUDENT BATCH & SESSION V1 ENDPOINTS
export async function getStudentBatches(): Promise<Batch[]> {
  const batches = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/student/batches`, { headers: authHeaders() })
  );
  return (batches || []).map(normalizeBatch);
}

export async function getStudentBatchById(id: string): Promise<Batch> {
  const batch = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/student/batches/${id}`, { headers: authHeaders() })
  );
  return normalizeBatch(batch);
}

export async function getStudentBatchSessions(id: string): Promise<Session[]> {
  const sessions = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/student/batches/${id}/sessions`, { headers: authHeaders() })
  );
  return (sessions || []).map(normalizeSession);
}

export async function getStudentSessions(): Promise<Session[]> {
  const sessions = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/student/sessions`, { headers: authHeaders() })
  );
  return (sessions || []).map(normalizeSession);
}

export async function joinStudentBatch(batch_code: string) {
  return handleResponse<{ message: string; batch: any }>(
    await fetch(`${BASE_URL}/api/v1/student/batches/join`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ batch_code }),
    })
  );
}

// SESSIONS
export async function getSessions(): Promise<Session[]> {
  const sessions = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/sessions`, { headers: authHeaders() })
  );
  return (sessions || []).map(normalizeSession);
}

export async function createSession(data: {
  title: string;
  course: string;
  type?: string;
  start_time?: string;
  end_time?: string;
  rule_id?: string;
  batch_ids?: string[];
  startTime?: string;
  endTime?: string;
  ruleSetId?: string;
  batchIds?: string[];
}) {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/sessions`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        ...data,
        start_time: data.start_time ?? data.startTime,
        end_time: data.end_time ?? data.endTime,
        rule_id: data.rule_id ?? data.ruleSetId,
        batch_ids: data.batch_ids ?? data.batchIds ?? [],
      }),
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

export async function startSession(id: string): Promise<Session> {
  try {
    const session = await handleResponse<any>(
      await fetch(`${BASE_URL}/api/v1/sessions/${id}/start`, {
        method: 'POST',
        headers: authHeaders(),
      })
    );
    return normalizeSession(session);
  } catch {
    return await updateSessionStatus(id, 'active');
  }
}

export async function endSession(id: string): Promise<Session> {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/sessions/${id}/end`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
  return normalizeSession(session);
}

export async function pauseSession(id: string): Promise<Session> {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/sessions/${id}/pause`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
  return normalizeSession(session);
}

export async function resumeSession(id: string): Promise<Session> {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/sessions/${id}/resume`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
  return normalizeSession(session);
}



export async function emergencyStopSession(id: string, reason: string = 'Professor authorized emergency stop'): Promise<Session> {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/sessions/${id}/emergency-stop`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ reason }),
    })
  );
  return normalizeSession(session);
}

export async function cancelSession(id: string): Promise<Session> {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/sessions/${id}/cancel`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
  return normalizeSession(session);
}

export async function joinStudentSession(id: string): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/student/sessions/${id}/join`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export async function leaveStudentSession(id: string): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/student/sessions/${id}/leave`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export async function getStudentSessionDetails(id: string): Promise<Session> {
  const session = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/student/sessions/${id}`, {
      headers: authHeaders(),
    })
  );
  return normalizeSession(session);
}

export async function joinSession(id: string) {
  return joinStudentSession(id);
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
export async function createLog(payload: {
  sessionId?: string;
  type?: string;
  resource?: string;
  details?: string;
  duration?: number;
  engagementScore?: number;
  isViolation?: boolean;
}) {
  const log = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/agent/report`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify([
        {
          domain: payload.resource || 'unknown',
          session_id: payload.sessionId,
          action: payload.isViolation ? 'Blocked' : 'Allowed',
        },
      ]),
    })
  );
  return normalizeId(log);
}

export async function getLogs(sessionId?: string): Promise<LogEntry[]> {
  const suffix = sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : '';
  const logs = await handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/logs${suffix}`, {
      headers: authHeaders(),
    })
  );
  return (logs || []).map(normalizeLog);
}

export async function getSessionLogs(sessionId: string): Promise<LogEntry[]> {
  return getLogs(sessionId);
}

// AGENT CONFIG
export async function getAgentConfig() {
  return handleResponse<any>(await fetch(`${BASE_URL}/api/agent/config`));
}

export async function getProfessorLiveMonitor(sessionId: string): Promise<LiveMonitorData> {
  return handleResponse<LiveMonitorData>(
    await fetch(`${BASE_URL}/api/v1/professor/sessions/${sessionId}/live`, {
      headers: authHeaders(),
    })
  );
}

// AGENT RELEASES & ENROLLMENT
export async function getAgentReleasesLatest(): Promise<{
  latest_version: string;
  releases: {
    windows: {
      platform: string;
      version: string;
      download_url: string;
      sha256: string;
      release_date: string;
      signature: string;
      min_os_version: string;
    };
    macos: {
      platform: string;
      version: string;
      download_url: string;
      sha256: string;
      release_date: string;
      signature: string;
      min_os_version: string;
    };
  };
}> {
  return handleResponse<any>(await fetch(`${BASE_URL}/api/v1/agent/releases/latest`));
}

export async function getAgentReleaseManifest(version: string, platform = 'windows') {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/agent/releases/${encodeURIComponent(version)}/manifest?platform=${encodeURIComponent(platform)}`)
  );
}

export async function generateEnrollmentToken(): Promise<{
  enrollment_token: string;
  expires_at: string;
  student_name: string;
  student_id: string;
  instructions: string;
}> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/agent/enrollment-token`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export async function getMyDeviceStatus(): Promise<{
  is_installed: boolean;
  is_enrolled: boolean;
  is_online: boolean;
  agent_state: string;
  active_session_id?: string | null;
  device?: {
    id: string;
    device_name: string;
    device_identifier: string;
    platform: string;
    platform_version?: string;
    agent_version: string;
    compliance_status: string;
    compliance_level: string;
    policy_delivery_state: string;
    last_seen_at?: string;
    enrolled_at?: string;
  } | null;
  message?: string;
}> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/agent/devices/me`, {
      headers: authHeaders(),
    })
  );
}

export async function getProfessorUnlockRequests(): Promise<any[]> {
  return handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/professor/unlock-requests`, {
      headers: authHeaders(),
    })
  );
}

export async function getStudentUnlockRequests(): Promise<any[]> {
  return handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/student/unlock-requests`, {
      headers: authHeaders(),
    })
  );
}

export async function getSessionUnlockRequests(sessionId: string): Promise<any[]> {
  return handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/sessions/${sessionId}/unlock-requests`, {
      headers: authHeaders(),
    })
  );
}

export async function resolveUnlockRequest(
  sessionId: string,
  requestId: string,
  status: 'approved' | 'rejected' | 'resolved',
  resolutionNotes?: string
): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/sessions/${sessionId}/unlock-requests/${requestId}/resolve`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ status, resolution_notes: resolutionNotes }),
    })
  );
}

export interface LiveEngagementStudent {
  student_id: string;
  student_name: string;
  student_email: string;
  batch_id: string;
  joined: boolean;
  last_window_at?: string | null;
  window_count: number;
  total_academic_seconds: number;
  total_non_academic_seconds: number;
  total_idle_seconds: number;
  total_switches: number;
  total_unauthorized_attempts: number;
  total_blocked_website_attempts: number;
  total_policy_violations: number;
  academic_ratio: number;
  focus_stability_index: number;
  violation_rate_per_hour: number;
  label?: 'High' | 'Medium' | 'Low' | null;
  prediction_available?: boolean;
  prediction_reason?: string | null;
  predicted_engagement?: 'High' | 'Medium' | 'Low' | null;
  confidence?: number | null;
  probability_high?: number | null;
  probability_medium?: number | null;
  probability_low?: number | null;
  model_version?: string | null;
  prediction_type?: 'live' | 'final' | null;
  review_status?: 'preliminary' | 'reviewed' | null;
  latest_prediction_id?: string | null;
  professor_override_label?: string | null;
}

export interface LiveEngagementData {
  session_id: string;
  session_title: string;
  session_status: string;
  is_active: boolean;
  prediction_available: boolean;
  students: LiveEngagementStudent[];
}

export interface MLModelInfo {
  id: string;
  version_tag: string;
  algorithm: string;
  status: 'draft' | 'approved' | 'retired';
  hyperparameters_json?: Record<string, any>;
  metrics_json?: {
    accuracy: number;
    f1_macro: number;
    precision_macro: number;
    recall_macro: number;
    feature_importances?: Record<string, number>;
  };
  artifact_path: string;
  trained_by: string;
  approved_by?: string | null;
  created_at: string;
  approved_at?: string | null;
  retired_at?: string | null;
}

export async function getLiveSessionEngagement(sessionId: string): Promise<LiveEngagementData> {
  return handleResponse<LiveEngagementData>(
    await fetch(`${BASE_URL}/api/v1/professor/sessions/${sessionId}/engagement/live`, {
      headers: authHeaders(),
    })
  );
}

export async function getSessionEngagementHistory(sessionId: string): Promise<any[]> {
  return handleResponse<any[]>(
    await fetch(`${BASE_URL}/api/v1/professor/sessions/${sessionId}/engagement/history`, {
      headers: authHeaders(),
    })
  );
}

export async function reviewEngagementPrediction(
  predictionId: string,
  arg?: 'High' | 'Medium' | 'Low' | { action: 'confirm' | 'override'; override_label?: string; notes?: string }
): Promise<any> {
  let payload: { action: string; override_label?: string; notes?: string };
  if (typeof arg === 'string') {
    payload = { action: 'override', override_label: arg };
  } else if (arg && typeof arg === 'object') {
    payload = arg;
  } else {
    payload = { action: 'confirm' };
  }

  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/professor/engagement/predictions/${predictionId}/review`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    })
  );
}

export async function labelSessionStudentEngagement(
  sessionId: string,
  studentId: string,
  label: 'High' | 'Medium' | 'Low',
  notes?: string
): Promise<any> {
  return handleResponse<any>(
    await fetch(`${BASE_URL}/api/v1/professor/sessions/${sessionId}/engagement/label`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ student_id: studentId, label, notes }),
    })
  );
}

export async function getMLModels(): Promise<MLModelInfo[]> {
  return handleResponse<MLModelInfo[]>(
    await fetch(`${BASE_URL}/api/v1/admin/ml/engagement/models`, {
      headers: authHeaders(),
    })
  );
}

export async function trainMLModel(params: { n_estimators?: number; version_tag?: string }): Promise<MLModelInfo> {
  return handleResponse<MLModelInfo>(
    await fetch(`${BASE_URL}/api/v1/admin/ml/engagement/train`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(params),
    })
  );
}

export async function approveMLModel(modelId: string): Promise<MLModelInfo> {
  return handleResponse<MLModelInfo>(
    await fetch(`${BASE_URL}/api/v1/admin/ml/engagement/models/${modelId}/approve`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

export async function retireMLModel(modelId: string): Promise<MLModelInfo> {
  return handleResponse<MLModelInfo>(
    await fetch(`${BASE_URL}/api/v1/admin/ml/engagement/models/${modelId}/retire`, {
      method: 'POST',
      headers: authHeaders(),
    })
  );
}

// =====================================================================
// Professor Student Engagement APIs
// =====================================================================

export interface EngagementBatchItem {
  id: string;
  name: string;
  code?: string;
  description?: string;
  student_count: number;
  created_at?: string;
}

export interface EngagementSessionItem {
  id: string;
  batch_id: string;
  title: string;
  status: string;
  is_active: boolean;
  start_time?: string;
  end_time?: string;
  created_at?: string;
  participant_count: number;
}

export interface StudentEngagementRowItem {
  student_name: string;
  student_id: string;
  student_email?: string;
  session_status: string; // 'Joined' | 'Left' | 'Offline'
  policy_status: string;  // 'Active' | 'Restored' | 'Failed'
  allowed_academic_application_active_seconds?: number;
  allowed_academic_website_active_seconds?: number;
  allowed_academic_active_seconds?: number;
  academic_activity_seconds: number;
  non_academic_activity_seconds: number;
  idle_seconds: number;
  unknown_or_unavailable_seconds?: number;
  feature_completeness_percent?: number;
  approved_apps_summary?: Record<string, number> | null;
  approved_websites_summary?: Record<string, number> | null;
  application_switch_count: number;
  blocked_website_attempt_count: number;
  unauthorized_application_attempt_count: number;
  policy_violation_count: number;
  engagement_estimate?: 'High' | 'Medium' | 'Low' | null;
  confidence?: number | null;
  probability_high?: number | null;
  probability_medium?: number | null;
  probability_low?: number | null;
  collection_status?: 'collecting' | 'data_insufficient' | 'preliminary_prediction' | 'final_prediction' | string;
  valid_windows_received?: number;
  minimum_windows_required?: number;
  session_elapsed_seconds?: number;
  last_telemetry_at?: string | null;
  prediction_type?: 'Collecting' | 'Live Preliminary' | 'Final' | null;
  prediction_available: boolean;
  prediction_reason?: string | null;
  last_updated_time?: string | null;
  professor_review_status?: string | null;
  professor_override_label?: string | null;
  prediction_id?: string | null;
  model_version?: string | null;
  is_advisory?: boolean;
  review_required?: boolean;
}

export interface SessionEngagementDetailResponse {
  session_id: string;
  session_title: string;
  batch_id: string;
  batch_name: string;
  session_status: string;
  is_active: boolean;
  has_active_model: boolean;
  model_version_tag?: string | null;
  students: StudentEngagementRowItem[];
  empty_reason?: string | null;
}

export async function fetchProfessorEngagementBatches(): Promise<EngagementBatchItem[]> {
  return handleResponse<EngagementBatchItem[]>(
    await fetch(`${BASE_URL}/api/v1/professor/engagement/batches`, {
      headers: authHeaders(),
    })
  );
}

export async function fetchProfessorEngagementBatchSessions(
  batchId: string,
  status?: string,
  startDate?: string,
  endDate?: string
): Promise<EngagementSessionItem[]> {
  const params = new URLSearchParams();
  if (status && status !== 'All') params.append('status', status);
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  const qs = params.toString() ? `?${params.toString()}` : '';

  return handleResponse<EngagementSessionItem[]>(
    await fetch(`${BASE_URL}/api/v1/professor/engagement/batches/${batchId}/sessions${qs}`, {
      headers: authHeaders(),
    })
  );
}

export async function fetchProfessorSessionEngagement(
  sessionId: string
): Promise<SessionEngagementDetailResponse> {
  return handleResponse<SessionEngagementDetailResponse>(
    await fetch(`${BASE_URL}/api/v1/professor/engagement/sessions/${sessionId}`, {
      headers: authHeaders(),
    })
  );
}

export interface StudentPredictionHistoryItem {
  id: string;
  student_id: string;
  prediction: string;
  confidence: number | null;
  prediction_type: string;
  review_status?: string | null;
  professor_override_label?: string | null;
  model_version_tag?: string | null;
  window_start_at?: string | null;
  window_end_at?: string | null;
  created_at?: string | null;
}

export async function fetchProfessorStudentPredictionHistory(
  sessionId: string,
  studentId?: string
): Promise<StudentPredictionHistoryItem[]> {
  const qs = studentId ? `?student_id=${encodeURIComponent(studentId)}` : '';
  return handleResponse<StudentPredictionHistoryItem[]>(
    await fetch(`${BASE_URL}/api/v1/professor/engagement/sessions/${sessionId}/history${qs}`, {
      headers: authHeaders(),
    })
  );
}

export const api = {
  get: async (url: string) => {
    const res = await fetch(`${BASE_URL}${url}`, { headers: authHeaders() });
    const data = await handleResponse<any>(res);
    return { data };
  },
  post: async (url: string, body?: any) => {
    const res = await fetch(`${BASE_URL}${url}`, {
      method: 'POST',
      headers: authHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await handleResponse<any>(res);
    return { data };
  },
  put: async (url: string, body?: any) => {
    const res = await fetch(`${BASE_URL}${url}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await handleResponse<any>(res);
    return { data };
  },
  delete: async (url: string) => {
    const res = await fetch(`${BASE_URL}${url}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    const data = await handleResponse<any>(res);
    return { data };
  },
};
