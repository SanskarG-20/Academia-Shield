
import { RuleSet, Session, SessionStatus, SessionType, LogEntry, Batch } from './types';

export const MOCK_RULE_SETS: RuleSet[] = [
  {
    id: '1',
    name: 'Strict Exam Mode',
    mode: 'Whitelist',
    websites: ['university.edu', 'canvas.instructure.com'],
    applications: ['Calculator', 'AcademiaShieldHelper'],
  },
  {
    id: '2',
    name: 'Open Lecture',
    mode: 'Blocklist',
    websites: ['facebook.com', 'twitter.com', 'tiktok.com', 'instagram.com'],
    applications: ['Steam', 'Discord'],
  },
  {
    id: '3',
    name: 'CS Lab Environment',
    mode: 'Whitelist',
    websites: ['github.com', 'stackoverflow.com', 'docs.python.org', 'university.edu'],
    applications: ['VS Code', 'Terminal', 'Chrome'],
  }
];

export const MOCK_BATCHES: Batch[] = [
  {
    id: 'b1',
    name: 'CS-A (Algorithms)',
    code: 'ALG9X2',
    department: 'CSE',
    year: '3',
    studentCount: 45,
    createdBy: 'Dr. A. Turing'
  },
  {
    id: 'b2',
    name: 'ML-Specialization',
    code: 'ML2024',
    department: 'CSE',
    year: '4',
    studentCount: 28,
    createdBy: 'Dr. A. Turing'
  }
];

export const MOCK_SESSIONS: Session[] = [
  {
    id: '101',
    title: 'Midterm Examination',
    course: 'CS 302: Algorithms',
    type: SessionType.EXAM,
    startTime: '2023-10-25T09:00:00',
    endTime: '2023-10-25T11:00:00',
    status: SessionStatus.ACTIVE,
    ruleSetId: '1',
    batchIds: ['b1']
  },
  {
    id: '102',
    title: 'Intro to ML Lecture',
    course: 'CS 405: Machine Learning',
    type: SessionType.LECTURE,
    startTime: '2023-10-25T13:00:00',
    endTime: '2023-10-25T14:30:00',
    status: SessionStatus.UPCOMING,
    ruleSetId: '2',
    batchIds: ['b2']
  },
  {
    id: '103',
    title: 'Database Systems Lab',
    course: 'CS 350: Databases',
    type: SessionType.LAB,
    startTime: '2023-10-24T14:00:00',
    endTime: '2023-10-24T16:00:00',
    status: SessionStatus.COMPLETED,
    ruleSetId: '3',
    batchIds: ['b1']
  },
];

export const MOCK_LOGS: LogEntry[] = [
  { id: 'l1', studentId: 'S1023', studentName: 'Alice Chen', sessionId: '101', sessionName: 'Midterm Examination', resourceAccessed: 'canvas.instructure.com', isWhitelisted: true, timeSpentSeconds: 1200, engagementScore: 98, timestamp: '2023-10-25T09:15:00' },
  { id: 'l2', studentId: 'S1045', studentName: 'Bob Smith', sessionId: '101', sessionName: 'Midterm Examination', resourceAccessed: 'chatgpt.com', isWhitelisted: false, timeSpentSeconds: 45, engagementScore: 15, timestamp: '2023-10-25T09:20:00' },
  { id: 'l3', studentId: 'S1023', studentName: 'Alice Chen', sessionId: '101', sessionName: 'Midterm Examination', resourceAccessed: 'university.edu', isWhitelisted: true, timeSpentSeconds: 850, engagementScore: 99, timestamp: '2023-10-25T09:45:00' },
  { id: 'l4', studentId: 'S1099', studentName: 'Charlie Day', sessionId: '103', sessionName: 'Database Systems Lab', resourceAccessed: 'stackoverflow.com', isWhitelisted: true, timeSpentSeconds: 300, engagementScore: 92, timestamp: '2023-10-24T14:30:00' },
  { id: 'l5', studentId: 'S1099', studentName: 'Charlie Day', sessionId: '103', sessionName: 'Database Systems Lab', resourceAccessed: 'discord.com', isWhitelisted: false, timeSpentSeconds: 120, engagementScore: 40, timestamp: '2023-10-24T14:45:00' },
];
