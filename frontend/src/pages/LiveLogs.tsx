import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Card } from '../components/ui/Card';
import {
  Activity,
  Wifi,
  WifiOff,
  ShieldAlert,
  CheckCircle,
  Loader2 as Spinner,
  Trash2,
  Search,
  Filter,
  Radio,
  Clock,
  Laptop,
  AlertTriangle,
  Play,
  Pause,
  RefreshCw,
  Globe,
  AppWindow,
  Usb,
  Users,
  Monitor,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Input';
import { LogEntry, Session } from '../types';
import { getLogs, getSessions } from '../lib/api';
import { getSocket, joinLiveLogs, joinSession, leaveSessionRoom } from '../lib/socket';

const renderResourceBadge = (resourceStr: string, isViolation: boolean = false) => {
  const res = String(resourceStr || '').trim();
  const lower = res.toLowerCase();

  // 1. USB / Pen Drive
  if (lower.includes('usb') || lower.includes('drive') || lower.includes('removable') || lower.includes('usbstor')) {
    return (
      <span className="inline-flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 rounded-lg bg-amber-500/10 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/30 font-semibold shadow-2xs">
        <Usb size={13} className="shrink-0 text-amber-500" />
        <span>{res.replace(/_/g, ' ')}</span>
      </span>
    );
  }

  // 2. Websites / Domains
  if (
    lower.includes('://') ||
    ['.com', '.org', '.net', '.io', '.ai', '.edu', '.in', '.gov', '.co', '.dev', '.app', '.xyz'].some((tld) =>
      lower.includes(tld)
    )
  ) {
    const cleanDomain = res.replace(/https?:\/\//i, '').split('/')[0];
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 rounded-lg border shadow-2xs ${
          isViolation
            ? 'bg-rose-500/10 text-rose-600 dark:text-rose-300 border-rose-500/30 font-bold'
            : 'bg-blue-500/10 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300 border-blue-500/30 font-medium'
        }`}
      >
        <Globe size={13} className="shrink-0" />
        <span>{cleanDomain}</span>
      </span>
    );
  }

  // 3. Applications (.exe / .app / processes)
  if (
    lower.endsWith('.exe') ||
    lower.endsWith('.app') ||
    ['chrome', 'code', 'discord', 'notepad', 'spotify', 'telegram', 'vlc', 'steam', 'powershell', 'cmd', 'python'].some(
      (app) => lower.includes(app)
    )
  ) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 rounded-lg border shadow-2xs ${
          isViolation
            ? 'bg-rose-500/10 text-rose-600 dark:text-rose-300 border-rose-500/30 font-bold'
            : 'bg-purple-500/10 dark:bg-purple-500/20 text-purple-600 dark:text-purple-300 border-purple-500/30 font-medium'
        }`}
      >
        <AppWindow size={13} className="shrink-0" />
        <span>{res}</span>
      </span>
    );
  }

  // 4. Student Attendance / Room Presence
  if (
    lower.includes('student_') ||
    lower.includes('joined') ||
    lower.includes('left') ||
    lower.includes('attendance') ||
    lower.includes('presence')
  ) {
    const isLeft = lower.includes('left');
    return (
      <span
        className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border font-medium shadow-2xs ${
          isLeft
            ? 'bg-slate-100 dark:bg-slate-800 text-slate-500 border-slate-300 dark:border-slate-700'
            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border-emerald-500/30'
        }`}
      >
        <Users size={13} className="shrink-0" />
        <span>{isLeft ? 'Left Session Room' : 'Joined Session Room'}</span>
      </span>
    );
  }

  // 5. Session Status / Controller Events
  if (lower.includes('session_') || lower.includes('status')) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-300 border border-indigo-500/30 font-medium shadow-2xs">
        <Activity size={13} className="shrink-0" />
        <span>{res.replace(/_/g, ' ')}</span>
      </span>
    );
  }

  // 6. Generic / Active Portal
  return (
    <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 shadow-2xs font-mono">
      <Monitor size={13} className="shrink-0 text-slate-400" />
      <span>{res || 'Active Portal'}</span>
    </span>
  );
};

const MAX_VISIBLE_LOGS = 150;

export const LiveLogs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'violations' | 'allowed'>('all');
  const [isPaused, setIsPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [socketConnected, setSocketConnected] = useState(false);
  const [recentLogId, setRecentLogId] = useState<string | null>(null);

  // Load active sessions and initial telemetry
  async function loadInitialData(silent = false) {
    if (!silent) setLoading(true);
    try {
      const [sessionsData, logsData] = await Promise.all([
        getSessions().catch(() => []),
        getLogs(selectedSessionId || undefined).catch(() => []),
      ]);

      setSessions(sessionsData || []);
      setLogs(logsData || []);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load live telemetry logs.');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadInitialData();

    // Connect WebSocket and join live_logs broadcast room
    const socket = getSocket();
    joinLiveLogs();
    if (selectedSessionId) {
      joinSession(selectedSessionId);
    }

    const onConnect = () => setSocketConnected(true);
    const onDisconnect = () => setSocketConnected(false);

    const onLiveLogUpdate = (data: any) => {
      if (isPaused) return;

      // If a specific session is selected, ignore logs explicitly for other sessions
      if (selectedSessionId && data.sessionId && data.sessionId !== selectedSessionId) {
        return;
      }

      const resStr = String(data.resource || data.activeApp || data.target_value || 'Activity').trim();
      const resLower = resStr.toLowerCase();

      // Skip internal lifecycle heartbeats and transitions
      if (
        resLower === 'policy_restored' ||
        resLower === 'system' ||
        resLower === 'heartbeat' ||
        resLower === 'state_transition' ||
        resLower === 'policy_delivered' ||
        resLower === 'policy_acknowledged'
      ) {
        return;
      }

      const canonicalId = data._id || data.event_id || data.id || `ws-${data.studentId || ''}-${resLower}-${data.timestamp || ''}`;
      const isViol = Boolean(data.isViolation || data.is_violation || data.type === 'VIOLATION');

      const newLog: LogEntry = {
        _id: canonicalId,
        type: isViol ? 'VIOLATION' : 'EVENT',
        studentId: data.studentId || '',
        studentName: data.studentName || 'Student',
        sessionId: data.sessionId || selectedSessionId || '',
        resource: resStr,
        details: data.details || (isViol ? `Blocked ${resStr}` : `Activity on ${resStr}`),
        duration: data.duration || 60,
        engagementScore: data.engagementScore ?? (isViol ? 30 : 85),
        isViolation: isViol,
        timestamp: data.timestamp || new Date().toISOString(),
      };

      setRecentLogId(canonicalId);
      setTimeout(() => setRecentLogId(null), 2500);

      setLogs((prev) => {
        if (prev.some((log) => log._id === newLog._id || (log.studentId === newLog.studentId && log.resource === newLog.resource && Math.abs(new Date(log.timestamp).getTime() - new Date(newLog.timestamp).getTime()) < 3000))) {
          return prev;
        }
        return [newLog, ...prev].slice(0, MAX_VISIBLE_LOGS);
      });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('live_log_update', onLiveLogUpdate);

    if (socket.connected) {
      setSocketConnected(true);
    }

    const interval = setInterval(() => {
      if (!isPaused) {
        getLogs(selectedSessionId || undefined)
          .then((fresh) => {
            setLogs((prev) => {
              const existingIds = new Set(prev.map((l) => l._id));
              const newItems = fresh.filter((l) => !existingIds.has(l._id));
              if (newItems.length === 0) return prev;
              return [...newItems, ...prev].slice(0, MAX_VISIBLE_LOGS);
            });
          })
          .catch(() => {});
      }
    }, 8000);

    return () => {
      if (selectedSessionId) {
        leaveSessionRoom(selectedSessionId);
      }
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('live_log_update', onLiveLogUpdate);
      socket.off('student_telemetry', onLiveLogUpdate);
      socket.off('policy_violation');
      clearInterval(interval);
    };
  }, [selectedSessionId, isPaused]);

  const logsForSession = useMemo(() => {
    if (!selectedSessionId) return logs;
    return logs.filter((log) => !log.sessionId || log.sessionId === selectedSessionId);
  }, [logs, selectedSessionId]);

  const filteredLogs = useMemo(() => {
    return logsForSession.filter((log) => {
      if (statusFilter === 'violations' && !log.isViolation) return false;
      if (statusFilter === 'allowed' && log.isViolation) return false;

      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase();
        const student = (log.studentName || '').toLowerCase();
        const res = (log.resource || '').toLowerCase();
        const det = (log.details || '').toLowerCase();
        return student.includes(term) || res.includes(term) || det.includes(term);
      }
      return true;
    });
  }, [logsForSession, statusFilter, searchTerm]);

  const violationCount = useMemo(() => logsForSession.filter((l) => l.isViolation).length, [logsForSession]);
  const activeStudentsCount = useMemo(() => {
    const ids = new Set(logsForSession.map((l) => l.studentId || l.studentName).filter(Boolean));
    return ids.size;
  }, [logsForSession]);

  const clearLogs = () => setLogs([]);

  if (loading && logs.length === 0) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            {socketConnected ? (
              <Radio className="text-emerald-500 animate-pulse" size={24} />
            ) : (
              <WifiOff className="text-amber-500" size={24} />
            )}
            Live Session Monitor
          </h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            {socketConnected
              ? 'Real-time telemetry streaming from student workspaces and local enforcement agents.'
              : 'Connecting to live telemetry WebSocket channel...'}
          </p>
        </div>

        {/* Live Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`px-3 py-1.5 rounded-full border flex items-center gap-1.5 text-xs font-semibold ${
              socketConnected
                ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400'
                : 'bg-amber-500/10 text-amber-600 border-amber-500/20 dark:text-amber-400'
            }`}
          >
            <Activity size={13} className={socketConnected ? 'animate-pulse' : ''} />
            {socketConnected ? 'Real-Time Stream Active' : 'Offline / Polling'}
          </span>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsPaused(!isPaused)}
            className={`text-xs ${isPaused ? 'border-amber-500 text-amber-500' : ''}`}
          >
            {isPaused ? <Play size={13} className="mr-1.5" /> : <Pause size={13} className="mr-1.5" />}
            {isPaused ? 'Resume Feed' : 'Pause Stream'}
          </Button>

          <Button variant="ghost" size="sm" onClick={() => loadInitialData(true)} className="text-xs">
            <RefreshCw size={13} className="mr-1.5" /> Refresh
          </Button>

          {logs.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearLogs} className="text-xs text-rose-500 hover:text-rose-600">
              <Trash2 size={13} className="mr-1.5" /> Clear
            </Button>
          )}
        </div>
      </div>

      {/* Live KPI Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Monitored Students</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{activeStudentsCount}</p>
          <span className="text-[11px] text-emerald-500 font-medium">Active In Telemetry</span>
        </div>
        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Total Streamed Events</p>
          <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-1">{logsForSession.length}</p>
          <span className="text-[11px] text-slate-400">Buffered In Session</span>
        </div>
        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Policy Violations</p>
          <p className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-1">{violationCount}</p>
          <span className="text-[11px] text-rose-500 font-medium">Blocked Processes/Web</span>
        </div>
        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Stream Status</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="h-3 w-3 rounded-full bg-emerald-500 animate-ping"></span>
            <p className="text-base font-bold text-slate-900 dark:text-white">
              {isPaused ? 'Paused' : 'Listening'}
            </p>
          </div>
          <span className="text-[11px] text-slate-400">Zero-latency WebSocket</span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="w-56">
            <Select
              label=""
              options={[
                { value: '', label: 'All Active Sessions' },
                ...sessions.map((s) => ({ value: s._id, label: s.title })),
              ]}
              value={selectedSessionId}
              onChange={(e) => setSelectedSessionId(e.target.value)}
              className="mb-0 text-xs"
            />
          </div>

          <div className="flex items-center bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl border border-slate-200 dark:border-slate-700/60 text-xs">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                statusFilter === 'all'
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              All Events ({logsForSession.length})
            </button>
            <button
              onClick={() => setStatusFilter('violations')}
              className={`px-3 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 ${
                statusFilter === 'violations'
                  ? 'bg-rose-500/20 text-rose-300 shadow-xs'
                  : 'text-slate-500 hover:text-rose-400'
              }`}
            >
              <ShieldAlert size={12} /> Violations ({violationCount})
            </button>
            <button
              onClick={() => setStatusFilter('allowed')}
              className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                statusFilter === 'allowed'
                  ? 'bg-emerald-500/20 text-emerald-300 shadow-xs'
                  : 'text-slate-500 hover:text-emerald-400'
              }`}
            >
              Allowed ({Math.max(0, logsForSession.length - violationCount)})
            </button>
          </div>
        </div>

        <div className="relative w-full sm:w-64">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search student, app, domain..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {error && <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>}

      {/* Telemetry Stream Table */}
      <Card noPadding>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700/80 text-xs font-semibold uppercase text-slate-500 tracking-wider">
              <tr>
                <th className="px-6 py-3.5">Timestamp</th>
                <th className="px-6 py-3.5">Student</th>
                <th className="px-6 py-3.5">Resource / Process</th>
                <th className="px-6 py-3.5">Enforcement Status</th>
                <th className="px-6 py-3.5">Engagement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 bg-white dark:bg-slate-900">
              {filteredLogs.map((log) => {
                const isRecent = log._id === recentLogId;
                const score = log.engagementScore ?? (log.isViolation ? 30 : 85);

                return (
                  <tr
                    key={log._id}
                    className={`transition-all duration-300 ${
                      isRecent
                        ? 'bg-indigo-500/15 dark:bg-indigo-500/25 ring-1 ring-indigo-500/50'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'
                    }`}
                  >
                    <td className="px-6 py-3.5 font-mono text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <Clock size={12} className="text-slate-400 shrink-0" />
                        <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                      </div>
                    </td>

                    <td className="px-6 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-xs">
                          {(log.studentName || 'S').charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-900 dark:text-white text-xs leading-tight">
                            {log.studentName || 'Student'}
                          </p>
                          {log.details && (
                            <p className="text-[11px] text-slate-400 truncate max-w-xs">{log.details}</p>
                          )}
                        </div>
                      </div>
                    </td>

                    <td className="px-6 py-3.5">
                      {renderResourceBadge(log.resource, log.isViolation)}
                    </td>

                    <td className="px-6 py-3.5">
                      {log.isViolation ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20">
                          <ShieldAlert size={13} /> Blocked / Terminated
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                          <CheckCircle size={13} /> Allowed
                        </span>
                      )}
                    </td>

                    <td className="px-6 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="w-20 bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              score >= 80 ? 'bg-emerald-500' : score >= 50 ? 'bg-amber-500' : 'bg-rose-500'
                            }`}
                            style={{ width: `${Math.max(8, Math.min(100, score))}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono font-bold text-slate-700 dark:text-slate-300">
                          {score}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {filteredLogs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-slate-400 space-y-2">
                    <Laptop size={32} className="mx-auto text-slate-500 opacity-60" />
                    <p className="font-medium text-slate-300 text-sm">No activity logs recorded</p>
                    <p className="text-xs text-slate-500">
                      {socketConnected
                        ? 'Live WebSocket connected — logs will appear here automatically when students perform actions.'
                        : 'Waiting for WebSocket reconnection...'}
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
