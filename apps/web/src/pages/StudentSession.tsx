import React, { useEffect, useMemo, useState } from 'react';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import {
  Calendar,
  Clock,
  ArrowRight,
  CheckCircle,
  BookOpen,
  EyeOff,
  RefreshCw,
  Globe,
  Play,
  Activity,
  Loader2 as Spinner,
} from 'lucide-react';
import { Batch, Session, SessionStatus } from '../types';
import { createLog, getAgentConfig, getMe, getMyBatches, getSessions, joinSession } from '../lib/api';

export const StudentSession: React.FC = () => {
  const [userName, setUserName] = useState('Student');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [myBatches, setMyBatches] = useState<Batch[]>([]);
  const [agentConfig, setAgentConfig] = useState<any>(null);
  const [hiddenSessionIds, setHiddenSessionIds] = useState<string[]>([]);
  const [isWorking, setIsWorking] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadData(showLoadingState = true) {
    try {
      if (showLoadingState) {
        setLoading(true);
      }
      const [profile, sessionsData, myBatchesData, agentData] = await Promise.all([
        getMe(),
        getSessions(),
        getMyBatches(),
        getAgentConfig(),
      ]);

      setUserName(profile.name || 'Student');
      setSessions(sessionsData);
      setMyBatches(myBatchesData);
      setAgentConfig(agentData);
      setError('');
    } catch (err: any) {
      if (showLoadingState) {
        setError(err.message || 'Failed to load student sessions.');
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
    loadData(true);
    const interval = setInterval(() => loadData(false), 15000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: SessionStatus | string) => {
    switch (String(status).toLowerCase()) {
      case 'active':
        return 'text-emerald-600 bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800';
      case 'upcoming':
        return 'text-blue-600 bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800';
      default:
        return 'text-slate-600 bg-slate-100 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700';
    }
  };

  const activeSession = useMemo(
    () => sessions.find((session) => String(session.status).toLowerCase() === 'active'),
    [sessions]
  );

  const upcomingSessions = useMemo(
    () =>
      sessions.filter(
        (session) =>
          String(session.status).toLowerCase() === 'upcoming' &&
          !hiddenSessionIds.includes(session._id)
      ),
    [sessions, hiddenSessionIds]
  );

  const currentSession = sessions.find((session) => session._id === currentSessionId) || activeSession;

  const hideSession = (id: string) => {
    setHiddenSessionIds((prev) => [...prev, id]);
  };

  const showAllSessions = () => {
    setHiddenSessionIds([]);
  };

  const handleStartWorking = async (sessionId: string) => {
    try {
      await joinSession(sessionId);
      setCurrentSessionId(sessionId);
      setIsWorking(true);
    } catch (err: any) {
      alert(err.message || 'Unable to join this session. Please join the class batch first.');
    }
  };

  const monitoredResources = agentConfig?.domains?.length
    ? agentConfig.domains
    : ['No active blocked domains at the moment'];

  // Automatic activity simulation for Working Mode
  useEffect(() => {
    let activityInterval: ReturnType<typeof setInterval>;

    if (isWorking && currentSession) {
      // Simulate activity every 15 seconds
      activityInterval = setInterval(async () => {
        try {
          const isViolation = Math.random() < 0.15; // 15% chance to simulate a violation
          const activeDomains = agentConfig?.domains || [];
          
          const resource = isViolation && activeDomains.length > 0
            ? activeDomains[Math.floor(Math.random() * activeDomains.length)]
            : 'vscode.dev';

          await createLog({
            sessionId: currentSession._id,
            type: 'EVENT',
            resource,
            details: isViolation ? `Agent blocked access to ${resource}` : 'Student working normally',
            engagementScore: isViolation ? 20 : 85 + Math.floor(Math.random() * 15),
            isViolation,
          });
        } catch (e) {
          console.warn('Background simulation log failed', e);
        }
      }, 15000);
    }

    return () => {
      if (activityInterval) clearInterval(activityInterval);
    };
  }, [isWorking, currentSession, agentConfig]);

  const simulateActivity = async (resource: string) => {
    if (!currentSession) return;

    try {
      await createLog({
        sessionId: currentSession._id,
        type: 'EVENT',
        resource,
        details: 'Student opened monitored resource',
        engagementScore: 90,
        isViolation: monitoredResources.includes(resource),
      });

      alert(`Activity logged for resource: ${resource}`);
    } catch (err: any) {
      alert(err.message || 'Failed to log student activity.');
    }
  };

  const batchCode =
    currentSession?.batchIds?.[0] &&
    myBatches.find((batch) => batch._id === currentSession.batchIds[0])?.code;

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  if (error) {
    return <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>;
  }

  if (isWorking && currentSession) {
    return (
      <div className="max-w-5xl mx-auto space-y-6 animate-fade-in">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
              <span className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
              Working Mode: {currentSession.title}
            </h2>
            <p className="text-slate-500 mt-1 flex items-center gap-2">
              <Activity size={14} className="text-emerald-500" />
              Activity logging enabled for this session
            </p>
          </div>
          <Button variant="danger" onClick={() => setIsWorking(false)}>
            Stop Session
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card title="Monitored Resources" className="md:col-span-2">
            <div className="space-y-4">
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-700 dark:text-blue-300 border border-blue-100 dark:border-blue-800">
                <strong>Session Policy:</strong> Resource access events are recorded for live monitoring.
              </div>
              <p className="text-sm text-slate-500">Click a resource below to simulate activity logging.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {monitoredResources.map((resource: string, index: number) => (
                  <button
                    key={`${resource}-${index}`}
                    onClick={() => simulateActivity(resource)}
                    className="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-brand-500 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-all text-left group"
                  >
                    <div className="p-2 bg-white dark:bg-slate-800 rounded-lg shadow-sm group-hover:scale-110 transition-transform">
                      <Globe size={20} className="text-brand-600" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">{resource}</p>
                      <p className="text-xs text-slate-500">Click to log activity</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </Card>

          <Card title="Session Stats">
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-500">Status</span>
                <span className="font-bold text-emerald-500">Live</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-500">Ends At</span>
                <span className="font-mono text-sm">{new Date(currentSession.endTime).toLocaleTimeString()}</span>
              </div>
              <div className="pt-4 border-t border-slate-100 dark:border-slate-700">
                <p className="text-xs text-slate-400 mb-2">Policy Status</p>
                <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 p-2 rounded">
                  <CheckCircle size={16} /> Compliant
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-brand-600 to-blue-700 rounded-2xl p-8 text-white shadow-xl">
        <div>
          <h1 className="text-3xl font-bold mb-2">Welcome back, {userName}</h1>
          <p className="text-brand-100 max-w-xl">
            You have {activeSession ? '1 active session' : 'no active sessions'} and {upcomingSessions.length} upcoming classes visible.
          </p>
        </div>
        <div className="hidden md:block bg-white/10 backdrop-blur-sm p-4 rounded-xl border border-white/20">
          <p className="text-sm font-medium text-brand-100 uppercase tracking-wider mb-1">Compliance Status</p>
          <div className="flex items-center gap-2 text-emerald-300 font-bold text-lg">
            <CheckCircle size={20} /> System Ready
          </div>
        </div>
      </div>

      {activeSession && (
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
            Live Now
          </h2>
          <SpotlightCard className="border-l-4 border-l-emerald-500" spotlightColor="rgba(16, 185, 129, 0.1)">
            <div className="p-6 md:p-8 flex flex-col md:flex-row gap-6 items-start md:items-center justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-500 text-white animate-pulse">LIVE SESSION</span>
                  <span className="text-sm text-slate-500 dark:text-slate-400 font-mono">Code: {batchCode || 'PUBLIC'}</span>
                </div>
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">{activeSession.title}</h3>
                <p className="text-slate-500 dark:text-slate-400 flex items-center gap-2">
                  <BookOpen size={16} /> {activeSession.course}
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-4 w-full md:w-auto">
                <div className="text-center px-6 py-3 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-100 dark:border-slate-700">
                  <p className="text-xs text-slate-400 uppercase">Ends At</p>
                  <p className="text-xl font-mono font-bold text-slate-900 dark:text-white">
                    {new Date(activeSession.endTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
                <Button
                  size="lg"
                  className="w-full md:w-auto shadow-lg shadow-brand-500/20"
                  icon={<Play size={20} />}
                  onClick={() => handleStartWorking(activeSession._id)}
                >
                  Start Working
                </Button>
              </div>
            </div>
          </SpotlightCard>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Upcoming Sessions</h2>
          {hiddenSessionIds.length > 0 && (
            <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />} onClick={showAllSessions}>
              Show Hidden ({hiddenSessionIds.length})
            </Button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {upcomingSessions.map((session) => (
            <Card key={session._id} className="flex flex-col h-full hover:border-brand-300 dark:hover:border-brand-700 transition-colors group relative">
              <button
                onClick={() => hideSession(session._id)}
                className="absolute top-3 right-3 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-full transition-colors opacity-0 group-hover:opacity-100 z-10"
                title="Hide from view"
              >
                <EyeOff size={16} />
              </button>

              <div className="flex justify-between items-start mb-4">
                <div className={`p-2 rounded-lg ${getStatusColor(session.status)}`}>
                  <Calendar size={20} />
                </div>
                <span className={`px-2.5 py-1 rounded text-xs font-medium border ${getStatusColor(session.status)}`}>
                  {new Date(session.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>

              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1 group-hover:text-brand-600 transition-colors">
                {session.title}
              </h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">{session.course}</p>

              <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between text-sm">
                <span className="text-slate-500 flex items-center gap-1">
                  <Clock size={14} /> {new Date(session.endTime).toLocaleDateString()}
                </span>
                <Button variant="ghost" size="sm" className="text-brand-600 p-0 hover:bg-transparent hover:underline">
                  View Details
                </Button>
              </div>
            </Card>
          ))}

          <button
            onClick={() => (window.location.hash = '/student/join-batch')}
            className="flex flex-col items-center justify-center p-6 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700 text-slate-400 hover:text-brand-600 hover:border-brand-300 hover:bg-brand-50/50 dark:hover:bg-brand-900/10 transition-all h-full min-h-[200px]"
          >
            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
              <ArrowRight size={24} />
            </div>
            <p className="font-medium">Join New Class</p>
            <p className="text-xs mt-1">Use batch code</p>
          </button>
        </div>
      </div>
    </div>
  );
};
