import React, { useEffect, useMemo, useState } from 'react';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
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
  UserCheck,
  ShieldCheck,
  Loader2 as Spinner,
} from 'lucide-react';
import { Batch, Session, SessionStatus } from '../types';
import { api, createLog, getAgentConfig, getMe, getStudentBatches, getStudentSessions, joinStudentSession, leaveStudentSession, getCurrentUserId, getStudentUnlockRequests } from '../lib/api';
import { getSocket, joinSessionRoom, sendPresenceHeartbeat, leaveSessionRoom } from '../lib/socket';
import { DeviceProtectionAgent } from '../components/DeviceProtectionAgent';
import { HelpCircle, QrCode, ShieldAlert, Usb, AppWindow, CheckCircle2, XCircle } from 'lucide-react';

export const StudentSession: React.FC = () => {
  const [userName, setUserName] = useState('Student');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [myBatches, setMyBatches] = useState<Batch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<string>('all');
  const [agentConfig, setAgentConfig] = useState<any>(null);
  const [hiddenSessionIds, setHiddenSessionIds] = useState<string[]>([]);
  const [isWorking, setIsWorking] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [selectedSessionForModal, setSelectedSessionForModal] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Quick Join Code & Unlock Request State
  const [sessionCodeInput, setSessionCodeInput] = useState('');
  const [isJoiningCode, setIsJoiningCode] = useState(false);
  const [isUnlockModalOpen, setIsUnlockModalOpen] = useState(false);
  const [unlockIssueType, setUnlockIssueType] = useState('technical_issue');
  const [unlockDescription, setUnlockDescription] = useState('');
  const [submittingUnlock, setSubmittingUnlock] = useState(false);
  const [unlockSuccessMsg, setUnlockSuccessMsg] = useState<string | null>(null);
  const [studentRequests, setStudentRequests] = useState<any[]>([]);
  const [recentBanner, setRecentBanner] = useState<{
    id: string;
    status: 'approved' | 'rejected';
    description: string;
    professorName: string;
    notes?: string;
  } | null>(null);
  const [sessionToLeave, setSessionToLeave] = useState<string | null>(null);

  async function loadData(showLoadingState = true) {
    try {
      if (showLoadingState) {
        setLoading(true);
      }
      setError('');

      const [user, batches, allSessions, config, myRequests] = await Promise.all([
        getMe().catch(() => null),
        getStudentBatches().catch(() => []),
        getStudentSessions().catch(() => []),
        getAgentConfig().catch(() => null),
        getStudentUnlockRequests().catch(() => []),
      ]);

      if (user) {
        setUserName(user.name || user.full_name || 'Student');
      }

      setMyBatches(batches || []);
      setSessions(allSessions || []);
      setAgentConfig(config);
      setStudentRequests(myRequests || []);
    } catch (err: any) {
      console.error('Failed to load student sessions data', err);
      setError(err.message || 'Failed to load session data.');
    } finally {
      if (showLoadingState) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  // Listen for unlock request resolution events from professor
  useEffect(() => {
    const socket = getSocket();
    const handleResolved = (payload: any) => {
      const myId = getCurrentUserId();
      if (!payload.student_id || payload.student_id === myId) {
        const isApproved = payload.status === 'approved';
        setRecentBanner({
          id: payload.id,
          status: isApproved ? 'approved' : 'rejected',
          description: payload.description || 'Access Request',
          professorName: payload.resolved_by_name || 'Professor',
          notes: payload.resolution_notes,
        });

        setStudentRequests((prev) => {
          const exists = prev.some((r) => r.id === payload.id);
          if (exists) {
            return prev.map((r) =>
              r.id === payload.id
                ? {
                    ...r,
                    status: payload.status,
                    resolution_notes: payload.resolution_notes,
                    resolved_by_name: payload.resolved_by_name,
                  }
                : r
            );
          }
          return [payload, ...prev];
        });
      }
    };

    const handleSessionUpdated = () => {
      loadData(false);
    };

    socket.on('unlock_request_resolved', handleResolved);
    socket.on('session_started', handleSessionUpdated);
    socket.on('session_updated', handleSessionUpdated);

    return () => {
      socket.off('unlock_request_resolved', handleResolved);
      socket.off('session_started', handleSessionUpdated);
      socket.off('session_updated', handleSessionUpdated);
    };
  }, []);

  const getStatusColor = (status: SessionStatus | string) => {
    switch (String(status).toLowerCase()) {
      case 'active':
        return 'text-emerald-600 bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800';
      case 'upcoming':
      case 'scheduled':
        return 'text-blue-600 bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800';
      default:
        return 'text-slate-600 bg-slate-100 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700';
    }
  };

  const activeJoinedSession = useMemo(() => {
    return sessions.find(
      (session) =>
        session.isJoined &&
        (String(session.status).toLowerCase() === 'active' || String(session.status).toLowerCase() === 'in-progress')
    );
  }, [sessions]);

  const filteredSessions = useMemo(() => {
    return sessions.filter((session) => {
      if (hiddenSessionIds.includes(session._id)) {
        return false;
      }
      if (selectedBatchId === 'all') {
        return true;
      }
      return session.batchIds?.includes(selectedBatchId) || (session as any).classId === selectedBatchId;
    });
  }, [sessions, hiddenSessionIds, selectedBatchId]);

  const currentSession = sessions.find((session) => session._id === currentSessionId) || activeJoinedSession;

  const hideSession = (id: string) => {
    setHiddenSessionIds((prev) => [...prev, id]);
  };

  const showAllSessions = () => {
    setHiddenSessionIds([]);
  };

  const handleJoinSession = async (sessionId: string) => {
    try {
      await joinStudentSession(sessionId);
      setCurrentSessionId(sessionId);
      setIsWorking(true);
      setSelectedSessionForModal(null);
      await loadData(false);

      await createLog({
        sessionId,
        type: 'EVENT',
        resource: 'system',
        details: 'Student manually joined live session',
        engagementScore: 90,
        isViolation: false,
      }).catch(() => null);
    } catch (err: any) {
      if (err.message && (err.message.includes('already joined') || err.message.includes('409'))) {
        setCurrentSessionId(sessionId);
        setIsWorking(true);
        setSelectedSessionForModal(null);
        await loadData(false);
        return;
      }
      alert(err.message || 'Unable to join session. The session must be active and you must be in the batch.');
    }
  };

  const promptLeaveSession = (sessionId?: string) => {
    const targetId = sessionId || currentSessionId || activeJoinedSession?._id;
    if (targetId) {
      setSessionToLeave(targetId);
    }
  };

  const confirmLeaveSession = async () => {
    if (!sessionToLeave) return;
    try {
      await leaveStudentSession(sessionToLeave);
      leaveSessionRoom(sessionToLeave);
    } catch (err: any) {
      console.warn('Failed to leave session on backend:', err);
    } finally {
      setSessionToLeave(null);
      setIsWorking(false);
      setCurrentSessionId(null);
      await loadData(false);
    }
  };

  const monitoredResources = agentConfig?.domains?.length
    ? agentConfig.domains
    : ['No active blocked domains at the moment'];

  // Socket.IO presence heartbeat (20s interval) for active joined session
  useEffect(() => {
    const sessId = activeJoinedSession?._id || currentSessionId;
    if (!sessId) return;

    joinSessionRoom(sessId);
    sendPresenceHeartbeat(sessId);

    const hbInterval = setInterval(() => {
      sendPresenceHeartbeat(sessId);
    }, 20000);

    return () => {
      clearInterval(hbInterval);
    };
  }, [activeJoinedSession?._id, currentSessionId]);



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

  const handleJoinByCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionCodeInput.trim()) return;
    setIsJoiningCode(true);
    try {
      const res = await api.post('/api/v1/sessions/join-by-code', { session_code: sessionCodeInput.trim().toUpperCase() });
      setSessionCodeInput('');
      await loadData(false);
      setCurrentSessionId(res.data.id);
      setIsWorking(true);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Invalid or inactive session code. Please check with your professor.');
    } finally {
      setIsJoiningCode(false);
    }
  };

  const handleSubmitUnlockRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentSession) return;
    setSubmittingUnlock(true);
    try {
      const res = await api.post(`/api/v1/sessions/${currentSession._id}/unlock-requests`, {
        issue_type: unlockIssueType,
        description: unlockDescription
      });
      setUnlockSuccessMsg('Your assistance / temporary unlock request was submitted to the professor.');
      if (res.data) {
        setStudentRequests((prev) => [res.data, ...prev]);
      }
      setUnlockDescription('');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to submit assistance request.');
    } finally {
      setSubmittingUnlock(false);
    }
  };

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
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
          <div>
            <div className="flex items-center gap-3">
              <span className="w-3 h-3 rounded-full bg-emerald-400 animate-ping" />
              <h2 className="text-2xl font-bold text-white">
                Academia Shield Workspace: {currentSession.title}
              </h2>
            </div>
            <p className="text-slate-400 text-sm mt-1 flex items-center gap-2">
              <ShieldCheck size={16} className="text-emerald-400" />
              Instructor: <span className="text-white font-medium">{currentSession.professorName || 'Professor'}</span>
              {' • '}
              Ends at: <span className="font-mono text-indigo-300">{new Date(currentSession.endTime).toLocaleTimeString()}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" className="!border-amber-500/40 !text-amber-400 hover:!bg-amber-500/10 text-xs" onClick={() => setIsUnlockModalOpen(true)}>
              <HelpCircle size={14} className="mr-1.5" /> Request Assistance / Unlock
            </Button>
            <Button variant="danger" onClick={() => promptLeaveSession(currentSession._id)}>
              Leave Session
            </Button>
          </div>
        </div>

        {/* Live Unlock Request Decision Banner */}
        {recentBanner && (
          <div
            className={`p-4 rounded-2xl border flex items-start justify-between gap-4 transition-all duration-300 shadow-xl animate-in fade-in slide-in-from-top-2 ${
              recentBanner.status === 'approved'
                ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-100 shadow-emerald-950/30'
                : 'bg-rose-950/80 border-rose-500/50 text-rose-100 shadow-rose-950/30'
            }`}
          >
            <div className="flex items-start gap-3.5">
              <div
                className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 ${
                  recentBanner.status === 'approved'
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                }`}
              >
                {recentBanner.status === 'approved' ? (
                  <CheckCircle size={20} className="text-emerald-400" />
                ) : (
                  <ShieldAlert size={20} className="text-rose-400" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${
                      recentBanner.status === 'approved'
                        ? 'bg-emerald-500/30 text-emerald-300 border border-emerald-500/40'
                        : 'bg-rose-500/30 text-rose-300 border border-rose-500/40'
                    }`}
                  >
                    {recentBanner.status === 'approved' ? 'Request Accepted & Allowed' : 'Request Denied'}
                  </span>
                  <span className="text-xs text-slate-400">by {recentBanner.professorName}</span>
                </div>
                <p className="text-sm font-semibold text-white mt-1">
                  "{recentBanner.description}"
                </p>
                {recentBanner.notes && (
                  <p className="text-xs text-slate-300 mt-1 opacity-90">
                    Note from instructor: {recentBanner.notes}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => setRecentBanner(null)}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors text-sm"
              title="Dismiss notification"
            >
              ✕
            </button>
          </div>
        )}

        {/* Policy Transparency Card */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card title="Session Governance Policy" className="md:col-span-2">
            <div className="space-y-4">
              <div className="p-4 bg-indigo-950/40 rounded-xl text-sm text-indigo-200 border border-indigo-800/40 flex items-start gap-3">
                <ShieldAlert size={20} className="text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-white">Active Restriction Rules</p>
                  <p className="text-xs text-indigo-300 mt-0.5">
                    Temporary restrictions applied to your endpoint for this class session. These automatically expire when class ends.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <div className="flex items-center gap-2 text-indigo-400 mb-1">
                    <Globe size={18} />
                    <span className="text-xs font-semibold uppercase tracking-wider">Web Filtering</span>
                  </div>
                  <p className="text-lg font-bold text-emerald-400">Protected</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Restricted via Hosts/DNS</p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <div className="flex items-center gap-2 text-indigo-400 mb-1">
                    <AppWindow size={18} />
                    <span className="text-xs font-semibold uppercase tracking-wider">App Control</span>
                  </div>
                  <p className="text-lg font-bold text-emerald-400">Protected</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Monitored process list</p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <div className="flex items-center gap-2 text-indigo-400 mb-1">
                    <Usb size={18} />
                    <span className="text-xs font-semibold uppercase tracking-wider">USB Storage</span>
                  </div>
                  <p className="text-lg font-bold text-emerald-400">Protected</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Mouse & Keyboards Safe</p>
                </div>
              </div>
            </div>
          </Card>

          <Card title="Endpoint Compliance">
            <div className="space-y-4">
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-400">Agent Protection</span>
                <span className="font-bold text-emerald-400 flex items-center gap-1">
                  <CheckCircle size={14} /> Active
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-400">Fail-Safe Watchdog</span>
                <span className="font-mono text-xs text-indigo-300">120s Auto-Unlock</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-slate-400">Class Batch</span>
                <span className="text-white font-medium">{currentSession.course || 'Academic Batch'}</span>
              </div>
              <div className="pt-4 border-t border-slate-800">
                <p className="text-xs text-slate-500">
                  If the server disconnects, restrictions automatically self-terminate.
                </p>
              </div>
            </div>
          </Card>
        </div>

        {/* Assistance / Unlock Request Modal */}
        <Modal
          isOpen={isUnlockModalOpen}
          onClose={() => {
            setIsUnlockModalOpen(false);
            setUnlockSuccessMsg(null);
          }}
          title="Request Temporary Policy Assistance"
        >
          <form onSubmit={handleSubmitUnlockRequest} className="space-y-4">
            {unlockSuccessMsg ? (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
                <CheckCircle size={18} />
                {unlockSuccessMsg}
              </div>
            ) : (
              <>
                <p className="text-xs text-slate-400">
                  Need access to a blocked site for an assignment, or encountering an issue? Send a request directly to your instructor.
                </p>
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase text-slate-400">Request Reason</label>
                  <select
                    value={unlockIssueType}
                    onChange={(e) => setUnlockIssueType(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="technical_issue">Technical Issue / Bug</option>
                    <option value="unlock_request">Need Website/App Access for Coursework</option>
                    <option value="emergency">Exam Exemption / Accommodation</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase text-slate-400">Details / Explanation</label>
                  <textarea
                    rows={3}
                    value={unlockDescription}
                    onChange={(e) => setUnlockDescription(e.target.value)}
                    placeholder="Describe the URL, application, or technical issue..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                    required
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="ghost" type="button" onClick={() => setIsUnlockModalOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={submittingUnlock}>
                    {submittingUnlock ? 'Submitting...' : 'Send Request to Professor'}
                  </Button>
                </div>
              </>
            )}
          </form>

          {/* Student's Recent Assistance Requests */}
          {studentRequests.length > 0 && (
            <div className="mt-6 pt-5 border-t border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Your Requests
                </span>
                <span className="text-[11px] text-slate-500">
                  {studentRequests.length} submitted
                </span>
              </div>
              <div className="max-h-48 overflow-y-auto space-y-2 pr-1 divide-y divide-slate-800/40">
                {studentRequests.map((req: any) => {
                  const isAppr = req.status === 'approved';
                  const isRej = req.status === 'rejected';
                  return (
                    <div
                      key={req.id || req._id}
                      className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 text-xs space-y-1.5 mt-1"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-slate-200 font-medium truncate max-w-[200px]">
                          {req.description}
                        </span>
                        <span
                          className={`px-2.5 py-0.5 rounded-lg text-[10px] font-semibold border ${
                            isAppr
                              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                              : isRej
                              ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                              : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                          }`}
                        >
                          {isAppr ? 'Accepted & Allowed' : isRej ? 'Denied' : 'Pending Review'}
                        </span>
                      </div>
                      {req.resolution_notes && (
                        <p className="text-[11px] text-slate-400 border-l-2 border-slate-700 pl-2">
                          {req.resolution_notes}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Modal>

        {/* Leave Workspace Confirmation Modal */}
        <Modal
          isOpen={!!sessionToLeave}
          onClose={() => setSessionToLeave(null)}
          title="Leave Classroom Workspace?"
        >
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-sm flex items-start gap-3">
              <ShieldAlert size={22} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-semibold text-white">Device Protection Remains Active</p>
                <p className="text-xs text-amber-200/90 leading-relaxed">
                  Leaving this page does not disable device protection. Protection remains active until the professor ends the session.
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-400">
              You can rejoin this workspace at any time while the session remains active.
            </p>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
              <Button variant="ghost" onClick={() => setSessionToLeave(null)}>
                Stay in Workspace
              </Button>
              <Button variant="danger" onClick={confirmLeaveSession}>
                Confirm Leave Portal
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Quick Join Header & Code Banner */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 bg-gradient-to-r from-indigo-900/90 via-slate-900 to-slate-900 border border-indigo-500/20 rounded-3xl p-8 text-white shadow-2xl">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight mb-2">Academia Shield Student Portal</h1>
          <p className="text-slate-300 max-w-xl text-sm">
            Enrolled in {myBatches.length} batch(es). Enter your instructor's 6-character session code to join an active classroom workspace immediately.
          </p>
        </div>

        {/* Quick Join Code Input */}
        <form onSubmit={handleJoinByCode} className="flex items-center gap-2 bg-slate-950/80 p-2 rounded-2xl border border-slate-800 shadow-inner">
          <input
            type="text"
            placeholder="Code (e.g. AS-9F2K1A)"
            value={sessionCodeInput}
            onChange={(e) => setSessionCodeInput(e.target.value)}
            className="bg-transparent px-4 py-2 font-mono text-sm text-white placeholder-slate-500 uppercase tracking-wider focus:outline-none w-48"
            required
          />
          <button
            type="submit"
            disabled={isJoiningCode}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold transition-all shadow-md shadow-indigo-600/30 disabled:opacity-50"
          >
            {isJoiningCode ? 'Joining...' : 'Join Session'}
          </button>
        </form>
      </div>

      {/* Device Protection Agent Section */}
      <DeviceProtectionAgent />

      <div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Batch Sessions</h2>
            <select
              value={selectedBatchId}
              onChange={(e) => setSelectedBatchId(e.target.value)}
              className="bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 rounded-lg text-sm px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="all">All Joined Batches ({myBatches.length})</option>
              {myBatches.map((b) => (
                <option key={b._id || (b as any).id} value={b._id || (b as any).id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>
          {hiddenSessionIds.length > 0 && (
            <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />} onClick={showAllSessions}>
              Show Hidden ({hiddenSessionIds.length})
            </Button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredSessions.map((session) => {
            const isActive = String(session.status).toLowerCase() === 'active';
            const isJoined = session.isJoined;

            return (
              <Card key={session._id} className={`flex flex-col h-full transition-all group relative ${isActive ? 'border-emerald-400 dark:border-emerald-700 shadow-md' : 'hover:border-brand-300 dark:hover:border-brand-700'}`}>
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
                  {isActive ? (
                    <span className="px-2.5 py-1 rounded text-xs font-bold bg-emerald-500 text-white animate-pulse flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                      ACTIVE NOW
                    </span>
                  ) : (
                    <span className={`px-2.5 py-1 rounded text-xs font-medium border ${getStatusColor(session.status)}`}>
                      {session.status}
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1 group-hover:text-brand-600 transition-colors">
                  {session.title}
                </h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">{session.course}</p>
                {session.description && (
                  <p className="text-xs text-slate-400 line-clamp-2 mb-4">{session.description}</p>
                )}

                <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700 flex flex-col gap-3">
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <Clock size={12} /> {new Date(session.startTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span>Instructor: {session.professorName || 'Professor'}</span>
                  </div>

                  <div className="flex items-center gap-2 pt-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex-1 text-xs"
                      onClick={() => setSelectedSessionForModal(session)}
                    >
                      View Details
                    </Button>

                    {isActive ? (
                      isJoined ? (
                        <div className="flex items-center gap-1.5 flex-1">
                          <Button
                            variant="outline"
                            size="sm"
                            className="!bg-emerald-50 !border-emerald-300 !text-emerald-700 font-semibold flex-1 text-xs"
                            onClick={() => {
                              setCurrentSessionId(session._id);
                              setIsWorking(true);
                            }}
                          >
                            <UserCheck size={14} className="mr-1" /> Workspace
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            className="text-xs px-2.5 py-1"
                            onClick={() => promptLeaveSession(session._id)}
                            title="Leave Session"
                          >
                            Leave
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="primary"
                          size="sm"
                          className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold flex-1 text-xs shadow-sm"
                          icon={<Play size={14} />}
                          onClick={() => handleJoinSession(session._id)}
                        >
                          Join Session
                        </Button>
                      )
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled
                        className="bg-slate-100 dark:bg-slate-800 text-slate-400 flex-1 text-xs cursor-not-allowed"
                        title="Waiting for professor to start session"
                      >
                        Not Started
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}

          <button
            onClick={() => (window.location.hash = '/student/join-batch')}
            className="flex flex-col items-center justify-center p-6 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700 text-slate-400 hover:text-brand-600 hover:border-brand-300 hover:bg-brand-50/50 dark:hover:bg-brand-900/10 transition-all h-full min-h-[220px]"
          >
            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
              <ArrowRight size={24} />
            </div>
            <p className="font-medium text-slate-700 dark:text-slate-300">Join New Batch</p>
            <p className="text-xs mt-1">Enter 6-char batch code</p>
          </button>
        </div>
      </div>

      {/* SESSION DETAILS MODAL */}
      {selectedSessionForModal && (
        <Modal
          isOpen={!!selectedSessionForModal}
          onClose={() => setSelectedSessionForModal(null)}
          title={`Session Details: ${selectedSessionForModal.title}`}
        >
          <div className="space-y-4">
            <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl space-y-3">
              <div>
                <p className="text-xs text-slate-400 uppercase font-semibold">Course / Batch</p>
                <p className="text-base font-semibold text-slate-900 dark:text-white">{selectedSessionForModal.course}</p>
              </div>

              {selectedSessionForModal.description && (
                <div>
                  <p className="text-xs text-slate-400 uppercase font-semibold">Description</p>
                  <p className="text-sm text-slate-700 dark:text-slate-300">{selectedSessionForModal.description}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <p className="text-xs text-slate-400 uppercase font-semibold">Instructor</p>
                  <p className="text-sm text-slate-800 dark:text-slate-200">{selectedSessionForModal.professorName || 'Professor'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400 uppercase font-semibold">Status</p>
                  <span className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${getStatusColor(selectedSessionForModal.status)}`}>
                    {selectedSessionForModal.status}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <p className="text-xs text-slate-400 uppercase font-semibold">Start Time</p>
                  <p className="text-sm font-mono">{new Date(selectedSessionForModal.startTime).toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400 uppercase font-semibold">End Time</p>
                  <p className="text-sm font-mono">{new Date(selectedSessionForModal.endTime).toLocaleString()}</p>
                </div>
              </div>
            </div>

            <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg text-xs text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 flex items-start gap-2">
              <ShieldCheck size={16} className="mt-0.5 shrink-0" />
              <span>
                <strong>Agent Policy Info:</strong> When you click "Join Session" during an active session, web domain and application rules will be enforced on your local device.
              </span>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
              <Button variant="ghost" onClick={() => setSelectedSessionForModal(null)}>
                Close
              </Button>
              {String(selectedSessionForModal.status).toLowerCase() === 'active' && !selectedSessionForModal.isJoined && (
                <Button
                  variant="primary"
                  className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
                  onClick={() => handleJoinSession(selectedSessionForModal._id)}
                >
                  <Play size={16} className="mr-1.5" /> Join Session Now
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
