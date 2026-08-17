import React, { useEffect, useMemo, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from 'recharts';
import { Card } from '../components/ui/Card';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { Button } from '../components/ui/Button';
import {
  Users,
  ShieldAlert,
  Activity,
  Calendar,
  Plus,
  Wifi,
  ChevronRight,
  CheckCircle,
  Loader2 as Spinner,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Batch, LogEntry, Session } from '../types';
import {
  getAgentConfig,
  getBatches,
  getLogs,
  getMe,
  getMyBatches,
  getSessions,
} from '../lib/api';

const StatCard = ({ title, value, trend, icon, color }: any) => (
  <SpotlightCard className="hover:-translate-y-1">
    <div className="p-6 flex items-start justify-between h-full">
      <div>
        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
        <h3 className="text-3xl font-bold text-slate-900 dark:text-white mt-2">{value}</h3>
        <p
          className={`text-xs font-medium mt-2 ${
            String(trend).includes('+') || String(trend).includes('Good') || String(trend).includes('Live')
              ? 'text-emerald-600'
              : 'text-red-600'
          }`}
        >
          {trend}
        </p>
      </div>
      <div className={`p-3 rounded-lg ${color} text-white`}>{icon}</div>
    </div>
  </SpotlightCard>
);

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const userRole = localStorage.getItem('userRole');
  const isStudent = userRole === 'student';

  const [userName, setUserName] = useState('User');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentConfig, setAgentConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadDashboard(showLoadingState = true) {
    try {
      if (showLoadingState) {
        setLoading(true);
      }

      const [profile, sessionsData, logsData, agentData] = await Promise.all([
        getMe(),
        getSessions(),
        getLogs(),
        getAgentConfig(),
      ]);

      setUserName(profile.name || (isStudent ? 'Student' : 'Professor'));
      setSessions(sessionsData);
      setLogs(logsData);
      setAgentConfig(agentData);

      if (isStudent) {
        const myBatches = await getMyBatches();
        setBatches(myBatches);
      } else {
        const professorBatches = await getBatches();
        setBatches(professorBatches);
      }

      setError('');
    } catch (err: any) {
      if (showLoadingState) {
        setError(err.message || 'Failed to load dashboard data.');
      } else {
        console.warn('Background polling failed:', err.message);
      }
    } finally {
      if (showLoadingState) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    loadDashboard(true);
    const interval = setInterval(() => loadDashboard(false), 15000);
    return () => clearInterval(interval);
  }, [isStudent]);

  const activeSessions = useMemo(
    () => sessions.filter((session) => String(session.status).toLowerCase() === 'active'),
    [sessions]
  );

  const upcomingExams = useMemo(
    () =>
      sessions.filter(
        (session) =>
          String(session.status).toLowerCase() === 'upcoming' && String(session.type).toLowerCase() === 'exam'
      ),
    [sessions]
  );

  const anomalyCount = useMemo(() => logs.filter((log) => log.isViolation).length, [logs]);

  const totalStudents = useMemo(() => {
    const uniqueStudents = new Set<string>();
    batches.forEach((batch) => {
      (batch.students || []).forEach((student) => uniqueStudents.add(student._id));
    });
    return uniqueStudents.size;
  }, [batches]);

  const activityData = useMemo(() => {
    const now = new Date();
    const buckets = Array.from({ length: 6 }, (_, index) => {
      const start = new Date(now);
      start.setMinutes(0, 0, 0);
      start.setHours(now.getHours() - (5 - index));
      const end = new Date(start);
      end.setHours(start.getHours() + 1);

      const count = logs.filter((log) => {
        const ts = new Date(log.timestamp);
        return ts >= start && ts < end;
      }).length;

      return {
        time: start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        students: count,
      };
    });

    return buckets;
  }, [logs]);

  const sessionData = useMemo(() => {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const byDay = days.map((day) => ({ name: day, Active: 0, Completed: 0 }));

    sessions.forEach((session) => {
      const dayIndex = new Date(session.startTime).getDay();
      const status = String(session.status).toLowerCase();
      if (status === 'active') byDay[dayIndex].Active += 1;
      if (status === 'completed') byDay[dayIndex].Completed += 1;
    });

    return byDay;
  }, [sessions]);

  const liveSessions = useMemo(() => {
    return activeSessions.map((session) => {
      const sessionLogs = logs.filter((log) => String(log.sessionId) === String(session._id));
      const uniqueStudents = new Set(sessionLogs.map((log) => log.studentId));
      const avgEngagement =
        sessionLogs.length > 0
          ? sessionLogs.reduce((sum, log) => sum + (log.engagementScore || 0), 0) / sessionLogs.length
          : 0;

      return {
        _id: session._id,
        title: session.title,
        course: session.course,
        totalStudents: uniqueStudents.size,
        currentEngagement: Number(avgEngagement.toFixed(1)),
      };
    });
  }, [activeSessions, logs]);

  const studentAnomalyCount = useMemo(() => logs.filter((log) => log.isViolation).length, [logs]);

  if (loading) {
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
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Dashboard Overview</h1>
          <p className="text-slate-500 dark:text-slate-400">
            {isStudent
              ? 'Welcome back. Check your upcoming schedule and compliance status.'
              : `Welcome back, ${userName}. Here is the current system status.`}
          </p>
        </div>
        {!isStudent && (
          <Button icon={<Plus size={18} />} onClick={() => navigate('/sessions')}>
            Create Session
          </Button>
        )}
      </div>

      {error && <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title={isStudent ? 'Enrolled Sessions' : 'Active Sessions'}
          value={isStudent ? sessions.length : activeSessions.length}
          trend={activeSessions.length > 0 ? 'Live' : 'Idle'}
          icon={<Activity size={24} />}
          color="bg-blue-500"
        />

        {isStudent ? (
          <>
            <StatCard
              title="Joined Classes"
              value={batches.length}
              trend={batches.length > 0 ? 'Good' : '0'}
              icon={<Users size={24} />}
              color="bg-emerald-500"
            />
            <StatCard
              title="Upcoming Exams"
              value={upcomingExams.length}
              trend={upcomingExams.length > 0 ? `+${upcomingExams.length}` : '0'}
              icon={<Calendar size={24} />}
              color="bg-indigo-500"
            />
            <StatCard
              title="System Status"
              value={studentAnomalyCount > 0 ? 'Attention' : 'Ready'}
              trend={studentAnomalyCount > 0 ? `${studentAnomalyCount} issue(s)` : 'Good'}
              icon={<ShieldAlert size={24} />}
              color="bg-teal-500"
            />
          </>
        ) : (
          <>
            <StatCard
              title="Total Students"
              value={totalStudents}
              trend={totalStudents > 0 ? `+${totalStudents}` : '0'}
              icon={<Users size={24} />}
              color="bg-indigo-500"
            />
            <StatCard
              title="Anomalies Detected"
              value={anomalyCount}
              trend={anomalyCount > 0 ? `${anomalyCount} open` : '0'}
              icon={<ShieldAlert size={24} />}
              color="bg-red-500"
            />
            <StatCard
              title="Upcoming Exams"
              value={upcomingExams.length}
              trend={upcomingExams.length > 0 ? `+${upcomingExams.length}` : '0'}
              icon={<Calendar size={24} />}
              color="bg-teal-500"
            />
          </>
        )}
      </div>

      {!isStudent && (
        <>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <Wifi className="text-red-500 animate-pulse" size={20} />
                Live Session Monitoring
              </h2>
              <Button variant="ghost" size="sm" className="text-sm" onClick={() => navigate('/sessions')}>
                View All <ChevronRight size={16} />
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {liveSessions.length === 0 ? (
                <Card className="md:col-span-3">
                  <p className="text-slate-500">No active sessions right now.</p>
                </Card>
              ) : (
                liveSessions.map((session) => (
                  <Card key={session._id} noPadding className="relative overflow-hidden border-l-4 border-l-brand-500">
                    <div className="p-5">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <h3 className="font-semibold text-slate-900 dark:text-white truncate pr-2">{session.title}</h3>
                          <p className="text-xs text-slate-500 dark:text-slate-400">{session.course}</p>
                        </div>
                        <span className="px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-xs font-bold rounded animate-pulse">
                          LIVE
                        </span>
                      </div>

                      <div className="mt-4 space-y-3">
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-500">Active Students</span>
                          <span className="font-medium text-slate-900 dark:text-white">{session.totalStudents}</span>
                        </div>
                        <div>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="text-slate-500">Engagement Score</span>
                            <span
                              className={`font-bold ${
                                session.currentEngagement > 85
                                  ? 'text-emerald-500'
                                  : session.currentEngagement > 60
                                  ? 'text-yellow-500'
                                  : 'text-red-500'
                              }`}
                            >
                              {session.currentEngagement}%
                            </span>
                          </div>
                          <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-700 ${
                                session.currentEngagement > 85
                                  ? 'bg-emerald-500'
                                  : session.currentEngagement > 60
                                  ? 'bg-yellow-500'
                                  : 'bg-red-500'
                              }`}
                              style={{ width: `${session.currentEngagement}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card title="Engagement Trends (Last 6h)" className="lg:col-span-2 h-96">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activityData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorStudents" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="students" stroke="#6366f1" strokeWidth={2.5} fillOpacity={1} fill="url(#colorStudents)" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Weekly Session Distribution" className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sessionData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <Tooltip cursor={{ fill: 'transparent' }} />
                  <Legend />
                  <Bar dataKey="Active" fill="#6366f1" radius={[6, 6, 0, 0]} barSize={20} />
                  <Bar dataKey="Completed" fill="#a5b4fc" radius={[6, 6, 0, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </>
      )}

      {isStudent && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Upcoming Schedule">
            <div className="space-y-4">
              {upcomingExams.slice(0, 3).map((session) => (
                <div
                  key={session._id}
                  className="flex items-center p-3 rounded-lg bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700"
                >
                  <div className="h-10 w-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center mr-4">
                    <Calendar size={20} />
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium text-slate-900 dark:text-white">{session.title}</h4>
                    <p className="text-xs text-slate-500">{new Date(session.startTime).toLocaleString()}</p>
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => navigate('/sessions')}>
                    Details
                  </Button>
                </div>
              ))}
              {upcomingExams.length === 0 && <p className="text-slate-500 text-sm">No upcoming exams scheduled.</p>}
            </div>
          </Card>

          <Card title="Compliance Status">
            <div className="flex flex-col items-center justify-center h-full py-6">
              <div className="h-16 w-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-4">
                <CheckCircle size={32} />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                {studentAnomalyCount > 0 ? 'Action Recommended' : 'You are Compliant'}
              </h3>
              <p className="text-center text-slate-500 text-sm mt-2 max-w-xs">
                {studentAnomalyCount > 0
                  ? `${studentAnomalyCount} violation event(s) detected in your recent activity logs.`
                  : 'Your device environment meets all current session requirements.'}
              </p>
              <Button className="mt-6" variant="outline" onClick={() => navigate('/settings')}>
                Open Settings
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};
