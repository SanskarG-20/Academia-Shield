import React, { useEffect, useMemo, useState } from 'react';
import { Card } from '../components/ui/Card';
import { Input, Select } from '../components/ui/Input';
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
import { Search, AlertTriangle, CheckCircle, Loader2 as Spinner } from 'lucide-react';
import { LogEntry, Session } from '../types';
import { getLogs, getSessions } from '../lib/api';

export const Logs: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadSessionsAndLogs() {
    try {
      setLoading(true);
      const sessionsData = await getSessions();
      setSessions(sessionsData);

      if (sessionsData.length > 0) {
        const firstSessionId = sessionsData[0]._id;
        setSelectedSessionId(firstSessionId);
        const logsData = await getLogs(firstSessionId);
        setLogs(logsData);
      } else {
        setLogs([]);
      }

      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load logs.');
    } finally {
      setLoading(false);
    }
  }

  async function loadLogsBySession(sessionId: string) {
    try {
      setLoading(true);
      const data = sessionId ? await getLogs(sessionId) : await getLogs();
      setLogs(data);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load logs for selected session.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSessionsAndLogs();
  }, []);

  const filteredLogs = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return logs;

    return logs.filter((log) => {
      const student = log.studentName?.toLowerCase() || '';
      const resource = log.resource?.toLowerCase() || '';
      const details = log.details?.toLowerCase() || '';
      return student.includes(term) || resource.includes(term) || details.includes(term);
    });
  }, [logs, searchTerm]);

  const engagementData = useMemo(() => {
    if (logs.length === 0) {
      return [
        { name: 'High Engagement', value: 0, color: '#10b981' },
        { name: 'Moderate', value: 0, color: '#f59e0b' },
        { name: 'Low/Distracted', value: 0, color: '#ef4444' },
      ];
    }

    const high = logs.filter((log) => (log.engagementScore || 0) >= 80).length;
    const moderate = logs.filter((log) => {
      const score = log.engagementScore || 0;
      return score >= 50 && score < 80;
    }).length;
    const low = logs.length - high - moderate;

    const toPercent = (count: number) => Math.round((count / logs.length) * 100);

    return [
      { name: 'High Engagement', value: toPercent(high), color: '#10b981' },
      { name: 'Moderate', value: toPercent(moderate), color: '#f59e0b' },
      { name: 'Low/Distracted', value: toPercent(low), color: '#ef4444' },
    ];
  }, [logs]);

  const usageData = useMemo(() => {
    const usageMap = logs.reduce((acc: Record<string, number>, log: LogEntry) => {
      const resourceKey = log.resource || 'unknown';
      acc[resourceKey] = (acc[resourceKey] || 0) + (log.duration || 1);
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(usageMap as Record<string, number>)
      .map(([site, time]) => ({ site, time: Math.max(1, Math.round(Number(time) / 60)) }))
      .sort((a, b) => b.time - a.time)
      .slice(0, 6);
  }, [logs]);

  if (loading && logs.length === 0) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Activity Logs & Analytics</h1>
          <p className="text-slate-500 dark:text-slate-400">Deep dive into student behavior and session security.</p>
        </div>
        <div className="w-full sm:w-72">
          <Select
            label="Session"
            options={[
              { value: '', label: 'All Sessions' },
              ...sessions.map((session) => ({ value: session._id, label: session.title })),
            ]}
            value={selectedSessionId}
            onChange={(e) => {
              setSelectedSessionId(e.target.value);
              loadLogsBySession(e.target.value);
            }}
            className="mb-0"
          />
        </div>
      </div>

      {error && (
        <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Engagement Distribution">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={engagementData}
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  cx="50%"
                  cy="50%"
                  animationDuration={1200}
                >
                  {engagementData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend verticalAlign="bottom" height={36} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Top Resource Usage (mins)">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={usageData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal vertical={false} stroke="#e2e8f0" />
                <XAxis type="number" hide />
                <YAxis dataKey="site" type="category" width={110} tick={{ fill: '#64748b', fontSize: 12 }} />
                <Tooltip cursor={{ fill: 'transparent' }} />
                <Bar dataKey="time" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card
        noPadding
        title="Detailed Activity Log"
        action={
          <div className="w-64">
            <Input
              placeholder="Search student or resource..."
              icon={<Search size={14} />}
              className="mb-0 h-9 text-sm"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-xs uppercase text-slate-500 font-medium">
              <tr>
                <th className="px-6 py-3">Timestamp</th>
                <th className="px-6 py-3">Student</th>
                <th className="px-6 py-3">Resource</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Engagement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700 bg-white dark:bg-slate-900">
              {filteredLogs.map((log) => (
                <tr key={log._id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors duration-150">
                  <td className="px-6 py-4 text-xs text-slate-500">{new Date(log.timestamp).toLocaleString()}</td>
                  <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">{log.studentName}</td>
                  <td className="px-6 py-4">
                    <span className="font-mono bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-xs text-slate-700 dark:text-slate-300">
                      {log.resource || 'N/A'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    {log.isViolation ? (
                      <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400 text-xs font-medium">
                        <AlertTriangle size={12} /> Violation
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                        <CheckCircle size={12} /> Allowed
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {log.engagementScore ?? '-'}
                    </span>
                  </td>
                </tr>
              ))}

              {filteredLogs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400 italic">
                    No logs found for the selected filters.
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
