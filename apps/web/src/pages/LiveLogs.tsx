import React, { useEffect, useState } from 'react';
import { Card } from '../components/ui/Card';
import { Activity, Wifi, ShieldAlert, CheckCircle, Loader2 as Spinner } from 'lucide-react';
import { LogEntry, Session } from '../types';
import { getLogs, getSessions } from '../lib/api';

export const LiveLogs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadLiveLogs() {
    try {
      const sessions: Session[] = await getSessions();
      const activeSessionIds = new Set(
        sessions
          .filter((session) => String(session.status).toLowerCase() === 'active')
          .map((session) => session._id)
      );

      if (activeSessionIds.size === 0) {
        setLogs([]);
        setError('');
        setLoading(false);
        return;
      }

      const allLogs = await getLogs();
      const activeLogs = allLogs
        .filter((log) => activeSessionIds.has(String(log.sessionId)))
        .sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp))
        .slice(0, 50);

      setLogs(activeLogs);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load live logs.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLiveLogs();
    const interval = setInterval(loadLiveLogs, 5000);
    return () => clearInterval(interval);
  }, []);

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
            <Wifi className="text-red-500 animate-pulse" /> Live Session Monitor
          </h1>
          <p className="text-slate-500 dark:text-slate-400">Real-time telemetry from active student sessions.</p>
        </div>
        <div className="flex gap-2 text-sm">
          <span className="px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full border border-emerald-100 flex items-center gap-1">
            <Activity size={14} /> Monitoring Active
          </span>
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
                        className={`${(log.engagementScore || 0) > 85 ? 'bg-emerald-500' : 'bg-amber-500'} h-full`}
                        style={{ width: `${Math.max(5, log.engagementScore || 0)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400 italic">
                    Waiting for live data from active sessions...
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
