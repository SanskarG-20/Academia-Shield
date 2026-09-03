
export enum SessionType {
  LECTURE = 'Lecture',
  EXAM = 'Exam',
  LAB = 'Lab',
  QUIZ = 'Quiz'
}

export enum SessionStatus {
  UPCOMING = 'Upcoming',
  ACTIVE = 'Active',
  COMPLETED = 'Completed',
  CANCELLED = 'Cancelled'
}

export interface RuleSet {
  _id: string;
  name: string;
  mode: 'Blocklist' | 'Whitelist';
  websites: string[];
  applications: string[];
  professorId?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface BatchStudent {
  _id: string;
  name: string;
  sapId: string;
  rollNumber: string;
  email?: string;
  department?: string;
  year?: string;
}

export interface Batch {
  _id: string;
  name: string;
  code: string;
  department: string;
  year: string;
  professorId?: string;
  students?: BatchStudent[];
  createdAt?: string;
  updatedAt?: string;
}

export interface Session {
  _id: string;
  title: string;
  course: string;
  type: SessionType | string;
  startTime: string;
  endTime: string;
  status: SessionStatus | string;
  ruleSetId?: string;
  batchIds: string[];
  professorId?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface LogEntry {
  _id: string;
  type: 'USAGE' | 'EVENT' | 'ANOMALY';
  studentId: string;
  studentName: string;
  sessionId: string;
  resource?: string;
  details?: string;
  duration?: number;
  engagementScore?: number;
  isViolation: boolean;
  timestamp: string;
}

export interface UserProfile {
  _id: string;
  name: string;
  email: string;
  role: 'student' | 'professor';
  sapId?: string;
  department?: string;
  rollNumber?: string;
  year?: string;
  designation?: string;
  joinedBatches?: Batch[];
}

export interface ActivityEvent {
  _id: string;
  sessionId: string;
  studentId: string;
  studentName: string;
  sapId: string;
  eventType: 'APP_FOCUS' | 'DOMAIN_VISIT' | 'DOMAIN_BLOCKED';
  application: string;
  domain?: string;
  title?: string;
  status: 'ALLOWED' | 'BLOCKED';
  startedAt: string;
  endedAt: string;
  durationMs: number;
  createdAt: string;
}

export interface ActivitySummary {
  totalActiveMs: number;
  topApplications: Array<{ application: string; durationMs: number; count: number }>;
  topDomains: Array<{ domain: string; durationMs: number; count: number; status: string }>;
  blockedAttempts: number;
  allowedDomains: number;
  uniqueApps: number;
}
