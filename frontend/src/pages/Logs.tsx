import React, { useEffect, useMemo, useState } from 'react';
import { Card } from '../components/ui/Card';
import { Select } from '../components/ui/Input';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import {
  Search,
  AlertTriangle,
  CheckCircle,
  Loader2 as Spinner,
  ShieldAlert,
  Activity,
  BarChart3,
  Clock,
  TrendingUp,
  RefreshCw,
  Globe,
  AppWindow,
  Usb,
  Users,
  Monitor,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
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

export const Logs: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'violations' | 'allowed'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadSessionsAndLogs(silent = false) {
    try {
      if (!silent) setLoading(true);
      const [sessionsData, logsData] = await Promise.all([
        getSessions().catch(() => []),
        getLogs(selectedSessionId || undefined).catch(() => []),
      ]);

      setSessions(sessionsData || []);
      setLogs(logsData || []);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load activity logs & analytics.');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function handleSessionChange(sessionId: string) {
    setSelectedSessionId(sessionId);
    try {
      setLoading(true);
      const data = await getLogs(sessionId || undefined);
      setLogs(data || []);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load logs for selected session.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSessionsAndLogs();

    // Connect to WebSockets for real-time analytics updates
    const socket = getSocket();
    joinLiveLogs();
    if (selectedSessionId) {
      joinSession(selectedSessionId);
    }

    const onLiveLogUpdate = (data: any) => {
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

      setLogs((prev) => {
        if (prev.some((log) => log._id === newLog._id || (log.studentId === newLog.studentId && log.resource === newLog.resource && Math.abs(new Date(log.timestamp).getTime() - new Date(newLog.timestamp).getTime()) < 3000))) {
          return prev;
        }
        return [newLog, ...prev];
      });
    };

    const onPolicyViolation = (viol: any) => {
      if (!viol) return;
      onLiveLogUpdate({
        ...viol,
        type: 'VIOLATION',
        isViolation: true,
        resource: viol.target_value || viol.resource || viol.domain || 'Restricted Resource',
        action: viol.action_taken || viol.action || 'Blocked',
        details: viol.details || `Restricted Access: ${viol.target_value || viol.resource || viol.domain || 'Resource'} (Blocked)`,
      });
    };

    socket.on('live_log_update', onLiveLogUpdate);
    socket.on('student_telemetry', onLiveLogUpdate);
    socket.on('policy_violation', onPolicyViolation);

    const interval = setInterval(() => {
      loadSessionsAndLogs(true);
    }, 10000);

    return () => {
      if (selectedSessionId) {
        leaveSessionRoom(selectedSessionId);
      }
      socket.off('live_log_update', onLiveLogUpdate);
      socket.off('student_telemetry', onLiveLogUpdate);
      socket.off('policy_violation', onPolicyViolation);
      clearInterval(interval);
    };
  }, [selectedSessionId]);

  const activeSessionLogs = useMemo(() => {
    if (!selectedSessionId) return logs;
    return logs.filter((log) => !log.sessionId || log.sessionId === selectedSessionId);
  }, [logs, selectedSessionId]);

  const filteredLogs = useMemo(() => {
    return activeSessionLogs.filter((log) => {
      if (statusFilter === 'violations' && !log.isViolation) return false;
      if (statusFilter === 'allowed' && log.isViolation) return false;

      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase();
        const student = (log.studentName || '').toLowerCase();
        const resource = (log.resource || '').toLowerCase();
        const details = (log.details || '').toLowerCase();
        return student.includes(term) || resource.includes(term) || details.includes(term);
      }
      return true;
    });
  }, [activeSessionLogs, statusFilter, searchTerm]);

  // Analytics Metrics
  const avgEngagement = useMemo(() => {
    if (activeSessionLogs.length === 0) return 0;
    const sum = activeSessionLogs.reduce((acc, log) => acc + (log.engagementScore ?? (log.isViolation ? 30 : 85)), 0);
    return Math.round(sum / activeSessionLogs.length);
  }, [activeSessionLogs]);

  const totalViolations = useMemo(() => activeSessionLogs.filter((l) => l.isViolation).length, [activeSessionLogs]);

  const engagementData = useMemo(() => {
    if (activeSessionLogs.length === 0) {
      return [
        { name: 'High Engagement (≥80%)', value: 0, color: '#10b981' },
        { name: 'Moderate (50-79%)', value: 0, color: '#f59e0b' },
        { name: 'Low / Distracted (<50%)', value: 0, color: '#ef4444' },
      ];
    }

    const high = activeSessionLogs.filter((log) => (log.engagementScore ?? (log.isViolation ? 30 : 85)) >= 80).length;
    const moderate = activeSessionLogs.filter((log) => {
      const s = log.engagementScore ?? (log.isViolation ? 30 : 85);
      return s >= 50 && s < 80;
    }).length;
    const low = activeSessionLogs.length - high - moderate;

    const toPercent = (count: number) => Math.round((count / activeSessionLogs.length) * 100);

    return [
      { name: 'High Engagement (≥80%)', value: toPercent(high), count: high, color: '#10b981' },
      { name: 'Moderate (50-79%)', value: toPercent(moderate), count: moderate, color: '#f59e0b' },
      { name: 'Low / Distracted (<50%)', value: toPercent(low), count: low, color: '#ef4444' },
    ];
  }, [activeSessionLogs]);

  const usageData = useMemo(() => {
    const isNonResource = (res: string) => {
      if (!res) return true;
      const l = res.trim().toLowerCase();
      return (
        l.includes('joined') ||
        l.includes('left') ||
        l.includes('session status') ||
        l.includes('session room') ||
        l.includes('policy enforcement') ||
        l === 'policy_restored' ||
        l === 'policy restored' ||
        l === 'system' ||
        l === 'unknown' ||
        l === 'workspace' ||
        l === 'active portal' ||
        l === 'application_access' ||
        l === 'heartbeat' ||
        l === 'state_transition' ||
        l === 'policy_delivered' ||
        l === 'policy_acknowledged'
      );
    };

    const usageMap = activeSessionLogs.reduce((acc: Record<string, number>, log: LogEntry) => {
      const resourceKey = (log.resource || '').trim();
      if (!resourceKey || isNonResource(resourceKey)) {
        return acc;
      }
      acc[resourceKey] = (acc[resourceKey] || 0) + (log.duration || 60);
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(usageMap as Record<string, number>)
      .map(([site, time]) => ({
        site: site.length > 20 ? site.slice(0, 18) + '...' : site,
        minutes: Math.max(1, Math.round(Number(time) / 60)),
      }))
      .sort((a, b) => b.minutes - a.minutes)
      .slice(0, 6);
  }, [activeSessionLogs]);

  if (loading && logs.length === 0) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <BarChart3 className="text-indigo-500" size={24} />
            Activity Logs & Analytics
          </h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            Live behavioral analytics, policy enforcement stats, and audit telemetry.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-64">
            <Select
              label=""
              options={[
                { value: '', label: 'All Sessions' },
                ...sessions.map((session) => ({ value: session._id, label: session.title })),
              ]}
              value={selectedSessionId}
              onChange={(e) => handleSessionChange(e.target.value)}
              className="mb-0 text-xs"
            />
          </div>

          <Button variant="outline" size="sm" onClick={() => loadSessionsAndLogs(true)} className="text-xs">
            <RefreshCw size={13} className="mr-1.5" /> Refresh
          </Button>
        </div>
      </div>

      {error && <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Total Activity Events</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{activeSessionLogs.length}</p>
          <span className="text-[11px] text-emerald-500 font-medium">Real-time Ingested</span>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Average Engagement</p>
          <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-1">{avgEngagement}%</p>
          <span className="text-[11px] text-indigo-400 font-medium">Across active students</span>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Enforcement Violations</p>
          <p className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-1">{totalViolations}</p>
          <span className="text-[11px] text-rose-500 font-medium">Blocked Items</span>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs text-slate-500 dark:text-slate-400">Monitored Resources</p>
          <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">{usageData.length}</p>
          <span className="text-[11px] text-slate-400">Distinct Apps/Domains</span>
        </div>
      </div>

      {/* Analytics Visualizations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Engagement Distribution">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={engagementData}
                  innerRadius={60}
                  outerRadius={85}
                  paddingAngle={5}
                  dataKey="value"
                  cx="50%"
                  cy="50%"
                  animationDuration={800}
                >
                  {engagementData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: any, name: any) => [`${value}% (${name})`, 'Engagement']}
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '0.75rem', color: '#fff' }}
                />
                <Legend verticalAlign="bottom" height={36} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Top Resource Usage (Minutes)">
          <div className="h-64 w-full">
            {usageData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={usageData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal vertical={false} stroke="#334155" opacity={0.2} />
                  <XAxis type="number" hide />
                  <YAxis dataKey="site" type="category" width={110} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                  <Tooltip
                    formatter={(value: any) => [`${value} min`, 'Active Usage']}
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '0.75rem', color: '#fff' }}
                  />
                  <Bar dataKey="minutes" fill="#6366f1" radius={[0, 6, 6, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-400 text-sm">
                No resource usage data recorded for this session.
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Filter and Search Bar for Activity Table */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="flex items-center bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl border border-slate-200 dark:border-slate-700/60 text-xs">
          <button
            onClick={() => setStatusFilter('all')}
            className={`px-3 py-1 rounded-lg font-medium transition-colors ${
              statusFilter === 'all'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            All Logs ({activeSessionLogs.length})
          </button>
          <button
            onClick={() => setStatusFilter('violations')}
            className={`px-3 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 ${
              statusFilter === 'violations'
                ? 'bg-rose-500/20 text-rose-300 shadow-xs'
                : 'text-slate-500 hover:text-rose-400'
            }`}
          >
            <ShieldAlert size={12} /> Violations ({totalViolations})
          </button>
          <button
            onClick={() => setStatusFilter('allowed')}
            className={`px-3 py-1 rounded-lg font-medium transition-colors ${
              statusFilter === 'allowed'
                ? 'bg-emerald-500/20 text-emerald-300 shadow-xs'
                : 'text-slate-500 hover:text-emerald-400'
            }`}
          >
            Allowed ({Math.max(0, activeSessionLogs.length - totalViolations)})
          </button>
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

      {/* Detailed Activity Table */}
      <Card noPadding>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700 text-xs uppercase text-slate-500 font-semibold tracking-wider">
              <tr>
                <th className="px-6 py-3.5">Timestamp</th>
                <th className="px-6 py-3.5">Student</th>
                <th className="px-6 py-3.5">Resource / Process</th>
                <th className="px-6 py-3.5">Enforcement Status</th>
                <th className="px-6 py-3.5">Engagement Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 bg-white dark:bg-slate-900">
              {filteredLogs.map((log) => {
                const score = log.engagementScore ?? (log.isViolation ? 30 : 85);

                return (
                  <tr key={log._id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors duration-150">
                    <td className="px-6 py-4 text-xs text-slate-500 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <Clock size={12} className="text-slate-400" />
                        {new Date(log.timestamp).toLocaleString()}
                      </div>
                    </td>

                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2.5">
                        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
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

                    <td className="px-6 py-4">
                      {renderResourceBadge(log.resource, log.isViolation)}
                    </td>

                    <td className="px-6 py-4">
                      {log.isViolation ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20">
                          <AlertTriangle size={13} /> Violation (Blocked)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                          <CheckCircle size={13} /> Allowed
                        </span>
                      )}
                    </td>

                    <td className="px-6 py-4">
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
                  <td colSpan={5} className="px-6 py-10 text-center text-slate-400 italic">
                    No activity logs found for the selected session or filters.
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
