import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  X,
  Wifi,
  WifiOff,
  Monitor,
  Clock,
  Users,
  ShieldAlert,
  Activity,
  TrendingUp,
} from 'lucide-react';
import { Session, LogEntry } from '../types';
import { getSocket, joinSession } from '../lib/socket';
import { getLogs, getSessionLogs, getBatchById } from '../lib/api';
import StudentActivityModal from './StudentActivityModal';
// ─── Types ─────────────────────────────────────────────────────────────────────
interface StudentTelemetry {
  studentId: string;
  studentName: string;
  sapId: string;
  activeApp: string;
  status: 'online' | 'idle' | 'offline';
  engagementScore: number;
  isViolation: boolean;
  lastSeen: string;
  lastActivityAt: number; // Date.now() when we last received ANY event for this student
}

interface SessionLiveMonitorModalProps {
  isOpen: boolean;
  onClose: () => void;
  session: Session;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────
const STALE_THRESHOLD_MS = 45_000; // 45s without activity → idle (accounts for 15s polling gap + network delay)
const OFFLINE_THRESHOLD_MS = 90_000; // 90s → offline

const getPresenceStatus = (lastActivityAt: number): 'online' | 'idle' | 'offline' => {
  if (lastActivityAt === 0) return 'offline'; // never seen (batch pre-populated)
  const delta = Date.now() - lastActivityAt;
  if (delta < STALE_THRESHOLD_MS) return 'online';
  if (delta < OFFLINE_THRESHOLD_MS) return 'idle';
  return 'offline';
};

const presenceConfig = {
  online: { color: 'bg-emerald-500', ring: 'ring-emerald-500/30', label: 'Online', text: 'text-emerald-600 dark:text-emerald-400' },
  idle: { color: 'bg-amber-500', ring: 'ring-amber-500/30', label: 'Idle', text: 'text-amber-600 dark:text-amber-400' },
  offline: { color: 'bg-slate-400', ring: 'ring-slate-400/30', label: 'Offline', text: 'text-slate-500 dark:text-slate-400' },
};

const engagementColor = (score: number) => {
  if (score >= 80) return 'bg-emerald-500';
  if (score >= 50) return 'bg-amber-500';
  return 'bg-rose-500';
};

const engagementTextColor = (score: number) => {
  if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
  if (score >= 50) return 'text-amber-600 dark:text-amber-400';
  return 'text-rose-600 dark:text-rose-400';
};

// ─── Component ─────────────────────────────────────────────────────────────────
export const SessionLiveMonitorModal: React.FC<SessionLiveMonitorModalProps> = ({
  isOpen,
  onClose,
  session,
}) => {
  const [students, setStudents] = useState<Map<string, StudentTelemetry>>(new Map());
  const [attentionScores, setAttentionScores] = useState<Map<string, { score: number; label: string; color: string }>>(new Map());
  const [selectedStudent, setSelectedStudent] = useState<StudentTelemetry | null>(null);
  const [recentLogs, setRecentLogs] = useState<LogEntry[]>([]);
  const [socketConnected, setSocketConnected] = useState(false);
  const presenceTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [, forceUpdate] = useState(0); // trigger re-render for stale checks

  // ── Load initial logs & enrolled batch students for this session
  const loadInitialLogs = useCallback(async () => {
    const studentMap = new Map<string, StudentTelemetry>();

    // 1. Pre-populate enrolled students from mapped batches
    if (Array.isArray(session.batchIds) && session.batchIds.length > 0) {
      try {
        const batchPromises = session.batchIds.map((bId) => getBatchById(bId).catch(() => null));
        const batches = await Promise.all(batchPromises);
        for (const batch of batches) {
          if (batch && Array.isArray(batch.students)) {
            for (const s of batch.students) {
              if (s && s._id && !studentMap.has(s._id)) {
                studentMap.set(s._id, {
                  studentId: s._id,
                  studentName: s.name || 'Enrolled Student',
                  sapId: s.sapId || '',
                  activeApp: 'Not Joined Yet',
                  status: 'offline',
                  engagementScore: 0,
                  isViolation: false,
                  lastSeen: new Date(0).toISOString(),
                  lastActivityAt: 0, // never seen
                });
              }
            }
          }
        }
      } catch (errBatch) {
        console.warn('[monitor] Failed to load batch students:', errBatch);
      }
    }

    // 2. Load activity logs
    let logs: LogEntry[] = [];
    try {
      logs = await getLogs(session._id);
    } catch {
      try {
        logs = await getSessionLogs(session._id);
      } catch (err2) {
        console.warn('[monitor] Failed to load initial logs:', err2);
      }
    }

    const sorted = logs
      .sort((a: LogEntry, b: LogEntry) => +new Date(b.timestamp) - +new Date(a.timestamp))
      .slice(0, 50);
    setRecentLogs(sorted);

    // 3. Update student presence from historical logs
    // Use the log timestamps to determine if the student was recently active
    const now = Date.now();
    for (const log of sorted) {
      const existing = studentMap.get(log.studentId);
      const logTime = new Date(log.timestamp).getTime();
      // If the log is recent (within our offline threshold), treat the student as having been active
      const activityAt = (now - logTime < OFFLINE_THRESHOLD_MS) ? logTime : 0;
      // Only update if this log is newer than what we have
      const currentActivityAt = existing?.lastActivityAt || 0;
      studentMap.set(log.studentId, {
        studentId: log.studentId,
        studentName: log.studentName || existing?.studentName || 'Student',
        sapId: existing?.sapId || '',
        activeApp: log.resource || existing?.activeApp || 'Unknown',
        status: 'offline', // will be recalculated
        engagementScore: log.engagementScore || 50,
        isViolation: log.isViolation,
        lastSeen: log.timestamp,
        lastActivityAt: Math.max(currentActivityAt, activityAt),
      });
    }

    setStudents(studentMap);
  }, [session._id, session.batchIds]);

  // ── Socket & telemetry setup
  useEffect(() => {
    if (!isOpen) return;

    loadInitialLogs();

    const socket = getSocket();
    joinSession(session._id);

    const onConnect = () => setSocketConnected(true);
    const onDisconnect = () => setSocketConnected(false);

    // Student Joined Event
    const onStudentJoined = (data: any) => {
      if (data.sessionId !== session._id) return;

      setStudents((prev) => {
        const updated = new Map(prev);
        const existing = updated.get(data.studentId);
        updated.set(data.studentId, {
          studentId: data.studentId,
          studentName: data.studentName || existing?.studentName || 'Student',
          sapId: data.sapId || existing?.sapId || '',
          activeApp: 'Joined Session',
          status: 'online',
          engagementScore: 85,
          isViolation: false,
          lastSeen: new Date().toISOString(),
          lastActivityAt: Date.now(), // ← KEY: real client-side timestamp
        });
        return updated;
      });
    };

    // Live student telemetry from agent heartbeats
    const onStudentTelemetry = (data: any) => {
      if (data.sessionId !== session._id) return;

      setStudents((prev) => {
        const updated = new Map(prev);
        const existing = updated.get(data.studentId);
        updated.set(data.studentId, {
          studentId: data.studentId,
          studentName: data.studentName || existing?.studentName || 'Unknown',
          sapId: data.sapId || existing?.sapId || '',
          activeApp: data.activeApp || 'Unknown',
          status: 'online',
          engagementScore: data.engagementScore ?? 50,
          isViolation: Boolean(data.isViolation),
          lastSeen: data.lastSeen || new Date().toISOString(),
          lastActivityAt: Date.now(), // ← KEY: real client-side timestamp
        });
        return updated;
      });
    };

    // Live log events (block attempts, activity)
    const onLiveLog = (data: any) => {
      if (data.sessionId !== session._id) return;
      const entry: LogEntry = {
        _id: data._id || `ws-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: data.type || 'EVENT',
        studentId: data.studentId || '',
        studentName: data.studentName || 'Unknown',
        sessionId: data.sessionId,
        resource: data.resource || '',
        details: data.details || '',
        duration: data.duration,
        engagementScore: data.engagementScore,
        isViolation: Boolean(data.isViolation),
        timestamp: data.timestamp || new Date().toISOString(),
      };

      setRecentLogs((prev) => {
        if (prev.some((l) => l._id === entry._id)) return prev;
        return [entry, ...prev].slice(0, 50);
      });

      // Always update student card presence on every log event
      if (entry.studentId) {
        setStudents((prev) => {
          const updated = new Map(prev);
          const existing = updated.get(entry.studentId);
          updated.set(entry.studentId, {
            studentId: entry.studentId,
            studentName: entry.studentName || existing?.studentName || 'Student',
            sapId: existing?.sapId || '',
            activeApp: entry.resource || existing?.activeApp || 'Unknown',
            status: 'online',
            engagementScore: entry.engagementScore ?? existing?.engagementScore ?? 50,
            isViolation: entry.isViolation || false,
            lastSeen: entry.timestamp,
            lastActivityAt: Date.now(), // ← KEY: real client-side timestamp
          });
          return updated;
        });
      }
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('student_joined', onStudentJoined);
    socket.on('student_telemetry', onStudentTelemetry);
    socket.on('live_log_update', onLiveLog);

    // Attention score updates
    const onAttentionUpdate = (data: any) => {
      if (!data?.studentId) return;
      setAttentionScores((prev) => {
        const updated = new Map(prev);
        updated.set(data.studentId, {
          score: data.score ?? 0,
          label: data.label || 'Moderate',
          color: data.color || '#f59e0b',
        });
        return updated;
      });
    };
    socket.on('attention_update', onAttentionUpdate);

    if (socket.connected) setSocketConnected(true);

    // Periodically refresh presence status (stale check)
    presenceTimerRef.current = setInterval(() => {
      forceUpdate((c) => c + 1);
    }, 10_000);

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('student_joined', onStudentJoined);
      socket.off('student_telemetry', onStudentTelemetry);
      socket.off('live_log_update', onLiveLog);
      socket.off('attention_update', onAttentionUpdate);
      if (presenceTimerRef.current) clearInterval(presenceTimerRef.current);
    };
  }, [isOpen, session._id, loadInitialLogs]);

  // ── Escape key to close
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // ── Derived stats (uses lastActivityAt for presence, NOT server timestamp)
  const studentList = Array.from(students.values()).map((s) => ({
    ...s,
    status: getPresenceStatus(s.lastActivityAt),
  }));
  const onlineCount = studentList.filter((s) => s.status === 'online').length;
  const violationCount = studentList.filter((s) => s.isViolation).length;
  const avgEngagement =
    studentList.length > 0
      ? Math.round(studentList.reduce((sum, s) => sum + s.engagementScore, 0) / studentList.length)
      : 0;

  const endTime = new Date(session.endTime);
  const now = new Date();
  const timeLeftMs = Math.max(0, endTime.getTime() - now.getTime());
  const timeLeftMin = Math.ceil(timeLeftMs / 60_000);

  return (
    <div className="fixed inset-0 z-50 flex flex-col animate-fade-in">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-900/70 backdrop-blur-sm" onClick={onClose} />

      {/* Modal Content */}
      <div className="relative flex-1 flex flex-col m-3 md:m-6 bg-white dark:bg-slate-900 rounded-2xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-700">
        {/* ─── Header ───────────────────────────────────────────────── */}
        <div className="shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-900">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span>
              </span>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Live Command Center
              </h2>
            </div>
            <span className="text-sm text-slate-500 dark:text-slate-400 hidden sm:inline">
              — {session.title}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
              socketConnected
                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                : 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800'
            }`}>
              {socketConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
              {socketConnected ? 'Connected' : 'Disconnected'}
            </span>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* ─── Summary Stats Bar ────────────────────────────────────── */}
        <div className="shrink-0 grid grid-cols-2 sm:grid-cols-4 gap-4 px-6 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Users size={18} className="text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Students Online</p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {onlineCount}<span className="text-sm font-normal text-slate-400">/{studentList.length}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-100 dark:bg-emerald-900/30 rounded-lg">
              <TrendingUp size={18} className="text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Avg Engagement</p>
              <p className={`text-lg font-bold ${engagementTextColor(avgEngagement)}`}>
                {avgEngagement}%
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-rose-100 dark:bg-rose-900/30 rounded-lg">
              <ShieldAlert size={18} className="text-rose-600 dark:text-rose-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Violations</p>
              <p className="text-lg font-bold text-rose-600 dark:text-rose-400">
                {violationCount}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
              <Clock size={18} className="text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Time Remaining</p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {timeLeftMin > 0 ? `${timeLeftMin}m` : session.status.toLowerCase() === 'active' ? 'Active' : 'Ended'}
              </p>
            </div>
          </div>
        </div>

        {/* ─── Body: Student Grid + Activity Feed ───────────────────── */}
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
          {/* Student Cards Grid */}
          <div className="flex-1 overflow-y-auto p-6">
            <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-4">
              Student Activity ({studentList.length})
            </h3>
            {studentList.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                <Users size={48} className="mb-4 opacity-40" />
                <p className="text-sm font-medium">Waiting for student activity...</p>
                <p className="text-xs mt-1 max-w-sm text-center">
                  Students will appear here once they join the session or their agent sends a heartbeat.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {studentList
                  .sort((a, b) => {
                    // Sort: violations first, then online, idle, offline
                    if (a.isViolation !== b.isViolation) return a.isViolation ? -1 : 1;
                    const order = { online: 0, idle: 1, offline: 2 };
                    return order[a.status] - order[b.status];
                  })
                  .map((student) => {
                    const presence = presenceConfig[student.status];
                    return (
                      <div
                        key={student.studentId}
                        onClick={() => setSelectedStudent(student)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedStudent(student); } }}
                        className={`relative p-4 rounded-xl border transition-all duration-300 cursor-pointer hover:ring-2 hover:ring-indigo-500/50 ${
                          student.isViolation
                            ? 'border-rose-400 dark:border-rose-700 bg-rose-50/80 dark:bg-rose-950/30 shadow-rose-200/50 dark:shadow-rose-900/20 shadow-md animate-pulse-slow'
                            : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:shadow-md'
                        }`}
                      >
                        {/* Status + Name */}
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-2.5">
                            <div className="relative">
                              <div className="h-10 w-10 rounded-full bg-gradient-to-br from-brand-500 to-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
                                {student.studentName.charAt(0).toUpperCase()}
                              </div>
                              <span className={`absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full ${presence.color} ring-2 ring-white dark:ring-slate-800`} />
                            </div>
                            <div>
                              <p className="font-semibold text-slate-900 dark:text-white text-sm leading-tight">
                                {student.studentName}
                              </p>
                              {student.sapId && (
                                <p className="text-[10px] text-slate-400 font-mono mt-0.5">{student.sapId}</p>
                              )}
                            </div>
                          </div>

                          {/* Attention Score */}
                          {(() => {
                            const attn = attentionScores.get(student.studentId);
                            const score = attn?.score ?? null;
                            const label = attn?.label || null;
                            const color = attn?.color || '#94a3b8';
                            const radius = 18;
                            const circumference = 2 * Math.PI * radius;
                            const progress = score !== null ? (score / 100) * circumference : 0;

                            return (
                              <div className="flex items-center gap-2 -mt-1 mb-1 ml-[52px]">
                                <svg width={44} height={44} viewBox="0 0 44 44" className="shrink-0">
                                  <circle cx={22} cy={22} r={radius} fill="none" stroke="currentColor" strokeWidth={3} className="text-slate-200 dark:text-slate-700" />
                                  {score !== null && (
                                    <circle cx={22} cy={22} r={radius} fill="none" stroke={color} strokeWidth={3} strokeDasharray={circumference} strokeDashoffset={circumference - progress} strokeLinecap="round" transform="rotate(-90 22 22)" className="transition-all duration-700" />
                                  )}
                                  <text x={22} y={22} textAnchor="middle" dominantBaseline="central" fill={score !== null ? color : '#94a3b8'} fontSize={score !== null ? 11 : 14} fontWeight="bold">
                                    {score !== null ? score : '—'}
                                  </text>
                                </svg>
                                {label && (
                                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                    label === 'Focused'
                                      ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
                                      : label === 'Moderate'
                                        ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
                                        : 'bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 animate-pulse'
                                  }`}>
                                    {label}
                                  </span>
                                )}
                              </div>
                            );
                          })()}
                          <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${presence.text} bg-slate-100 dark:bg-slate-700`}>
                            {presence.label}
                          </span>
                        </div>

                        {/* Active App */}
                        <div className="flex items-center gap-2 mb-3 px-2.5 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-700/50 border border-slate-100 dark:border-slate-600">
                          <Monitor size={13} className="text-slate-400 shrink-0" />
                          <p className={`text-xs font-mono truncate ${
                            student.isViolation ? 'text-rose-600 dark:text-rose-400 font-semibold' : 'text-slate-600 dark:text-slate-300'
                          }`}>
                            {student.activeApp}
                            {student.isViolation && ' ⚠️'}
                          </p>
                        </div>

                        {/* Engagement Bar */}
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${engagementColor(student.engagementScore)}`}
                              style={{ width: `${Math.min(100, student.engagementScore)}%` }}
                            />
                          </div>
                          <span className={`text-xs font-bold ${engagementTextColor(student.engagementScore)}`}>
                            {student.engagementScore}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>

          {/* Activity Feed Sidebar */}
          <div className="lg:w-80 xl:w-96 shrink-0 border-t lg:border-t-0 lg:border-l border-slate-200 dark:border-slate-700 flex flex-col bg-slate-50/50 dark:bg-slate-800/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-2">
                <Activity size={14} />
                Activity Feed
              </h3>
              <span className="text-xs text-slate-400 bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded-full">
                {recentLogs.length}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {recentLogs.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-8">No activity yet</p>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-700/50">
                  {recentLogs.slice(0, 30).map((log) => (
                    <div key={log._id} className="px-4 py-2.5 hover:bg-white dark:hover:bg-slate-800 transition-colors">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-slate-900 dark:text-white truncate">
                            {log.studentName}
                          </p>
                          <p className={`text-[11px] mt-0.5 truncate ${
                            log.isViolation ? 'text-rose-600 dark:text-rose-400 font-semibold' : 'text-slate-500 dark:text-slate-400'
                          }`}>
                            {log.isViolation ? '🚫 ' : ''}{log.resource || log.details || 'Activity'}
                          </p>
                        </div>
                        <span className="text-[10px] text-slate-400 font-mono whitespace-nowrap shrink-0">
                          {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      {selectedStudent && (
        <StudentActivityModal
          isOpen={!!selectedStudent}
          onClose={() => setSelectedStudent(null)}
          student={selectedStudent}
          sessionId={session._id}
          sessionTitle={session.title}
        />
      )}
    </div>
  );
};
