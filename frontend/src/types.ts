export enum SessionType {
  LECTURE = 'Lecture',
  EXAM = 'Exam',
  LAB = 'Lab',
  QUIZ = 'Quiz'
}

export enum SessionStatus {
  SCHEDULED = 'Upcoming',
  UPCOMING = 'Upcoming',
  ACTIVE = 'Active',
  PAUSED = 'Paused',
  COMPLETED = 'Completed',
  CANCELLED = 'Cancelled'
}

export interface BatchStudent {
  _id: string;
  id?: string;
  studentId?: string;
  name: string;
  sapId?: string;
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
  description?: string;
  course: string;
  type: SessionType | string;
  startTime: string;
  endTime: string;
  startedAt?: string;
  endedAt?: string;
  status: SessionStatus | string;
  isJoined?: boolean;
  professorName?: string;
  ruleSetId?: string;
  batchIds: string[];
  professorId?: string;
  violationCount?: number;
  violation_count?: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface LogEntry {
  _id: string;
  type: 'USAGE' | 'EVENT' | 'ANOMALY' | 'VIOLATION';
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

export interface WebsiteRule {
  _id?: string;
  id?: string;
  rule_set_id?: string;
  domain_pattern: string;
  rule_mode: 'allowed' | 'blocked';
  category?: string;
  priority?: number;
  is_enabled?: boolean;
  reason?: string;
  created_at?: string;
}

export interface ApplicationRule {
  _id?: string;
  id?: string;
  rule_set_id?: string;
  application_name: string;
  rule_mode: 'allowed' | 'blocked';
  category?: string;
  action?: 'log' | 'warn' | 'close';
  is_enabled?: boolean;
  reason?: string;
  created_at?: string;
}

export interface DevicePolicyRequirement {
  _id?: string;
  id?: string;
  rule_set_id?: string;
  require_agent_enrolled?: boolean;
  require_website_filtering?: boolean;
  require_application_control?: boolean;
  require_managed_browser?: boolean;
  require_usb_storage_restriction?: boolean;
  required_device_compliance_level?: 'audit' | 'development' | 'managed' | 'strict';
  blocked_app_action?: 'log' | 'warn' | 'close';
  created_at?: string;
  updated_at?: string;
}

export interface RuleSet {
  _id: string;
  id?: string;
  name: string;
  description?: string;
  batch_id?: string;
  batchId?: string;
  session_id?: string;
  sessionId?: string;
  version: number;
  status: 'draft' | 'published' | 'revoked';
  policy_hash?: string;
  signature?: string;
  mode?: 'Allowlist' | 'Blocklist';
  websites?: string[];
  applications?: string[];
  allowed_websites?: string[];
  blocked_websites?: string[];
  allowed_applications?: string[];
  blocked_applications?: string[];
  website_rules?: WebsiteRule[];
  application_rules?: ApplicationRule[];
  device_requirements?: DevicePolicyRequirement;
  created_at?: string;
  updated_at?: string;
}

export interface LiveMonitorStudent {
  student_id: string;
  name: string;
  participant_status: 'joined' | 'left';
  presence_status: 'online' | 'offline';
  enforcement_status?: string;
  policy_status?: 'pending' | 'active' | 'restored' | 'failed' | string;
  usb_storage_status?: 'active' | 'inactive' | 'requires_managed_device' | 'unsupported' | 'error' | 'not_compliant' | string;
  device_compliance_status?: string;
  engagement_state?: 'collecting_live_data' | 'data_insufficient' | 'high' | 'medium' | 'low' | 'final' | string;
  last_seen_at: string;
  connection_source: 'both' | 'browser' | 'agent' | 'none';
  engagement_score: number | null;
  latest_activity: string;
  violation_count?: number;
  blocked_website_attempts?: number;
  blocked_app_attempts?: number;
  academic_activity_summary?: Record<string, number>;
}

export interface LiveMonitorData {
  session_id: string;
  status: string;
  students: LiveMonitorStudent[];
  online_count: number;
  joined_count: number;
  enforcing_count?: number;
  violation_count: number;
}
