
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
  id: string;
  name: string;
  mode: 'Blocklist' | 'Whitelist';
  websites: string[];
  applications: string[];
}

export interface Batch {
  id: string;
  name: string;
  code: string; // The 6-char code students use to join
  department: string;
  year: string;
  studentCount: number;
  createdBy: string;
}

export interface Session {
  id: string;
  title: string;
  course: string;
  type: SessionType;
  startTime: string;
  endTime: string;
  status: SessionStatus;
  ruleSetId: string;
  batchIds?: string[]; // Optional for backward compatibility, but used for assignment
}

export interface LogEntry {
  id: string;
  studentId: string;
  studentName: string;
  sessionId: string;
  sessionName: string;
  resourceAccessed: string;
  isWhitelisted: boolean;
  timeSpentSeconds: number;
  engagementScore: number;
  timestamp: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'Admin' | 'Professor' | 'Student';
  avatar?: string;
}
