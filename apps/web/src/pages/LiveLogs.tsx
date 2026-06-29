import React, { useEffect, useRef, useState } from 'react';
import { Card } from '../components/ui/Card';
import { Activity, Wifi, WifiOff, ShieldAlert, CheckCircle, Loader2 as Spinner, Trash2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { LogEntry, Session } from '../types';
import { getLogs, getSessions } from '../lib/api';
import { getSocket, joinLiveLogs } from '../lib/socket';

const MAX_VISIBLE_LOGS = 100;

export const LiveLogs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [socketConnected, setSocketConnected] = useState(false);
  const activeSessionIdsRef = useRef<Set<string>>(new Set());

  // Load active session IDs and initial logs via REST
  async function loadInitialData() {
    try {
      const sessions: Session[] = await getSessions();
      const activeIds = new Set(
        sessions
          .filter((session) => String(session.status).toLowerCase() === 'active')
          .map((session) => session._id)
      );
      activeSessionIdsRef.current = activeIds;

      if (activeIds.size === 0) {
        setLogs([]);
        setError('');
        setLoading(false);
        return;
      }

      const allLogs = await getLogs();
      const activeLogs = allLogs
        .filter((log) => activeIds.has(String(log.sessionId)))
        .sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp))
        .slice(0, MAX_VISIBLE_LOGS);

      setLogs(activeLogs);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load live logs.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInitialData();

    // Connect WebSocket and join the live_logs broadcast room
    const socket = getSocket();
    joinLiveLogs();

    const onConnect = () => setSocketConnected(true);
    const onDisconnect = () => setSocketConnected(false);

    const onLiveLogUpdate = (data: any) => {
      const newLog: LogEntry = {
        _id: data._id || `ws-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: data.type || 'EVENT',
        studentId: data.studentId || '',
        studentName: data.studentName || 'Unknown',
        sessionId: data.sessionId || '',
        resource: data.resource || '',
        details: data.details || '',
        duration: data.duration,
        engagementScore: data.engagementScore,
        isViolation: Boolean(data.isViolation),
        timestamp: data.timestamp || new Date().toISOString(),
      };

      setLogs((prev) => {
        // Deduplicate by _id
        if (prev.some((log) => log._id === newLog._id)) {
          return prev;
        }
        const updated = [newLog, ...prev].slice(0, MAX_VISIBLE_LOGS);
        return updated;
      });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('live_log_update', onLiveLogUpdate);

    if (socket.connected) {
      setSocketConnected(true);
    }

    // Periodic refresh of session IDs (to detect newly activated sessions)
    const sessionRefresh = setInterval(async () => {
      try {
        const sessions: Session[] = await getSessions();
        const activeIds = new Set(
          sessions
            .filter((s) => String(s.status).toLowerCase() === 'active')
            .map((s) => s._id)
        );
        activeSessionIdsRef.current = activeIds;
      } catch {
        // Ignore — just keep existing session IDs
      }
    }, 30000);

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('live_log_update', onLiveLogUpdate);
      clearInterval(sessionRefresh);
    };
  }, []);

  const clearLogs = () => setLogs([]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            {socketConnected ? (
              <Wifi className="text-emerald-500 animate-pulse" />
            ) : (
              <WifiOff className="text-red-500" />
            )}
            Live Session Monitor
          </h1>
          <p className="text-slate-500 dark:text-slate-400">
            {socketConnected
              ? 'Real-time telemetry via WebSocket — logs appear instantly.'
              : 'WebSocket disconnected — waiting for reconnection...'}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <span
            className={`px-3 py-1 rounded-full border flex items-center gap-1 text-sm ${
              socketConnected
                ? 'bg-emerald-50 text-emerald-600 border-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800'
                : 'bg-red-50 text-red-600 border-red-100 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800'
            }`}
          >
            <Activity size={14} />
            {socketConnected ? 'Live' : 'Offline'}
          </span>
          <span className="px-3 py-1 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 rounded-full text-sm border border-slate-200 dark:border-slate-700">
            {logs.length} entries
          </span>
          {logs.length > 0 && (
            <Button variant="ghost" onClick={clearLogs} className="text-xs">
              <Trash2 size={14} className="mr-1" /> Clear
            </Button>
          )}
        </div>
      </div>

      {error && <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>}

      <Card noPadding>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="px-6 py-3 font-medium text-slate-500">Timestamp</th>
                <th className="px-6 py-3 font-medium text-slate-500">Student</th>
                <th className="px-6 py-3 font-medium text-slate-500">Activity</th>
                <th className="px-6 py-3 font-medium text-slate-500">Status</th>
                <th className="px-6 py-3 font-medium text-slate-500">Engagement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {logs.map((log) => (
                <tr key={log._id} className="animate-fade-in">
                  <td className="px-6 py-3 font-mono text-slate-500 text-xs">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="px-6 py-3 font-medium text-slate-900 dark:text-white">{log.studentName}</td>
                  <td className="px-6 py-3 text-slate-600 dark:text-slate-400">
                    <span className="font-mono text-xs bg-slate-100 dark:bg-slate-700 px-1 rounded">{log.resource || 'N/A'}</span>
                  </td>
                  <td className="px-6 py-3">
                    {log.isViolation ? (
                      <span className="flex items-center gap-1 text-red-600 text-xs font-medium">
                        <ShieldAlert size={14} /> Blocked
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-emerald-600 text-xs font-medium">
                        <CheckCircle size={14} /> Allowed
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3">
                    <div className="w-24 bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`${(log.engagementScore || 0) > 85 ? 'bg-emerald-500' : 'bg-amber-500'} h-full transition-all duration-300`}
                        style={{ width: `${Math.max(5, log.engagementScore || 0)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400 italic">
                    {socketConnected
                      ? 'Connected — waiting for live data from active sessions...'
                      : 'No active sessions or WebSocket is disconnected.'}
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
