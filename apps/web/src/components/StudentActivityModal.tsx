import React, { useEffect, useState, useMemo } from 'react';
import {
  X,
  Monitor,
  Globe,
  ShieldAlert,
  Clock,
  Search,
  Filter,
  RefreshCw,
  Loader2,
  AlertCircle,
  Activity
} from 'lucide-react';
import { getStudentActivity, getStudentActivitySummary, getSessions } from '../lib/api';
import { getSocket } from '../lib/socket';
import { ActivityEvent, ActivitySummary, Session } from '../types';

interface StudentActivityModalProps {
  isOpen: boolean;
  onClose: () => void;
  student: {
    studentId: string;
    studentName: string;
    sapId: string;
    activeApp: string;
    status: 'online' | 'idle' | 'offline';
    engagementScore: number;
    isViolation: boolean;
  };
  sessionId: string;
  sessionTitle: string;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return '<1s';
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

const presenceConfig = {
  online: { color: 'bg-emerald-500', label: 'Online', text: 'text-emerald-600 dark:text-emerald-400' },
  idle: { color: 'bg-amber-500', label: 'Idle', text: 'text-amber-600 dark:text-amber-400' },
  offline: { color: 'bg-slate-400', label: 'Offline', text: 'text-slate-500 dark:text-slate-400' },
};

export default function StudentActivityModal({
  isOpen,
  onClose,
  student,
  sessionId,
  sessionTitle
}: StudentActivityModalProps) {
  const [activeTab, setActiveTab] = useState<'timeline' | 'websites' | 'applications'>('timeline');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [summary, setSummary] = useState<ActivitySummary | null>(null);

  const [selectedSessionId, setSelectedSessionId] = useState<string>(sessionId);
  const [availableSessions, setAvailableSessions] = useState<Session[]>([]);

  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const [webSearch, setWebSearch] = useState('');
  const [webStatusFilter, setWebStatusFilter] = useState<'All' | 'ALLOWED' | 'BLOCKED'>('All');
  const [webSortBy, setWebSortBy] = useState<'domain' | 'duration' | 'firstSeen' | 'lastSeen' | 'blocks'>('duration');
  const [webSortDesc, setWebSortDesc] = useState(true);

  const loadData = async (offset = 0, isRefresh = false, targetSessionId = selectedSessionId) => {
    if (offset === 0 && !isRefresh) setIsLoading(true);
    if (!isRefresh) setError(null);
    try {
      const activeSessionParam = targetSessionId || undefined;
      const [acts, sum] = await Promise.all([
        getStudentActivity(student.studentId, activeSessionParam, 200, offset),
        getStudentActivitySummary(student.studentId, activeSessionParam)
      ]);
      if (offset === 0) {
        setActivities(acts);
      } else {
        setActivities(prev => [...prev, ...acts]);
      }
      setSummary(sum);
      setHasMore(acts.length === 200);
      setPage(Math.floor(offset / 200));
    } catch (err: any) {
      if (!isRefresh) setError(err.message || 'Failed to load activity');
    } finally {
      if (!isRefresh) setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    getSessions().then(sessions => {
      setAvailableSessions(sessions);
    }).catch(console.error);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    loadData(0, false, selectedSessionId);

    const socket = getSocket();
    const onUpdate = (data: any) => {
      if (
        (data?.studentId === student.studentId || data?.sapId === student.sapId) &&
        (!selectedSessionId || data?.sessionId === selectedSessionId)
      ) {
        loadData(0, true, selectedSessionId);
      }
    };

    socket.on('student_activity_update', onUpdate);

    // Live continuous stream: silently refresh every 3 seconds while open
    const liveTimer = setInterval(() => {
      loadData(0, true, selectedSessionId);
    }, 3000);

    return () => {
      socket.off('student_activity_update', onUpdate);
      clearInterval(liveTimer);
    };
  }, [isOpen, student.studentId, student.sapId, selectedSessionId]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  // Aggregate Websites
  const websiteStats = useMemo(() => {
    const map = new Map<string, {
      domain: string;
      status: string;
      durationMs: number;
      firstSeen: number;
      lastSeen: number;
      blockEvents: number;
    }>();
    
    for (const act of activities) {
      if (!act.domain) continue;
      const t = new Date(act.startedAt).getTime();
      const existing = map.get(act.domain);
      const isBlocked = act.status === 'BLOCKED' || act.eventType === 'DOMAIN_BLOCKED';
      if (!existing) {
        map.set(act.domain, {
          domain: act.domain,
          status: act.status,
          durationMs: act.durationMs || 0,
          firstSeen: t,
          lastSeen: t,
          blockEvents: isBlocked ? 1 : 0
        });
      } else {
        existing.durationMs += act.durationMs || 0;
        existing.firstSeen = Math.min(existing.firstSeen, t);
        existing.lastSeen = Math.max(existing.lastSeen, t);
        if (isBlocked) existing.blockEvents += 1;
        // if any event is allowed, mark as overall allowed? We'll just keep the first or latest.
        if (act.status === 'ALLOWED') existing.status = 'ALLOWED';
      }
    }
    
    let list = Array.from(map.values());
    if (webSearch) {
      list = list.filter(w => w.domain.toLowerCase().includes(webSearch.toLowerCase()));
    }
    if (webStatusFilter !== 'All') {
      list = list.filter(w => w.status === webStatusFilter);
    }
    
    list.sort((a, b) => {
      let cmp = 0;
      if (webSortBy === 'domain') cmp = a.domain.localeCompare(b.domain);
      else if (webSortBy === 'duration') cmp = a.durationMs - b.durationMs;
      else if (webSortBy === 'firstSeen') cmp = a.firstSeen - b.firstSeen;
      else if (webSortBy === 'lastSeen') cmp = a.lastSeen - b.lastSeen;
      else if (webSortBy === 'blocks') cmp = a.blockEvents - b.blockEvents;
      return webSortDesc ? -cmp : cmp;
    });
    return list;
  }, [activities, webSearch, webStatusFilter, webSortBy, webSortDesc]);

  // Aggregate Applications
  const appStats = useMemo(() => {
    const map = new Map<string, { app: string; durationMs: number; firstSeen: number; lastSeen: number }>();
    for (const act of activities) {
      if (!act.application) continue;
      const t = new Date(act.startedAt).getTime();
      const existing = map.get(act.application);
      if (!existing) {
        map.set(act.application, {
          app: act.application,
          durationMs: act.durationMs || 0,
          firstSeen: t,
          lastSeen: t
        });
      } else {
        existing.durationMs += act.durationMs || 0;
        existing.firstSeen = Math.min(existing.firstSeen, t);
        existing.lastSeen = Math.max(existing.lastSeen, t);
      }
    }
    return Array.from(map.values()).sort((a, b) => b.durationMs - a.durationMs);
  }, [activities]);


  if (!isOpen) return null;
  const presence = presenceConfig[student.status];

  return (
    <div className="fixed inset-0 z-[60] flex flex-col animate-fade-in">
      <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-md" onClick={onClose} />
      <div className="relative flex-1 flex flex-col m-3 md:m-8 lg:mx-auto lg:w-full lg:max-w-6xl bg-white dark:bg-[#0c0f1a] rounded-2xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-800">
        
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#151929]/50">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="h-12 w-12 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center text-white font-bold text-lg shadow-sm">
                {student.studentName.charAt(0).toUpperCase()}
              </div>
              <span className={`absolute -bottom-0.5 -right-0.5 h-4 w-4 rounded-full ${presence.color} ring-2 ring-white dark:ring-[#0c0f1a]`} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white leading-tight">
                {student.studentName}
              </h2>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-xs text-slate-500 dark:text-slate-400 font-mono">
                  {student.sapId}
                </span>
                <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 ${presence.text}`}>
                  {presence.label}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <select
                value={selectedSessionId}
                onChange={(e) => setSelectedSessionId(e.target.value)}
                className="text-xs sm:text-sm font-medium py-1.5 px-3 pr-8 bg-slate-100 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 appearance-none cursor-pointer"
              >
                <option value={sessionId}>{sessionTitle} (Current Session)</option>
                <option value="">All Sessions</option>
                {availableSessions
                  .filter(s => s._id !== sessionId)
                  .map(s => (
                    <option key={s._id} value={s._id}>{s.title}</option>
                  ))}
              </select>
            </div>
            <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto bg-white dark:bg-[#0c0f1a] p-6">
          {isLoading && !activities.length ? (
            <div className="flex flex-col items-center justify-center h-64 text-indigo-500">
              <Loader2 size={32} className="animate-spin mb-4" />
              <p className="text-slate-500 dark:text-slate-400">Loading activity...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-64 text-rose-500">
              <AlertCircle size={32} className="mb-4" />
              <p className="font-medium">{error}</p>
              <button onClick={() => loadData(0, true)} className="mt-4 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg flex items-center gap-2">
                <RefreshCw size={16} /> Retry
              </button>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                <div className="p-4 bg-slate-50 dark:bg-dark-card rounded-xl border border-slate-100 dark:border-slate-800 flex items-center gap-4">
                  <div className="p-3 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-lg">
                    <Clock size={20} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Total Observed</p>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">
                      {summary ? formatDuration(summary.totalActiveMs) : '0s'}
                    </p>
                  </div>
                </div>
                <div className="p-4 bg-slate-50 dark:bg-dark-card rounded-xl border border-slate-100 dark:border-slate-800 flex items-center gap-4">
                  <div className="p-3 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-lg">
                    <Globe size={20} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Allowed Domains</p>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">
                      {summary?.allowedDomains || 0}
                    </p>
                  </div>
                </div>
                <div className="p-4 bg-slate-50 dark:bg-dark-card rounded-xl border border-slate-100 dark:border-slate-800 flex items-center gap-4">
                  <div className="p-3 bg-rose-100 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400 rounded-lg">
                    <ShieldAlert size={20} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Blocked Attempts</p>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">
                      {summary?.blockedAttempts || 0}
                    </p>
                  </div>
                </div>
                <div className="p-4 bg-slate-50 dark:bg-dark-card rounded-xl border border-slate-100 dark:border-slate-800 flex items-center gap-4">
                  <div className="p-3 bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 rounded-lg">
                    <Monitor size={20} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Apps Used</p>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">
                      {summary?.uniqueApps || 0}
                    </p>
                  </div>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex border-b border-slate-200 dark:border-slate-800 mb-6">
                <button
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'timeline' ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'}`}
                  onClick={() => setActiveTab('timeline')}
                >
                  Timeline
                </button>
                <button
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'websites' ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'}`}
                  onClick={() => setActiveTab('websites')}
                >
                  Websites
                </button>
                <button
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'applications' ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'}`}
                  onClick={() => setActiveTab('applications')}
                >
                  Applications
                </button>
              </div>

              {/* Tab Content */}
              {activities.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                  <Activity size={48} className="mb-4 opacity-40" />
                  <p className="text-sm font-medium">No activity recorded for this session.</p>
                </div>
              ) : (
                <div className="min-h-[400px]">
                  {/* TIMELINE */}
                  {activeTab === 'timeline' && (
                    <div className="space-y-4">
                      {activities.map((act) => (
                        <div key={act._id} className="flex items-start gap-4 p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-dark-card hover:border-slate-200 dark:hover:border-slate-700 transition-colors">
                          <div className={`p-2 rounded-lg shrink-0 ${act.status === 'BLOCKED' ? 'bg-rose-100 dark:bg-rose-500/20 text-rose-600' : act.domain ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600' : 'bg-blue-100 dark:bg-blue-500/20 text-blue-600'}`}>
                            {act.status === 'BLOCKED' ? <ShieldAlert size={18} /> : act.domain ? <Globe size={18} /> : <Monitor size={18} />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <p className="font-semibold text-slate-900 dark:text-white truncate">
                                {act.title || act.domain || act.application}
                              </p>
                              {act.status === 'BLOCKED' ? (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400">BLOCKED</span>
                              ) : (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400">ALLOWED</span>
                              )}
                            </div>
                            <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                              <span>{act.application}</span>
                              {act.domain && <span className="font-mono">{act.domain}</span>}
                              <span>{formatDuration(act.durationMs || 0)}</span>
                            </div>
                          </div>
                          <div className="shrink-0 text-xs text-slate-400 whitespace-nowrap font-mono">
                            {new Date(act.startedAt).toLocaleTimeString()}
                          </div>
                        </div>
                      ))}
                      {hasMore && (
                        <button
                          onClick={() => loadData((page + 1) * 200)}
                          disabled={isLoading}
                          className="w-full py-3 text-sm font-medium text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 rounded-xl transition-colors border border-dashed border-indigo-200 dark:border-indigo-800 disabled:opacity-50"
                        >
                          {isLoading ? 'Loading...' : 'Load Older Activity'}
                        </button>
                      )}
                    </div>
                  )}

                  {/* WEBSITES */}
                  {activeTab === 'websites' && (
                    <div className="flex flex-col h-full">
                      <div className="flex flex-col sm:flex-row gap-3 mb-4">
                        <div className="relative flex-1">
                          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                          <input
                            type="text"
                            placeholder="Search domains..."
                            value={webSearch}
                            onChange={(e) => setWebSearch(e.target.value)}
                            className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                        </div>
                        <div className="relative w-full sm:w-48 shrink-0">
                          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                          <select
                            value={webStatusFilter}
                            onChange={(e) => setWebStatusFilter(e.target.value as any)}
                            className="w-full pl-9 pr-8 py-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 appearance-none"
                          >
                            <option value="All">All Statuses</option>
                            <option value="ALLOWED">Allowed</option>
                            <option value="BLOCKED">Blocked</option>
                          </select>
                        </div>
                      </div>
                      
                      <div className="bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="w-full text-left border-collapse">
                            <thead>
                              <tr className="bg-slate-50 dark:bg-[#151929] border-b border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                <th className="px-6 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => { setWebSortBy('domain'); setWebSortDesc(!webSortDesc); }}>
                                  Domain {webSortBy === 'domain' && (webSortDesc ? '↓' : '↑')}
                                </th>
                                <th className="px-6 py-3">Status</th>
                                <th className="px-6 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => { setWebSortBy('duration'); setWebSortDesc(!webSortDesc); }}>
                                  Duration {webSortBy === 'duration' && (webSortDesc ? '↓' : '↑')}
                                </th>
                                <th className="px-6 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => { setWebSortBy('blocks'); setWebSortDesc(!webSortDesc); }}>
                                  Blocks {webSortBy === 'blocks' && (webSortDesc ? '↓' : '↑')}
                                </th>
                                <th className="px-6 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => { setWebSortBy('firstSeen'); setWebSortDesc(!webSortDesc); }}>
                                  First Seen {webSortBy === 'firstSeen' && (webSortDesc ? '↓' : '↑')}
                                </th>
                                <th className="px-6 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => { setWebSortBy('lastSeen'); setWebSortDesc(!webSortDesc); }}>
                                  Last Seen {webSortBy === 'lastSeen' && (webSortDesc ? '↓' : '↑')}
                                </th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                              {websiteStats.map(w => (
                                <tr key={w.domain} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                  <td className="px-6 py-3 font-mono text-sm text-slate-900 dark:text-slate-200">{w.domain}</td>
                                  <td className="px-6 py-3">
                                    {w.status === 'BLOCKED' ? (
                                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400">BLOCKED</span>
                                    ) : (
                                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400">ALLOWED</span>
                                    )}
                                  </td>
                                  <td className="px-6 py-3 text-sm text-slate-600 dark:text-slate-400">{formatDuration(w.durationMs)}</td>
                                  <td className="px-6 py-3 text-sm text-rose-500">{w.blockEvents > 0 ? w.blockEvents : '-'}</td>
                                  <td className="px-6 py-3 text-sm text-slate-500 font-mono">{new Date(w.firstSeen).toLocaleTimeString()}</td>
                                  <td className="px-6 py-3 text-sm text-slate-500 font-mono">{new Date(w.lastSeen).toLocaleTimeString()}</td>
                                </tr>
                              ))}
                              {websiteStats.length === 0 && (
                                <tr>
                                  <td colSpan={6} className="px-6 py-8 text-center text-slate-500">No websites match filters.</td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* APPLICATIONS */}
                  {activeTab === 'applications' && (
                    <div className="bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                          <thead>
                            <tr className="bg-slate-50 dark:bg-[#151929] border-b border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                              <th className="px-6 py-3">Application</th>
                              <th className="px-6 py-3">Observed Duration</th>
                              <th className="px-6 py-3">First Seen</th>
                              <th className="px-6 py-3">Last Seen</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                            {appStats.map(a => (
                              <tr key={a.app} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                <td className="px-6 py-3 font-medium text-sm text-slate-900 dark:text-slate-200 flex items-center gap-2">
                                  <Monitor size={14} className="text-slate-400" />
                                  {a.app}
                                </td>
                                <td className="px-6 py-3 text-sm text-slate-600 dark:text-slate-400">{formatDuration(a.durationMs)}</td>
                                <td className="px-6 py-3 text-sm text-slate-500 font-mono">{new Date(a.firstSeen).toLocaleTimeString()}</td>
                                <td className="px-6 py-3 text-sm text-slate-500 font-mono">{new Date(a.lastSeen).toLocaleTimeString()}</td>
                              </tr>
                            ))}
                            {appStats.length === 0 && (
                              <tr>
                                <td colSpan={4} className="px-6 py-8 text-center text-slate-500">No applications recorded.</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
