import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bell,
  Search,
  User,
  ShieldCheck,
  Check,
  X,
  Clock,
  AlertCircle,
  HelpCircle,
  Globe,
  Laptop,
  CheckCircle2,
  XCircle,
  Loader2 as Spinner,
} from 'lucide-react';
import {
  getProfessorUnlockRequests,
  getStudentUnlockRequests,
  resolveUnlockRequest,
  getCurrentUserId
} from '../../lib/api';
import { getSocket, joinLiveLogs } from '../../lib/socket';

interface UnlockNotification {
  id: string;
  session_id: string;
  student_id: string;
  student_name?: string;
  issue_type: string;
  description: string;
  status: string;
  resolution_notes?: string;
  resolved_by_name?: string;
  created_at: string;
  updated_at?: string;
}

interface ToastNotification {
  id: string;
  requestId: string;
  status: 'approved' | 'rejected';
  title: string;
  description: string;
  professorName: string;
  notes?: string;
}

export const Navbar: React.FC = () => {
  const userName = localStorage.getItem('userName') || 'Authenticated User';
  const role = localStorage.getItem('userRole') || 'user';
  const department = localStorage.getItem('userDepartment') || '';
  const isProfessor = role === 'professor' || role === 'admin' || role === 'superadmin';
  const displayRole = role === 'student' ? 'Student' : 'Professor';

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [notifications, setNotifications] = useState<UnlockNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [hasNewAlert, setHasNewAlert] = useState(false);
  const [toasts, setToasts] = useState<ToastNotification[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const playNotificationSound = (type: 'pending' | 'approved' | 'rejected' = 'pending') => {
    try {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) return;
      const ctx = new AudioContextClass();
      const now = ctx.currentTime;

      if (type === 'approved') {
        // High, pleasant double chime (C5 -> E5 -> G5)
        const notes = [523.25, 659.25, 783.99];
        notes.forEach((freq, idx) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, now + idx * 0.1);
          gain.gain.setValueAtTime(0.18, now + idx * 0.1);
          gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.1 + 0.25);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(now + idx * 0.1);
          osc.stop(now + idx * 0.1 + 0.25);
        });
      } else if (type === 'rejected') {
        // Subtle low alert tone (F4 -> D4)
        const notes = [349.23, 293.66];
        notes.forEach((freq, idx) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, now + idx * 0.14);
          gain.gain.setValueAtTime(0.16, now + idx * 0.14);
          gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.14 + 0.28);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(now + idx * 0.14);
          osc.stop(now + idx * 0.14 + 0.28);
        });
      } else {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.15);
        gain.gain.setValueAtTime(0.15, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.3);
      }
    } catch {
      // Browser autoplay restriction handling
    }
  };

  // Request browser desktop notification permission if supported
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
    }
  }, []);

  const fetchNotifications = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      if (isProfessor) {
        const data = await getProfessorUnlockRequests();
        setNotifications(data || []);
      } else {
        const data = await getStudentUnlockRequests();
        setNotifications(data || []);
      }
    } catch (err) {
      console.warn('[Navbar] Failed to load unlock requests:', err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [isProfessor]);

  useEffect(() => {
    fetchNotifications(true);
    if (isProfessor) {
      joinLiveLogs();
    }

    const socket = getSocket();

    const handleUnlockCreated = (payload: any) => {
      console.log('[Navbar] New unlock request created:', payload);
      if (isProfessor) {
        setNotifications((prev) => {
          const exists = prev.some((n) => n.id === payload.id);
          if (exists) return prev;
          return [
            {
              id: payload.id,
              session_id: payload.session_id,
              student_id: payload.student_id,
              student_name: payload.student_name || 'Student',
              issue_type: payload.issue_type,
              description: payload.description,
              status: 'pending',
              created_at: payload.created_at || new Date().toISOString(),
            },
            ...prev,
          ];
        });
        setHasNewAlert(true);
        playNotificationSound('pending');
      } else {
        // If current student created a request, refresh their list
        const currentUserId = getCurrentUserId();
        if (!payload.student_id || payload.student_id === currentUserId) {
          fetchNotifications(true);
        }
      }
    };

    const handleUnlockResolved = (payload: any) => {
      console.log('[Navbar] Unlock request resolved:', payload);

      if (isProfessor) {
        setNotifications((prev) =>
          prev.map((n) =>
            n.id === payload.id
              ? { ...n, status: payload.status, resolution_notes: payload.resolution_notes, resolved_by_name: payload.resolved_by_name }
              : n
          )
        );
      } else {
        // For Student: Check if this resolution is for the current student
        const currentUserId = getCurrentUserId();
        const isForMe = !payload.student_id || payload.student_id === currentUserId;

        if (isForMe) {
          const status = payload.status === 'approved' ? 'approved' : 'rejected';
          const profName = payload.resolved_by_name || 'Professor';
          const description = payload.description || 'Access Request';
          const isApproved = status === 'approved';

          // Play audio notification
          playNotificationSound(status);

          // Add floating Toast notification
          const newToast: ToastNotification = {
            id: `toast-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
            requestId: payload.id,
            status,
            title: isApproved ? 'Request Approved!' : 'Request Denied',
            description,
            professorName: profName,
            notes: payload.resolution_notes,
          };

          setToasts((prev) => [newToast, ...prev.slice(0, 4)]);

          // Trigger native desktop notification if permitted
          if ('Notification' in window && Notification.permission === 'granted') {
            try {
              new Notification(
                isApproved ? '✓ Request Approved' : '✕ Request Denied',
                {
                  body: `Your request for "${description}" was ${isApproved ? 'accepted' : 'denied'} by ${profName}.`,
                  icon: '/favicon.ico',
                }
              );
            } catch {}
          }

          // Automatically dismiss toast after 8 seconds
          setTimeout(() => {
            removeToast(newToast.id);
          }, 8000);

          // Update student notification history
          setNotifications((prev) => {
            const exists = prev.some((n) => n.id === payload.id);
            if (exists) {
              return prev.map((n) =>
                n.id === payload.id
                  ? {
                      ...n,
                      status: payload.status,
                      resolution_notes: payload.resolution_notes,
                      resolved_by_name: profName,
                      updated_at: payload.updated_at || new Date().toISOString(),
                    }
                  : n
              );
            }
            return [
              {
                id: payload.id,
                session_id: payload.session_id,
                student_id: payload.student_id,
                student_name: userName,
                issue_type: payload.issue_type || 'unlock_request',
                description,
                status: payload.status,
                resolution_notes: payload.resolution_notes,
                resolved_by_name: profName,
                created_at: payload.created_at || new Date().toISOString(),
                updated_at: payload.updated_at || new Date().toISOString(),
              },
              ...prev,
            ];
          });

          setHasNewAlert(true);
        }
      }
    };

    socket.on('unlock_request_created', handleUnlockCreated);
    socket.on('unlock_request_resolved', handleUnlockResolved);

    const interval = setInterval(() => fetchNotifications(true), 12000);

    return () => {
      socket.off('unlock_request_created', handleUnlockCreated);
      socket.off('unlock_request_resolved', handleUnlockResolved);
      clearInterval(interval);
    };
  }, [isProfessor, userName, fetchNotifications]);

  // Click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const pendingRequests = notifications.filter((n) => n.status === 'pending');
  const studentRecentResolved = notifications.filter((n) => n.status === 'approved' || n.status === 'rejected');
  const unreadCount = isProfessor ? pendingRequests.length : (hasNewAlert ? 1 : 0);

  const handleResolve = async (req: UnlockNotification, status: 'approved' | 'rejected') => {
    setProcessingId(req.id);
    try {
      await resolveUnlockRequest(
        req.session_id,
        req.id,
        status,
        status === 'approved' ? 'Approved by instructor' : 'Dismissed by instructor'
      );
      setNotifications((prev) =>
        prev.map((n) => (n.id === req.id ? { ...n, status } : n))
      );
    } catch (err: any) {
      alert(err.message || 'Failed to update request.');
    } finally {
      setProcessingId(null);
    }
  };

  const formatTimeAgo = (dateStr: string) => {
    try {
      const diffSec = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
      if (diffSec < 60) return 'Just now';
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24) return `${diffHr}h ago`;
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return '';
    }
  };

  const getIssueBadge = (type: string) => {
    switch (type) {
      case 'unlock_request':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Globe size={11} /> Site/App Access
          </span>
        );
      case 'technical_issue':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertCircle size={11} /> Technical Issue
          </span>
        );
      case 'emergency':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <HelpCircle size={11} /> Accommodation
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Laptop size={11} /> Assistance
          </span>
        );
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-6 text-slate-100">
      {/* Floating Resolution Toasts for Student */}
      {toasts.length > 0 && (
        <div className="fixed top-20 right-6 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none animate-in fade-in slide-in-from-top-4 duration-300">
          {toasts.map((toast) => {
            const isApproved = toast.status === 'approved';
            return (
              <div
                key={toast.id}
                className={`pointer-events-auto p-4 rounded-2xl shadow-2xl border backdrop-blur-xl transition-all ${
                  isApproved
                    ? 'bg-slate-900/95 border-emerald-500/60 shadow-emerald-950/40 text-slate-100'
                    : 'bg-slate-900/95 border-rose-500/60 shadow-rose-950/40 text-slate-100'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 ${
                      isApproved
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {isApproved ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h4
                        className={`text-sm font-bold ${
                          isApproved ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {toast.title}
                      </h4>
                      <button
                        onClick={() => removeToast(toast.id)}
                        className="text-slate-400 hover:text-slate-200 p-0.5 rounded-lg transition-colors"
                      >
                        <X size={14} />
                      </button>
                    </div>
                    <p className="text-xs text-slate-200 mt-1 font-semibold leading-snug">
                      "{toast.description}"
                    </p>
                    <p className="text-[11px] text-slate-400 mt-1">
                      {isApproved ? 'Accepted' : 'Denied'} by{' '}
                      <span className="text-white font-medium">{toast.professorName}</span>
                      {toast.notes ? ` • ${toast.notes}` : ''}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Search Bar */}
      <div className="flex w-full max-w-md items-center">
        <div className="relative w-full">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-500">
            <Search size={18} />
          </span>
          <input
            type="text"
            placeholder="Search sessions, batches, or policy logs..."
            className="w-full rounded-xl border border-slate-800 bg-slate-950/80 py-2 pl-10 pr-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-all"
          />
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4">
        <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono rounded-full">
          <ShieldCheck size={14} />
          <span>RBAC Protected Session</span>
        </div>

        {/* Notification Bell with Interactive Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => {
              setIsDropdownOpen(!isDropdownOpen);
              setHasNewAlert(false);
            }}
            className="relative rounded-xl p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors focus:outline-none"
            title={isProfessor ? "Student Assistance Requests" : "My Requests & Notifications"}
          >
            <Bell size={20} className={unreadCount > 0 ? 'text-indigo-400' : ''} />
            {isProfessor && unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow-lg animate-pulse ring-2 ring-slate-900">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
            {!isProfessor && hasNewAlert && (
              <span className="absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-slate-900 animate-pulse"></span>
            )}
          </button>

          {/* Popover Dropdown */}
          {isDropdownOpen && (
            <div className="absolute right-0 mt-3 w-80 sm:w-96 rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
              <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
                <div className="flex items-center gap-2">
                  <Bell size={16} className="text-indigo-400" />
                  <h3 className="text-sm font-semibold text-white">
                    {isProfessor ? 'Student Requests' : 'My Access Requests'}
                  </h3>
                </div>
                {isProfessor ? (
                  unreadCount > 0 ? (
                    <span className="px-2 py-0.5 text-[11px] font-semibold bg-rose-500/20 text-rose-300 rounded-full border border-rose-500/30">
                      {unreadCount} Pending
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400">Up to date</span>
                  )
                ) : (
                  <span className="text-xs text-slate-400">
                    {notifications.length} {notifications.length === 1 ? 'request' : 'requests'}
                  </span>
                )}
              </div>

              <div className="max-h-96 overflow-y-auto divide-y divide-slate-800/60">
                {loading && notifications.length === 0 ? (
                  <div className="p-8 flex justify-center items-center">
                    <Spinner className="animate-spin text-indigo-400" size={24} />
                  </div>
                ) : notifications.length === 0 ? (
                  <div className="p-8 text-center text-slate-400 space-y-2">
                    <CheckCircle2 size={32} className="mx-auto text-emerald-400 opacity-60" />
                    <p className="text-sm font-medium text-slate-300">
                      {isProfessor ? 'No assistance requests' : 'No access requests yet'}
                    </p>
                    <p className="text-xs text-slate-500">
                      {isProfessor
                        ? 'When students request temporary unblocks or assistance, they will appear here in real time.'
                        : 'If you need access to a restricted tool or website during class, submit a request from your active session.'}
                    </p>
                  </div>
                ) : (
                  notifications.map((req) => {
                    const isPending = req.status === 'pending';
                    const isApproved = req.status === 'approved';
                    const isRejected = req.status === 'rejected';
                    const isProcessing = processingId === req.id;

                    return (
                      <div
                        key={req.id}
                        className={`p-4 transition-colors ${
                          isPending
                            ? 'bg-indigo-950/20 hover:bg-indigo-950/30'
                            : isApproved
                            ? 'bg-emerald-950/10 hover:bg-emerald-950/20'
                            : 'hover:bg-slate-800/40 opacity-80'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2 mb-1.5">
                          <div className="flex items-center gap-2">
                            <div
                              className={`h-7 w-7 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0 ${
                                isApproved
                                  ? 'bg-emerald-600'
                                  : isRejected
                                  ? 'bg-rose-600'
                                  : 'bg-gradient-to-br from-indigo-500 to-brand-600'
                              }`}
                            >
                              {(req.student_name || 'S').charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <p className="text-xs font-bold text-white leading-tight">
                                {isProfessor ? (req.student_name || 'Student') : 'Access Request'}
                              </p>
                              <span className="text-[10px] text-slate-400">{formatTimeAgo(req.created_at)}</span>
                            </div>
                          </div>
                          {getIssueBadge(req.issue_type)}
                        </div>

                        <p className="text-xs text-slate-300 bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/80 mb-3 whitespace-pre-wrap leading-relaxed">
                          {req.description}
                        </p>

                        {isProfessor ? (
                          isPending ? (
                            <div className="flex items-center gap-2">
                              <button
                                disabled={isProcessing}
                                onClick={() => handleResolve(req, 'approved')}
                                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-medium transition-colors shadow-sm"
                              >
                                {isProcessing ? <Spinner size={13} className="animate-spin" /> : <Check size={13} />}
                                Approve & Allow
                              </button>
                              <button
                                disabled={isProcessing}
                                onClick={() => handleResolve(req, 'rejected')}
                                className="flex items-center justify-center gap-1 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 text-xs font-medium transition-colors"
                              >
                                <X size={13} /> Dismiss
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center justify-between text-[11px] pt-1">
                              <span className="text-slate-500 flex items-center gap-1">
                                <Clock size={11} /> Status:
                              </span>
                              <span
                                className={`font-semibold capitalize px-2 py-0.5 rounded-md ${
                                  isApproved
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                    : 'bg-slate-800 text-slate-400'
                                }`}
                              >
                                {req.status}
                              </span>
                            </div>
                          )
                        ) : (
                          /* Student View */
                          <div className="pt-1 space-y-1.5">
                            <div className="flex items-center justify-between text-[11px]">
                              <span className="text-slate-400 flex items-center gap-1">
                                {isApproved ? (
                                  <CheckCircle2 size={13} className="text-emerald-400" />
                                ) : isRejected ? (
                                  <XCircle size={13} className="text-rose-400" />
                                ) : (
                                  <Clock size={13} className="text-amber-400" />
                                )}
                                Decision:
                              </span>
                              <span
                                className={`font-semibold text-xs px-2.5 py-0.5 rounded-lg border ${
                                  isApproved
                                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                                    : isRejected
                                    ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                                    : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                                }`}
                              >
                                {isApproved ? 'Accepted' : isRejected ? 'Denied' : 'Pending Review'}
                              </span>
                            </div>

                            {(req.resolution_notes || isApproved || isRejected) && (
                              <p className="text-[11px] text-slate-400 pl-4 border-l-2 border-slate-700/60 mt-1">
                                {req.resolution_notes ||
                                  (isApproved
                                    ? `Allowed by ${req.resolved_by_name || 'instructor'}`
                                    : `Dismissed by ${req.resolved_by_name || 'instructor'}`)}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 border-l border-slate-800 pl-4">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-semibold text-slate-100">{userName}</p>
            <p className="text-xs text-indigo-400 capitalize">
              {displayRole} {department ? `• ${department}` : ''}
            </p>
          </div>
          <div className="h-9 w-9 rounded-xl bg-indigo-600/20 text-indigo-400 flex items-center justify-center border border-indigo-500/30">
            <User size={18} />
          </div>
        </div>
      </div>
    </header>
  );
};