import { RuleSet, Session } from '../types';

// ⚠️  DEMO CONFIG — UPDATE BEFORE DEMO
// Step 1: On professor's laptop run: ipconfig (Windows) or ifconfig (Mac)
// Step 2: Find "Wireless LAN adapter" → IPv4 Address
// Step 3: Paste it below (Windows hotspot default: 192.168.137.1)
export const BASE_URL = 'http://localhost:5000';

// ──────────────────────────────────────────────────────────────────────────────
// INTERNAL HELPERS
// ──────────────────────────────────────────────────────────────────────────────

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: 'Server error' }));
    throw new Error(err.message || `HTTP ${res.status}`);
  }
  return res.json();
}

// ──────────────────────────────────────────────────────────────────────────────
// AUTH
// ──────────────────────────────────────────────────────────────────────────────

export async function professorLogin(email: string, password: string) {
  const data = await handleResponse<any>(
    await fetch(`${BASE_URL}/api/auth/professor/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  );
  // Save to localStorage exactly as App.tsx auth guard expects
  localStorage.setItem('token', data.token);
  localStorage.setItem('isAuthenticated', 'true');
  localStorage.setItem('userRole', 'professor');
  localStorage.setItem('userName', data.user?.name || 'Professor');
  localStorage.setItem('userEmail', email);
  localStorage.setItem('professorProfile', JSON.stringify(data.user));
  return data;
}

// ──────────────────────────────────────────────────────────────────────────────
// RULES
// ──────────────────────────────────────────────────────────────────────────────

export async function getRules(): Promise<RuleSet[]> {
  return handleResponse(
    await fetch(`${BASE_URL}/api/rules`, { headers: authHeaders() })
  );
}

export async function createRule(
  name: string,
  mode: string,
  websites: string[],
  applications: string[]
) {
  return handleResponse(
    await fetch(`${BASE_URL}/api/rules`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ name, mode, websites, applications }),
    })
  );
}

export async function deleteRule(id: string): Promise<void> {
  await handleResponse(
    await fetch(`${BASE_URL}/api/rules/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// SESSIONS
// ──────────────────────────────────────────────────────────────────────────────

export async function getSessions(): Promise<Session[]> {
  return handleResponse(
    await fetch(`${BASE_URL}/api/sessions`, { headers: authHeaders() })
  );
}

export async function createSession(data: {
  title: string;
  course: string;
  type: string;
  startTime: string;
  endTime: string;
  ruleSetId: string;
  batchIds: string[];
}) {
  return handleResponse(
    await fetch(`${BASE_URL}/api/sessions`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    })
  );
}

export async function updateSessionStatus(id: string, status: string) {
  return handleResponse(
    await fetch(`${BASE_URL}/api/sessions/${id}/status`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ status }),
    })
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// AGENT CONFIG — no auth required
// ──────────────────────────────────────────────────────────────────────────────

export async function getAgentConfig() {
  return handleResponse<{
    blocking_active: boolean;
    domains: string[];
    apps: string[];
    server_time: string;
    active_sessions: { id: string; title: string; ends_at: string }[];
  }>(await fetch(`${BASE_URL}/api/agent/config`));
}
