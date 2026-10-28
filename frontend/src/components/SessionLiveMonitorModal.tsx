import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import {
  X,
  Wifi,
  WifiOff,
  Monitor,
  Clock,
  Users,
  ShieldAlert,
  ShieldCheck,
  Activity,
  Globe,
  Plus,
  Trash2,
  Play,
  Pause,
  AlertTriangle,
  AlertOctagon,
  Square,
  Brain,
  Tag,
  Award,
  Sparkles,
  CheckCircle2,
  Check,
} from 'lucide-react';
import { Session, LogEntry, RuleSet, LiveMonitorStudent, LiveMonitorData } from '../types';
import { getSocket, joinSession } from '../lib/socket';
import {
  getProfessorLiveMonitor,
  getRules,
  createRule,
  quickUpdateRule,
  getSessionLogs,
  pauseSession,
  resumeSession,
  endSession,
  emergencyStopSession,
  getLiveSessionEngagement,
  labelSessionStudentEngagement,
  reviewEngagementPrediction,
  LiveEngagementData,
  LiveEngagementStudent,
} from '../lib/api';

interface SessionLiveMonitorModalProps {
  isOpen: boolean;
  onClose: () => void;
  session: Session;
}

const presenceConfig = {
  online: { color: 'bg-emerald-500', label: 'Online', text: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800' },
  offline: { color: 'bg-amber-400', label: 'Offline', text: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60 border-amber-200 dark:border-amber-800' },
  left: { color: 'bg-rose-400', label: 'Left', text: 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/60 border-rose-200 dark:border-rose-800' },
};

export const SessionLiveMonitorModal: React.FC<SessionLiveMonitorModalProps> = ({
  isOpen,
  onClose,
  session,
}) => {
  const [liveData, setLiveData] = useState<LiveMonitorData | null>(null);
  const [recentLogs, setRecentLogs] = useState<LogEntry[]>([]);
  const [socketConnected, setSocketConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [currentRuleSet, setCurrentRuleSet] = useState<RuleSet | null>(null);
  const [quickItemText, setQuickItemText] = useState('');
  const [quickItemType, setQuickItemType] = useState<'website' | 'application'>('website');
  const [quickRuleMode, setQuickRuleMode] = useState<'blocked' | 'allowed'>('blocked');
  const [sessionStatus, setSessionStatus] = useState(session.status || 'Active');
  const [isTogglingStatus, setIsTogglingStatus] = useState(false);
  const [blockSuccessMsg, setBlockSuccessMsg] = useState('');

  // Derived lists for Blocked and Allowed Websites & Applications
  const allowedWebsites = useMemo(() => {
    if (!currentRuleSet) return [];
    const fromList = currentRuleSet.allowed_websites || [];
    const fromRules = currentRuleSet.website_rules
      ? currentRuleSet.website_rules.filter((r) => r.rule_mode === 'allowed' && r.is_enabled !== false).map((r) => r.domain_pattern)
      : [];
    const fromLegacy = currentRuleSet.mode === 'Allowlist' ? (currentRuleSet.websites || []) : [];
    return Array.from(new Set([...fromList, ...fromRules, ...fromLegacy])).filter(Boolean);
  }, [currentRuleSet]);

  const blockedWebsites = useMemo(() => {
    if (!currentRuleSet) return [];
    const fromList = currentRuleSet.blocked_websites || [];
    const fromRules = currentRuleSet.website_rules
      ? currentRuleSet.website_rules.filter((r) => r.rule_mode === 'blocked' && r.is_enabled !== false).map((r) => r.domain_pattern)
      : [];
    const fromLegacy = currentRuleSet.mode !== 'Allowlist' ? (currentRuleSet.websites || []) : [];
    return Array.from(new Set([...fromList, ...fromRules, ...fromLegacy])).filter(Boolean);
  }, [currentRuleSet]);

  const allowedApplications = useMemo(() => {
    if (!currentRuleSet) return [];
    const fromList = currentRuleSet.allowed_applications || [];
    const fromRules = currentRuleSet.application_rules
      ? currentRuleSet.application_rules.filter((r) => r.rule_mode === 'allowed' && r.is_enabled !== false).map((r) => r.application_name)
      : [];
    const fromLegacy = currentRuleSet.mode === 'Allowlist' ? (currentRuleSet.applications || []) : [];
    return Array.from(new Set([...fromList, ...fromRules, ...fromLegacy])).filter(Boolean);
  }, [currentRuleSet]);

  const blockedApplications = useMemo(() => {
    if (!currentRuleSet) return [];
    const fromList = currentRuleSet.blocked_applications || [];
    const fromRules = currentRuleSet.application_rules
      ? currentRuleSet.application_rules.filter((r) => r.rule_mode === 'blocked' && r.is_enabled !== false).map((r) => r.application_name)
      : [];
    const fromLegacy = currentRuleSet.mode !== 'Allowlist' ? (currentRuleSet.applications || []) : [];
    return Array.from(new Set([...fromList, ...fromRules, ...fromLegacy])).filter(Boolean);
  }, [currentRuleSet]);

  const isPaused = (liveData?.status || sessionStatus).toLowerCase() === 'paused';
  const isEnded = (liveData?.status || sessionStatus).toLowerCase() === 'ended' || (liveData?.status || sessionStatus).toLowerCase() === 'completed';

  const [liveEngagement, setLiveEngagement] = useState<LiveEngagementData | null>(null);
  const [activeViewTab, setActiveViewTab] = useState<'presence' | 'engagement'>('presence');
  const [labellingStudent, setLabellingStudent] = useState<LiveEngagementStudent | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<'High' | 'Medium' | 'Low'>('High');
  const [labelNotes, setLabelNotes] = useState('');
  const [isSavingLabel, setIsSavingLabel] = useState(false);

  const [reviewingStudent, setReviewingStudent] = useState<LiveEngagementStudent | null>(null);
  const [reviewOverrideLabel, setReviewOverrideLabel] = useState<'High' | 'Medium' | 'Low'>('High');
  const [isSavingReview, setIsSavingReview] = useState(false);

  const [isEndingSession, setIsEndingSession] = useState(false);
  const [isEmergencyModalOpen, setIsEmergencyModalOpen] = useState(false);
  const [emergencyReason, setEmergencyReason] = useState('');
  const [isEmergencyStopping, setIsEmergencyStopping] = useState(false);

  const handleEndSession = async () => {
    if (!window.confirm('Are you sure you want to END this session? All device restrictions will be revoked immediately.')) {
      return;
    }
    setIsEndingSession(true);
    try {
      await endSession(session._id);
      setSessionStatus('ended');
      if (liveData) setLiveData({ ...liveData, status: 'ended' });
      setBlockSuccessMsg('Session ended. All student device protections revoked.');
      setTimeout(() => setBlockSuccessMsg(''), 5000);
    } catch (err: any) {
      alert(err.message || 'Failed to end session');
    } finally {
      setIsEndingSession(false);
    }
  };

  const handleEmergencyStop = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsEmergencyStopping(true);
    try {
      await emergencyStopSession(session._id, emergencyReason || 'Professor authorized emergency stop');
      setIsEmergencyModalOpen(false);
      setSessionStatus('ended');
      if (liveData) setLiveData({ ...liveData, status: 'ended' });
      setBlockSuccessMsg('EMERGENCY STOP executed. All student restrictions halted.');
      setTimeout(() => setBlockSuccessMsg(''), 5000);
    } catch (err: any) {
      alert(err.message || 'Emergency stop failed');
    } finally {
      setIsEmergencyStopping(false);
    }
  };

  const handleTogglePauseResume = async () => {
    setIsTogglingStatus(true);
    try {
      if (isPaused) {
        await resumeSession(session._id);
        setSessionStatus('active');
        if (liveData) setLiveData({ ...liveData, status: 'active' });
      } else {
        await pauseSession(session._id);
        setSessionStatus('paused');
        if (liveData) setLiveData({ ...liveData, status: 'paused' });
      }
    } catch (err: any) {
      alert(err.message || 'Failed to update session status');
    } finally {
      setIsTogglingStatus(false);
    }
  };

  const loadRuleSet = useCallback(async () => {
    try {
      const rules = await getRules();
      let found = session.ruleSetId ? rules.find((r) => r._id === session.ruleSetId) : null;
      if (!found && session.batchIds && session.batchIds.length > 0) {
        found = rules.find((r: any) => session.batchIds!.includes(r.batch_id || '') || session.batchIds!.includes(r.batchId || '')) || null;
      }
      if (!found && rules.length > 0) {
        found = rules[0];
      }
      if (found) {
        setCurrentRuleSet(found);
        return found;
      }
    } catch (err) {
      console.warn('[monitor] Failed to load rule set:', err);
    }
    return null;
  }, [session.ruleSetId, session.batchIds]);

  const seenEventIdsRef = useRef<Set<string>>(new Set());

  const fetchLiveMonitorData = useCallback(async () => {
    try {
      const data = await getProfessorLiveMonitor(session._id);
      setLiveData(data);
      setError('');
    } catch (err: any) {
      console.warn('[monitor] Failed to fetch live data:', err);
      setError(err.message || 'Failed to load live monitor data');
    } finally {
      setLoading(false);
    }
  }, [session._id]);

  const fetchEngagementData = useCallback(async () => {
    try {
      const data = await getLiveSessionEngagement(session._id);
      setLiveEngagement(data);
    } catch (err: any) {
      console.warn('[monitor] Failed to fetch live engagement features:', err);
    }
  }, [session._id]);

  const fetchSessionLogs = useCallback(async () => {
    try {
      const logs = await getSessionLogs(session._id);
      if (logs && Array.isArray(logs)) {
        setRecentLogs(logs.slice(0, 50));
      }
    } catch (err) {
      console.warn('[monitor] Failed to fetch session logs:', err);
    }
  }, [session._id]);

  const handleSaveLabel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!labellingStudent) return;
    setIsSavingLabel(true);
    try {
      await labelSessionStudentEngagement(session._id, labellingStudent.student_id, selectedLabel, labelNotes);
      setBlockSuccessMsg(`Ground truth label saved for ${labellingStudent.student_name}: ${selectedLabel}`);
      setLabellingStudent(null);
      setLabelNotes('');
      await fetchEngagementData();
      setTimeout(() => setBlockSuccessMsg(''), 5000);
    } catch (err: any) {
      alert(err.message || 'Failed to save engagement label');
    } finally {
      setIsSavingLabel(false);
    }
  };

  const handleSaveReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewingStudent || !reviewingStudent.latest_prediction_id) return;
    setIsSavingReview(true);
    try {
      await reviewEngagementPrediction(reviewingStudent.latest_prediction_id, reviewOverrideLabel);
      setBlockSuccessMsg(`Advisory prediction reviewed for ${reviewingStudent.student_name}: ${reviewOverrideLabel}`);
      setReviewingStudent(null);
      await fetchEngagementData();
      setTimeout(() => setBlockSuccessMsg(''), 5000);
    } catch (err: any) {
      alert(err.message || 'Failed to review prediction');
    } finally {
      setIsSavingReview(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadRuleSet();
      fetchLiveMonitorData();
      fetchEngagementData();
      fetchSessionLogs();
    }
  }, [isOpen, loadRuleSet, fetchLiveMonitorData, fetchEngagementData, fetchSessionLogs]);

  const handleQuickRuleUpdate = async (
    action: 'add' | 'remove',
    type: 'website' | 'application',
    item: string,
    ruleMode: 'blocked' | 'allowed' = 'blocked'
  ) => {
    const cleanItem = item.trim();
    if (!cleanItem) return;

    let targetRuleSet = currentRuleSet;
    if (!targetRuleSet) {
      targetRuleSet = await loadRuleSet();
    }
    if (!targetRuleSet) {
      try {
        const created = await createRule(
          `${session.course || 'Class'} Policy`,
          ruleMode === 'allowed' ? 'Allowlist' : 'Blocklist',
          type === 'website' ? [cleanItem] : [],
          type === 'application' ? [cleanItem] : [],
          session.batchIds && session.batchIds[0] ? session.batchIds[0] : undefined
        );
        setCurrentRuleSet(created);
        return;
      } catch (err: any) {
        alert(err.message || 'Failed to initialize policy for session');
        return;
      }
    }

    try {
      const updated = await quickUpdateRule(targetRuleSet._id, {
        action,
        type,
        item: cleanItem,
        rule_mode: ruleMode,
      } as any);
      setCurrentRuleSet(updated);
    } catch (err: any) {
      alert(err.message || 'Failed to update rule');
    }
  };

  const handleAddBlockItem = async (e: React.FormEvent) => {
    e.preventDefault();
    let rawText = quickItemText.trim();
    if (!rawText) return;

    let targetType: 'website' | 'application' = quickItemType;
    const lower = rawText.toLowerCase();

    // Auto-detect application processes (.exe, .app) even if "website" was selected
    if (lower.endsWith('.exe') || lower.endsWith('.app')) {
      targetType = 'application';
    } else if (lower.includes('://') || ['.com', '.org', '.net', '.io', '.ai', '.edu', '.in', '.gov', '.co', '.xyz'].some(ext => lower.includes(ext))) {
      targetType = 'website';
      // Clean domain URL
      if (rawText.includes('://')) {
        try {
          rawText = new URL(rawText).hostname;
        } catch {
          rawText = rawText.split('://')[1].split('/')[0];
        }
      } else {
        rawText = rawText.split('/')[0].split('?')[0].split('#')[0];
      }
    }

    if (isPaused) {
      try {
        await resumeSession(session._id);
        setSessionStatus('active');
        if (liveData) setLiveData({ ...liveData, status: 'active' });
      } catch (err) {
        console.warn('Auto-resume failed:', err);
      }
    }

    await handleQuickRuleUpdate('add', targetType, rawText, quickRuleMode);
    setQuickItemText('');
    setBlockSuccessMsg(`Successfully ${quickRuleMode === 'allowed' ? 'allowed' : 'blocked'} "${rawText}" live! Policy active.`);
    setTimeout(() => setBlockSuccessMsg(''), 4000);
  };

  // Socket setup & real-time updates
  useEffect(() => {
    if (!isOpen) return;

    const socket = getSocket();
    joinSession(session._id);

    const onConnect = () => setSocketConnected(true);
    const onDisconnect = () => setSocketConnected(false);

    // Event: student_joined / presence_updated
    const handlePresenceUpdate = (eventPayload: any) => {
      if (eventPayload.session_id !== session._id && eventPayload.sessionId !== session._id) return;

      const studentId = eventPayload.student_id || eventPayload.studentId;
      const studentName = eventPayload.name || eventPayload.studentName || 'Student';
      const participantStatus = (eventPayload.participant_status || 'joined') as 'joined' | 'left';
      const presenceStatus = (eventPayload.presence_status || 'online') as 'online' | 'offline';
      const connectionSource = eventPayload.connection_source || 'browser';
      const lastSeenAt = eventPayload.last_seen_at || new Date().toISOString();
      const activityLabel = (eventPayload.latest_activity || 'PRESENCE_UPDATED').toUpperCase();

      setLiveData((prev) => {
        const base = prev || {
          session_id: session._id,
          batch_name: session.course,
          session_title: session.title,
          status: sessionStatus,
          students: [],
          online_count: 0,
          joined_count: 0,
          enforcing_count: 0,
          violation_count: 0,
        };

        const updatedStudents = [...base.students];
        const existingIdx = updatedStudents.findIndex((s) => s.student_id === studentId);

        const existing = existingIdx >= 0 ? updatedStudents[existingIdx] : null;
        const newItem: LiveMonitorStudent = {
          student_id: studentId,
          name: studentName,
          participant_status: participantStatus,
          presence_status: presenceStatus,
          last_seen_at: lastSeenAt,
          connection_source: connectionSource,
          engagement_score: eventPayload.engagement_score ?? existing?.engagement_score ?? null,
          latest_activity: activityLabel,
          violation_count: eventPayload.violation_count ?? existing?.violation_count ?? 0,
          enforcement_status: eventPayload.enforcement_status ?? existing?.enforcement_status,
        };

        if (existingIdx >= 0) {
          updatedStudents[existingIdx] = newItem;
        } else {
          updatedStudents.push(newItem);
        }

        const onlineCount = updatedStudents.filter(
          (s) => s.participant_status === 'joined' && s.presence_status === 'online'
        ).length;
        const joinedCount = updatedStudents.filter((s) => s.participant_status === 'joined').length;

        return {
          ...base,
          students: updatedStudents,
          online_count: onlineCount,
          joined_count: joinedCount,
        };
      });

      // Routine heartbeats and keepalives must NOT flood the activity feed
      const isRoutineHeartbeat =
        !activityLabel ||
        activityLabel === 'PRESENCE_UPDATED' ||
        activityLabel === 'HEARTBEAT' ||
        activityLabel === 'PING';

      if (isRoutineHeartbeat) {
        return;
      }

      // Real state transitions (e.g. STUDENT_JOINED, STUDENT_LEFT)
      const readableAction = activityLabel.replace(/_/g, ' ');
      let details = `${studentName} - ${readableAction.toLowerCase()}`;
      if (activityLabel === 'STUDENT_JOINED') {
        details = `${studentName} joined the session`;
      } else if (activityLabel === 'STUDENT_LEFT') {
        details = `${studentName} left the session`;
      }

      // Deduplicate: ignore identical event for same student within 15 seconds
      setRecentLogs((prev) => {
        const isDuplicate = prev.slice(0, 8).some(
          (l) => l.studentName === studentName && (l.details === details || l.resource === activityLabel)
        );
        if (isDuplicate) return prev;

        const presenceLog: LogEntry = {
          _id: `presence-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type: 'EVENT',
          studentId: studentId,
          studentName: studentName,
          sessionId: session._id,
          resource: activityLabel === 'STUDENT_JOINED' ? 'Joined Session Room' : (activityLabel === 'STUDENT_LEFT' ? 'Left Session Room' : activityLabel),
          details: details,
          isViolation: false,
          timestamp: lastSeenAt,
        };
        return [presenceLog, ...prev].slice(0, 50);
      });
    };

    // Event: session_ended
    const handleSessionEnded = (eventPayload: any) => {
      if (eventPayload.session_id !== session._id && eventPayload.sessionId !== session._id) return;
      setLiveData((prev) => (prev ? { ...prev, status: 'ended' } : prev));
    };

    // Event: engagement_features_updated
    const handleEngagementUpdate = (eventPayload: any) => {
      if (eventPayload.session_id !== session._id) return;
      const student = eventPayload.student;
      if (!student) return;
      setLiveEngagement((prev) => {
        if (!prev) return prev;
        const list = [...prev.students];
        const idx = list.findIndex((s) => s.student_id === student.student_id);
        if (idx >= 0) {
          list[idx] = student;
        } else {
          list.push(student);
        }
        return { ...prev, students: list };
      });
    };

    // Event: live_log_update (authoritative real-time stream for violations and student activity)
    const handleLiveLogUpdate = (payload: any) => {
      if (!payload) return;
      const evSessionId = String(payload.sessionId || payload.session_id || '').trim();
      if (evSessionId && evSessionId !== session._id) return;

      const studentId = payload.studentId || payload.student_id;
      const studentName = payload.studentName || payload.student_name || 'Student';
      const action = payload.resource || payload.action || payload.activeApp || payload.target_value || 'Activity';
      const actLower = String(action).trim().toLowerCase();

      // Guard: internal system actions must not be processed as activity or violations
      if (
        actLower === 'policy_restored' ||
        actLower === 'system' ||
        actLower === 'heartbeat' ||
        actLower === 'state_transition' ||
        actLower === 'policy_delivered' ||
        actLower === 'policy_acknowledged'
      ) {
        return;
      }

      const eventKey = String(payload._id || payload.event_id || payload.id || `${studentId}_${actLower}_${payload.timestamp || ''}`);
      if (seenEventIdsRef.current.has(eventKey)) {
        return;
      }
      seenEventIdsRef.current.add(eventKey);

      const isViolation = Boolean(payload.isViolation || payload.is_violation || payload.type === 'VIOLATION');
      const details = payload.details || payload.description || `${studentName} - ${isViolation ? 'Violation: ' : ''}${action}`;

      const normalizedLog: LogEntry = {
        _id: eventKey,
        type: payload.type || (isViolation ? 'VIOLATION' : 'EVENT'),
        studentId: studentId || '',
        studentName: studentName,
        sessionId: session._id,
        resource: action,
        details: details,
        isViolation: isViolation,
        timestamp: payload.timestamp || payload.occurred_at || new Date().toISOString(),
      };

      setRecentLogs((prev) => {
        if (prev.some((item) => item._id === normalizedLog._id)) return prev;
        return [normalizedLog, ...prev].slice(0, 50);
      });

      setLiveData((prev) => {
        const base = prev || {
          session_id: session._id,
          batch_name: session.course,
          session_title: session.title,
          status: sessionStatus,
          students: [],
          online_count: 0,
          joined_count: 0,
          enforcing_count: 0,
          violation_count: 0,
        };
        const newViolCount = isViolation ? (base.violation_count || 0) + 1 : base.violation_count;
        let matched = false;
        const updatedStudents = base.students.map((s) => {
          const isMatch = (studentId && s.student_id === studentId) || (s.name && s.name.toLowerCase() === studentName.toLowerCase());
          if (isMatch) {
            matched = true;
            const actStr = String(action || '').toLowerCase();
            const resStr = String(payload.resource || '').toLowerCase();
            const isProc = actStr.endsWith('.exe') || resStr.endsWith('.exe') || payload.category === 'Process';
            const isUsb = actStr.includes('usb') || resStr.includes('usb') || actStr.includes('drive');
            const isWeb = !isProc && !isUsb && (actStr.includes('.') || actStr.includes('://') || payload.category === 'Web');
            const actLabel = isViolation
              ? (isProc ? `Blocked App: ${action}` : isUsb ? `Blocked USB: ${action}` : (isWeb ? `Restricted Site: ${action}` : `Violation: ${action}`))
              : action;
            return {
              ...s,
              presence_status: 'online' as const,
              last_seen_at: payload.timestamp || new Date().toISOString(),
              latest_activity: actLabel,
              violation_count: (s.violation_count || 0) + (isViolation ? 1 : 0),
            };
          }
          return s;
        });

        if (!matched && studentId) {
          const actStr = String(action || '').toLowerCase();
          const resStr = String(payload.resource || '').toLowerCase();
          const isProc = actStr.endsWith('.exe') || resStr.endsWith('.exe') || payload.category === 'Process';
          const isUsb = actStr.includes('usb') || resStr.includes('usb') || actStr.includes('drive');
          const isWeb = !isProc && !isUsb && (actStr.includes('.') || actStr.includes('://') || payload.category === 'Web');
          const actLabel = isViolation
            ? (isProc ? `Blocked App: ${action}` : isUsb ? `Blocked USB: ${action}` : (isWeb ? `Restricted Site: ${action}` : `Violation: ${action}`))
            : action;
          updatedStudents.push({
            student_id: studentId,
            name: studentName,
            participant_status: 'joined',
            presence_status: 'online',
            last_seen_at: payload.timestamp || new Date().toISOString(),
            latest_activity: actLabel,
            connection_source: 'agent',
            violation_count: isViolation ? 1 : 0,
            engagement_score: payload.engagementScore ?? null,
          });
        }

        return {
          ...base,
          violation_count: newViolCount,
          students: updatedStudents,
        };
      });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('student_joined', handlePresenceUpdate);
    socket.on('presence_updated', handlePresenceUpdate);
    socket.on('student_left', handlePresenceUpdate);
    socket.on('session_ended', handleSessionEnded);
    socket.on('engagement_features_updated', handleEngagementUpdate);
    socket.on('live_log_update', handleLiveLogUpdate);
    socket.on('student_telemetry', handleLiveLogUpdate);
    socket.on('policy_violation', handleLiveLogUpdate);

    if (socket.connected) setSocketConnected(true);

    // Periodic poll refresh to keep data synchronized
    const pollInterval = setInterval(() => {
      fetchLiveMonitorData();
      fetchEngagementData();
      fetchSessionLogs();
    }, 5000);

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('student_joined', handlePresenceUpdate);
      socket.off('presence_updated', handlePresenceUpdate);
      socket.off('student_left', handlePresenceUpdate);
      socket.off('session_ended', handleSessionEnded);
      socket.off('engagement_features_updated', handleEngagementUpdate);
      socket.off('live_log_update', handleLiveLogUpdate);
      socket.off('student_telemetry', handleLiveLogUpdate);
      socket.off('policy_violation', handleLiveLogUpdate);
      clearInterval(pollInterval);
    };
  }, [isOpen, session._id, fetchLiveMonitorData, fetchEngagementData, fetchSessionLogs]);

  // Escape key to close
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const studentsList = liveData?.students || [];
  const onlineCount = liveData?.online_count || 0;
  const joinedCount = liveData?.joined_count || 0;
  const localViolationCount = recentLogs.filter((l) => l.isViolation).length;
  const violationCount = Math.max(liveData?.violation_count || 0, localViolationCount);

  const endTime = new Date(session.endTime);
  const now = new Date();
  const timeLeftMs = Math.max(0, endTime.getTime() - now.getTime());
  const timeLeftMin = Math.ceil(timeLeftMs / 60_000);

  return (
    <div className="fixed inset-0 z-50 flex flex-col animate-fade-in">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-900/70 backdrop-blur-sm" onClick={onClose} />

      {/* Modal Content */}
      <div className="relative flex-1 flex flex-col m-3 md:m-6 bg-white dark:bg-slate-900 rounded-2xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-700">
        {/* ─── Header ───────────────────────────────────────────────── */}
        <div className="shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-900">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Live Command Center
              </h2>
            </div>
            <span className="text-sm text-slate-500 dark:text-slate-400 hidden sm:inline">
              — {session.title}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
              socketConnected
                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                : 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800'
            }`}>
              {socketConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
              {socketConnected ? 'Connected' : 'Disconnected'}
            </span>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* ─── Summary Stats Bar ────────────────────────────────────── */}
        <div className="shrink-0 grid grid-cols-2 sm:grid-cols-5 gap-3 px-6 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Users size={18} className="text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Portal Online</p>
              <p className="text-base font-bold text-slate-900 dark:text-white">
                {onlineCount}<span className="text-xs font-normal text-slate-400"> / {joinedCount} Joined</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-100 dark:bg-emerald-900/30 rounded-lg">
              <ShieldCheck size={18} className="text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Enforcing Devices</p>
              <p className="text-base font-bold text-emerald-600 dark:text-emerald-400">
                {isEnded ? 0 : (liveData?.enforcing_count ?? (sessionStatus.toLowerCase() === 'active' ? joinedCount : 0))} Active
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-rose-100 dark:bg-rose-900/30 rounded-lg">
              <ShieldAlert size={18} className="text-rose-600 dark:text-rose-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Violations</p>
              <p className="text-base font-bold text-rose-600 dark:text-rose-400">
                {violationCount}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isEnded ? 'bg-slate-100 dark:bg-slate-800' : isPaused ? 'bg-amber-100 dark:bg-amber-900/30' : 'bg-emerald-100 dark:bg-emerald-900/30'}`}>
              <Clock size={18} className={isEnded ? 'text-slate-400' : isPaused ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'} />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400">Session Lifecycle</p>
              <div className="flex items-center gap-2">
                <p className="text-base font-bold text-slate-900 dark:text-white capitalize">
                  {liveData?.status || sessionStatus}
                </p>
                {!isEnded && (
                  <button
                    onClick={handleTogglePauseResume}
                    disabled={isTogglingStatus}
                    className={`text-[11px] px-2 py-0.5 rounded font-medium transition-colors flex items-center gap-1 cursor-pointer ${
                      isPaused
                        ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-200'
                        : 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 hover:bg-amber-200'
                    }`}
                    title={isPaused ? 'Resume Session (Enforce Rules)' : 'Pause Session (Suspend Rules)'}
                  >
                    {isPaused ? <><Play size={11} /> Resume</> : <><Pause size={11} /> Pause</>}
                  </button>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-col justify-center gap-1.5 col-span-2 sm:col-span-1 border-t sm:border-t-0 sm:border-l border-slate-200 dark:border-slate-700 pt-2 sm:pt-0 sm:pl-3">
            <button
              onClick={handleEndSession}
              disabled={isEndingSession || isEnded}
              className="px-2.5 py-1 text-xs bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold rounded-lg transition-colors flex items-center justify-center gap-1 cursor-pointer disabled:opacity-50"
              title="Gracefully end session and unblock endpoints"
            >
              <Square size={11} className="text-slate-500" />
              {isEndingSession ? 'Ending...' : isEnded ? 'Session Ended' : 'End Session'}
            </button>
            <button
              onClick={() => setIsEmergencyModalOpen(true)}
              disabled={isEnded}
              className="px-2.5 py-1 text-xs bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-colors flex items-center justify-center gap-1 shadow-xs cursor-pointer disabled:opacity-50"
              title="Emergency Stop: Immediately restore network adapters and revoke all policies"
            >
              <AlertOctagon size={12} />
              Emergency Stop
            </button>
          </div>
        </div>

        {/* ─── Paused Session Alert Banner ──────────────────────────── */}
        {isPaused && (
          <div className="shrink-0 px-6 py-2.5 bg-amber-500/15 border-b border-amber-500/30 flex items-center justify-between gap-3 text-xs animate-in fade-in">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300 font-medium">
              <AlertTriangle size={16} className="shrink-0 text-amber-500" />
              <span>Session is currently <strong>PAUSED</strong>. Website and application restrictions on student computers are temporarily suspended.</span>
            </div>
            <button
              onClick={handleTogglePauseResume}
              disabled={isTogglingStatus}
              className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-lg text-xs transition-colors flex items-center gap-1.5 shadow-xs shrink-0 cursor-pointer disabled:opacity-50"
            >
              <Play size={13} /> Resume Session & Enforce
            </button>
          </div>
        )}

        {/* ─── Live Block Feedback Toast ────────────────────────────── */}
        {blockSuccessMsg && (
          <div className="shrink-0 px-6 py-2 bg-emerald-50 dark:bg-emerald-950/40 border-b border-emerald-200 dark:border-emerald-800/40 flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-300 font-medium animate-in fade-in">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            <span>✓ {blockSuccessMsg}</span>
          </div>
        )}

        {/* ─── Live Policy Control Bar ─────────────────────────────── */}
        {currentRuleSet && (
          <div className="shrink-0 px-6 py-3 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-200 dark:border-slate-800 flex flex-col gap-3">
            {/* Top row: Blocked & Allowed lists */}
            <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3">
              <div className="flex-1 space-y-2">
                {/* Active Blocking Section */}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-bold text-rose-700 dark:text-rose-400 flex items-center gap-1 uppercase tracking-wide mr-1 shrink-0">
                    <Globe size={14} className="text-rose-500" /> Active Blocking:
                  </span>

                  {blockedWebsites.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mr-2">
                      <span className="text-[11px] font-semibold text-slate-500">Domains:</span>
                      {blockedWebsites.map((w) => (
                        <span
                          key={`block-site-${w}`}
                          className="inline-flex items-center gap-1 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 px-2 py-0.5 rounded-full border border-rose-200 dark:border-rose-800/60 font-mono shadow-2xs text-[11px]"
                        >
                          🌐 {w}
                          <button
                            onClick={() => handleQuickRuleUpdate('remove', 'website', w, 'blocked')}
                            className="hover:text-red-500 transition-colors ml-0.5 font-bold cursor-pointer"
                            title={`Unblock ${w}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  {blockedApplications.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-slate-500">Apps:</span>
                      {blockedApplications.map((a) => (
                        <span
                          key={`block-app-${a}`}
                          className="inline-flex items-center gap-1 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full border border-purple-200 dark:border-purple-800/60 font-mono shadow-2xs text-[11px]"
                        >
                          💻 {a}
                          <button
                            onClick={() => handleQuickRuleUpdate('remove', 'application', a, 'blocked')}
                            className="hover:text-red-500 transition-colors ml-0.5 font-bold cursor-pointer"
                            title={`Unblock ${a}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  {blockedWebsites.length === 0 && blockedApplications.length === 0 && (
                    <span className="text-slate-400 italic text-[11px]">No items blocked in active rule set</span>
                  )}
                </div>

                {/* Active Allowlist Section */}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-bold text-emerald-700 dark:text-emerald-400 flex items-center gap-1 uppercase tracking-wide mr-1 shrink-0">
                    <CheckCircle2 size={14} className="text-emerald-500" /> Active Allowlist:
                  </span>

                  {allowedWebsites.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mr-2">
                      <span className="text-[11px] font-semibold text-slate-500">Allowed Websites:</span>
                      {allowedWebsites.map((w) => (
                        <span
                          key={`allow-site-${w}`}
                          className="inline-flex items-center gap-1 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800/60 font-mono shadow-2xs text-[11px]"
                        >
                          🌐 {w}
                          <button
                            onClick={() => handleQuickRuleUpdate('remove', 'website', w, 'allowed')}
                            className="hover:text-red-500 transition-colors ml-0.5 font-bold cursor-pointer"
                            title={`Remove allowed ${w}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  {allowedApplications.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-slate-500">Allowed Apps:</span>
                      {allowedApplications.map((a) => (
                        <span
                          key={`allow-app-${a}`}
                          className="inline-flex items-center gap-1 bg-teal-50 dark:bg-teal-950/40 text-teal-700 dark:text-teal-300 px-2 py-0.5 rounded-full border border-teal-200 dark:border-teal-800/60 font-mono shadow-2xs text-[11px]"
                        >
                          💻 {a}
                          <button
                            onClick={() => handleQuickRuleUpdate('remove', 'application', a, 'allowed')}
                            className="hover:text-red-500 transition-colors ml-0.5 font-bold cursor-pointer"
                            title={`Remove allowed ${a}`}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  {allowedWebsites.length === 0 && allowedApplications.length === 0 && (
                    <span className="text-slate-400 italic text-[11px]">No specific allowed websites/apps configured (standard internet access)</span>
                  )}
                </div>
              </div>

              {/* Quick Policy Add Form */}
              <form onSubmit={handleAddBlockItem} className="flex flex-wrap sm:flex-nowrap items-center gap-2 w-full lg:w-auto shrink-0">
                <select
                  value={quickRuleMode}
                  onChange={(e) => setQuickRuleMode(e.target.value as 'blocked' | 'allowed')}
                  className={`text-xs py-1.5 px-2 font-semibold border rounded-lg transition-colors ${
                    quickRuleMode === 'allowed'
                      ? 'bg-emerald-50 dark:bg-emerald-950/60 border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300'
                      : 'bg-rose-50 dark:bg-rose-950/60 border-rose-300 dark:border-rose-700 text-rose-800 dark:text-rose-300'
                  }`}
                >
                  <option value="blocked">🚫 Block</option>
                  <option value="allowed">✅ Allow</option>
                </select>
                <select
                  value={quickItemType}
                  onChange={(e) => setQuickItemType(e.target.value as 'website' | 'application')}
                  className="text-xs py-1.5 px-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-800 dark:text-slate-200"
                >
                  <option value="website">🌐 Website Domain</option>
                  <option value="application">💻 App (.exe)</option>
                </select>
                <input
                  type="text"
                  placeholder={quickItemType === 'website' ? 'e.g. docs.python.org' : 'e.g. code.exe'}
                  value={quickItemText}
                  onChange={(e) => setQuickItemText(e.target.value)}
                  className="text-xs py-1.5 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-brand-500 min-w-[170px]"
                />
                <button
                  type="submit"
                  className={`text-xs py-1.5 px-3 font-semibold rounded-lg transition-colors shadow-2xs whitespace-nowrap cursor-pointer text-white ${
                    quickRuleMode === 'allowed'
                      ? 'bg-emerald-600 hover:bg-emerald-700'
                      : 'bg-rose-600 hover:bg-rose-700'
                  }`}
                >
                  {quickRuleMode === 'allowed' ? '+ Allow Live' : '+ Block Live'}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* ─── Mode Tab Switcher ───────────────────────────────────── */}
        <div className="shrink-0 px-6 pt-2 pb-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveViewTab('presence')}
              className={`pb-2.5 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
                activeViewTab === 'presence'
                  ? 'border-brand-600 text-brand-600 dark:text-brand-400 dark:border-brand-400'
                  : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              <ShieldCheck size={14} />
              Presence & Protection ({studentsList.length})
            </button>
            <button
              onClick={() => setActiveViewTab('engagement')}
              className={`pb-2.5 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
                activeViewTab === 'engagement'
                  ? 'border-brand-600 text-brand-600 dark:text-brand-400 dark:border-brand-400'
                  : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              <Brain size={14} />
              Engagement Telemetry & Labelling
              <span className="px-1.5 py-0.5 bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 rounded text-[10px]">
                5-Min Windows
              </span>
            </button>
          </div>

          <div className="hidden sm:flex items-center gap-2 text-[11px] text-slate-500 pb-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span>Strict Privacy-Preserving Features (No Screen/Keystroke/Content Logging)</span>
          </div>
        </div>

        {/* ─── Body: Student Grid + Activity Feed OR Engagement View ─── */}
        {activeViewTab === 'presence' ? (
          <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
            {/* Student Cards Grid */}
            <div className="flex-1 overflow-y-auto p-6">
              <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-4">
                Students ({studentsList.length})
              </h3>
              {studentsList.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                  <Users size={48} className="mb-4 opacity-40" />
                  <p className="text-base font-semibold text-slate-700 dark:text-slate-300">
                    No students have joined this session yet
                  </p>
                  <p className="text-xs mt-1 max-w-sm text-center text-slate-500">
                    When a student clicks "Join Session" in their dashboard, their live status will appear here in real time.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {studentsList.map((student) => {
                    const isJoined = student.participant_status === 'joined';
                    const isOnline = isJoined && student.presence_status === 'online';
                    const presence = !isJoined ? presenceConfig.left : isOnline ? presenceConfig.online : presenceConfig.offline;
                    const studentViolCount = Math.max(
                      student.violation_count || 0,
                      recentLogs.filter((l) => l.isViolation && (l.studentId === student.student_id || (l.studentName && l.studentName.toLowerCase() === student.name.toLowerCase()))).length
                    );
                    const hasViolations = studentViolCount > 0;

                    return (
                      <div
                        key={student.student_id}
                        className={`relative p-4 rounded-xl border transition-all duration-300 ${
                          !isJoined
                            ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50/30 dark:bg-rose-950/10 opacity-75'
                            : hasViolations
                            ? 'border-rose-300 dark:border-rose-800 bg-rose-50/25 dark:bg-rose-950/20 shadow-xs ring-1 ring-rose-500/25'
                            : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:shadow-md'
                        }`}
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-2.5">
                            <div className="relative">
                              <div className="h-10 w-10 rounded-full bg-gradient-to-br from-brand-500 to-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
                                {student.name.charAt(0).toUpperCase()}
                              </div>
                              <span className={`absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full ${presence.color} ring-2 ring-white dark:ring-slate-800`} />
                            </div>
                            <div>
                              <p className="font-semibold text-slate-900 dark:text-white text-sm leading-tight">
                                {student.name}
                              </p>
                              <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                                {isJoined && student.connection_source !== 'none' ? `Source: ${student.connection_source}` : 'Disconnected'}
                              </p>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            {/* Presence Badge */}
                            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border ${presence.text}`}>
                              {isOnline ? '🟢 Online' : isJoined ? '🟡 Offline' : '🚪 Left'}
                            </span>
                            
                            {/* Policy Status Badge */}
                            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border ${
                              student.policy_status === 'active'
                                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                                : student.policy_status === 'restored'
                                ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800'
                                : student.policy_status === 'failed'
                                ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800'
                                : 'bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                            }`}>
                              🛡️ Policy: {student.policy_status || (isEnded ? 'Revoked' : 'Active')}
                            </span>

                            {/* USB Compliance Badge */}
                            {student.usb_storage_status && (
                              <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border ${
                                student.usb_storage_status === 'active'
                                  ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                                  : student.usb_storage_status === 'requires_managed_device'
                                  ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                                  : student.usb_storage_status === 'not_compliant'
                                  ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800'
                                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700'
                              }`}>
                                🔌 USB: {
                                  student.usb_storage_status === 'requires_managed_device'
                                    ? 'Req Managed Device'
                                    : student.usb_storage_status.toUpperCase()
                                }
                              </span>
                            )}

                            {/* Engagement State Badge */}
                            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border ${
                              student.engagement_state === 'high'
                                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                                : student.engagement_state === 'low'
                                ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800'
                                : student.engagement_state === 'medium'
                                ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                                : student.engagement_state === 'final'
                                ? 'bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800'
                                : student.engagement_state === 'data_insufficient'
                                ? 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700'
                                : 'bg-sky-50 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800'
                            }`}>
                              🧠 {
                                student.engagement_state === 'collecting_live_data' || !student.engagement_state
                                  ? 'Collecting Live Data'
                                  : student.engagement_state.replace('_', ' ')
                              }
                            </span>
                          </div>
                        </div>

                        {/* Violations and Blocked Attempts */}
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          {hasViolations ? (
                            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800 flex items-center gap-1 animate-pulse">
                              <ShieldAlert size={10} /> {studentViolCount} {studentViolCount === 1 ? 'Violation' : 'Violations'}
                            </span>
                          ) : (
                            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-emerald-50/80 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/40 flex items-center gap-1">
                              <ShieldCheck size={10} /> 0 Violations
                            </span>
                          )}

                          {((student.blocked_website_attempts || 0) > 0 || (student.blocked_app_attempts || 0) > 0) && (
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-50 dark:bg-rose-950/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900">
                              Blocked: {student.blocked_website_attempts || 0} Web, {student.blocked_app_attempts || 0} App
                            </span>
                          )}
                        </div>

                        {/* Academic Activity Breakdown Chips */}
                        {student.academic_activity_summary && Object.keys(student.academic_activity_summary).length > 0 && (
                          <div className="pt-2 pb-1 border-t border-slate-100 dark:border-slate-700/60">
                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                              Academic Activity Breakdown
                            </span>
                            <div className="flex flex-wrap gap-1">
                              {Object.entries(student.academic_activity_summary).slice(0, 3).map(([item, sec]) => (
                                <span key={item} className="text-[10px] bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60 px-1.5 py-0.5 rounded font-mono">
                                  {item}: {Math.round(sec / 60)}m
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 mt-2 pt-2 border-t border-slate-100 dark:border-slate-700">
                          <span className="truncate">
                            Activity: <strong className={`font-mono ${hasViolations && String(student.latest_activity).toLowerCase().includes('block') ? 'text-rose-600 dark:text-rose-400' : 'text-slate-700 dark:text-slate-200'}`}>{student.latest_activity}</strong>
                          </span>
                          <span className="text-[10px] font-mono text-slate-400 shrink-0">
                            {student.last_seen_at ? new Date(student.last_seen_at).toLocaleTimeString() : 'N/A'}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Activity Feed Sidebar */}
            <div className="lg:w-80 xl:w-96 shrink-0 border-t lg:border-t-0 lg:border-l border-slate-200 dark:border-slate-700 flex flex-col bg-slate-50/50 dark:bg-slate-800/30 overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-2">
                  <Activity size={14} />
                  Activity Feed
                </h3>
                <span className="text-xs text-slate-400 bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded-full">
                  {recentLogs.length}
                </span>
              </div>
              <div className="flex-1 overflow-y-auto">
                {recentLogs.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-8">No real-time events recorded yet</p>
                ) : (
                  <div className="divide-y divide-slate-100 dark:divide-slate-700/50">
                    {recentLogs.slice(0, 30).map((log) => (
                      <div key={log._id} className="px-4 py-2.5 hover:bg-white dark:hover:bg-slate-800 transition-colors">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <p className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                                {log.studentName}
                              </p>
                              {log.isViolation && (
                                <span className="px-1.5 py-0.2 rounded text-[9px] font-bold uppercase bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300 border border-rose-200 dark:border-rose-900">
                                  Violation
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">
                              {log.details || log.resource || 'Session Event'}
                            </p>
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono whitespace-nowrap shrink-0">
                            {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* ─── Engagement Telemetry & Labelling Dashboard ──────────── */
          <div className="flex-1 overflow-y-auto p-6 space-y-5">
            {/* Telemetry & Model Status Header Banner */}
            <div className="p-4 rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-gradient-to-r from-indigo-50/70 via-brand-50/40 to-slate-50 dark:from-indigo-950/30 dark:via-brand-950/20 dark:to-slate-900 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Brain size={18} className="text-indigo-600 dark:text-indigo-400" />
                  <h3 className="font-bold text-slate-900 dark:text-white text-sm">
                    Live Privacy-Minimized Engagement Feature Streams
                  </h3>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                    prediction_available: false
                  </span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 max-w-2xl leading-relaxed">
                  The Local Agent flushes aggregated real-time rolling windows. Telemetry is strictly privacy-minimized: zero screenshots, zero keystrokes, and zero file contents. Real-time features are ready for ML training and live inference.
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs px-3 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-slate-700 dark:text-slate-300">
                  Windows Recorded: <strong>{liveEngagement?.students.reduce((acc, s) => acc + s.window_count, 0) || 0}</strong>
                </span>
                {isEnded ? (
                  <span className="text-xs px-3 py-1.5 rounded-lg bg-purple-100 dark:bg-purple-950/70 text-purple-800 dark:text-purple-300 border border-purple-200 dark:border-purple-800 font-semibold flex items-center gap-1">
                    <Award size={13} /> Session Completed — Labelling Active
                  </span>
                ) : (
                  <span className="text-xs px-3 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-950/70 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 font-semibold flex items-center gap-1">
                    <Sparkles size={13} /> Real-time Feature Ingestion Active
                  </span>
                )}
              </div>
            </div>

            {/* Students Engagement Feature Cards */}
            {(!liveEngagement || liveEngagement.students.length === 0) ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                <Brain size={48} className="mb-4 opacity-40" />
                <p className="text-base font-semibold text-slate-700 dark:text-slate-300">
                  No engagement feature windows recorded yet
                </p>
                <p className="text-xs mt-1 max-w-md text-center text-slate-500">
                  Active local agents submit privacy-minimized real-time rolling windows during the session. Features update live via professor-scoped WebSocket.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {liveEngagement.students.map((st) => {
                  const academicMins = (st.total_academic_seconds / 60).toFixed(1);
                  const nonAcademicMins = (st.total_non_academic_seconds / 60).toFixed(1);
                  const idleMins = (st.total_idle_seconds / 60).toFixed(1);
                  const academicPct = Math.round(st.academic_ratio * 100);

                  return (
                    <div
                      key={`eng-${st.student_id}`}
                      className="p-5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/90 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
                    >
                      <div>
                        {/* Header */}
                        <div className="flex items-start justify-between gap-3 mb-3">
                          <div>
                            <h4 className="font-bold text-slate-900 dark:text-white text-sm">
                              {st.student_name}
                            </h4>
                            <p className="text-[11px] text-slate-400 font-mono">
                              {st.student_email || st.student_id}
                            </p>
                          </div>
                          {st.label ? (
                            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                              st.label === 'High'
                                ? 'bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800'
                                : st.label === 'Medium'
                                ? 'bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-800'
                                : 'bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-800'
                            }`}>
                              Label: {st.label}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono text-slate-400 bg-slate-100 dark:bg-slate-700/50">
                              Unlabelled
                            </span>
                          )}
                        </div>

                        {/* Ratios & Safe Indices */}
                        <div className="grid grid-cols-2 gap-2 mb-4 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 text-xs">
                          <div>
                            <span className="text-[10px] text-slate-400 uppercase font-semibold">Academic Ratio</span>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className="font-bold text-sm text-slate-800 dark:text-slate-100">{academicPct}%</span>
                              <div className="flex-1 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                <div className="h-full bg-brand-500 rounded-full" style={{ width: `${Math.min(100, academicPct)}%` }} />
                              </div>
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400 uppercase font-semibold">Focus Stability</span>
                            <p className="font-bold text-sm text-indigo-600 dark:text-indigo-400 mt-0.5 font-mono">
                              {st.focus_stability_index.toFixed(2)}
                            </p>
                          </div>
                        </div>

                        {/* ML Preliminary Engagement Advisory Prediction */}
                        <div className="mb-3 p-2.5 rounded-xl border border-indigo-100 dark:border-indigo-900/50 bg-indigo-50/50 dark:bg-indigo-950/30 text-xs">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 flex items-center gap-1">
                              <Brain size={12} />
                              ML Engagement Advisory
                            </span>
                            {st.prediction_available && st.predicted_engagement ? (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-200/60 dark:bg-indigo-900/80 text-indigo-800 dark:text-indigo-200 font-semibold uppercase">
                                {st.review_status === 'reviewed' ? 'Reviewed' : 'Preliminary'}
                              </span>
                            ) : null}
                          </div>

                          {st.prediction_available && st.predicted_engagement ? (
                            <div className="space-y-1.5">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1.5">
                                  <span className={`px-2 py-0.5 rounded text-xs font-black uppercase ${
                                    st.predicted_engagement === 'High'
                                      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                                      : st.predicted_engagement === 'Medium'
                                      ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
                                      : 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300'
                                  }`}>
                                    {st.predicted_engagement}
                                  </span>
                                  {st.professor_override_label && (
                                    <span className="text-[10px] text-slate-500 line-through">
                                      {st.professor_override_label}
                                    </span>
                                  )}
                                </div>
                                <span className="text-xs font-bold text-slate-700 dark:text-slate-300 font-mono">
                                  {st.confidence ? `${Math.round(st.confidence * 100)}% Conf.` : ''}
                                </span>
                              </div>

                              {/* Probabilities */}
                              <div className="grid grid-cols-3 gap-1 text-[10px] text-slate-500 dark:text-slate-400 font-mono pt-1 border-t border-indigo-100 dark:border-indigo-900/40">
                                <div>H: {st.probability_high ? `${Math.round(st.probability_high * 100)}%` : '0%'}</div>
                                <div>M: {st.probability_medium ? `${Math.round(st.probability_medium * 100)}%` : '0%'}</div>
                                <div>L: {st.probability_low ? `${Math.round(st.probability_low * 100)}%` : '0%'}</div>
                              </div>

                              <div className="flex items-center justify-between pt-1 text-[9px] text-slate-400">
                                <span>Model: {st.model_version || 'rf-latest'}</span>
                                {st.latest_prediction_id && (
                                  <button
                                    onClick={() => {
                                      setReviewingStudent(st);
                                      setReviewOverrideLabel((st.predicted_engagement as any) || 'High');
                                    }}
                                    className="text-indigo-600 dark:text-indigo-400 hover:underline font-semibold cursor-pointer"
                                  >
                                    Review / Override
                                  </button>
                                )}
                              </div>
                            </div>
                          ) : (
                            <div className="py-1 text-[11px] text-slate-500 dark:text-slate-400 italic">
                              {st.prediction_reason || 'Waiting for enough live session data (min. 5m)'}
                            </div>
                          )}
                        </div>

                        {/* Raw Aggregated Feature Values */}
                        <div className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300 mb-4 font-mono">
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Academic Active:</span>
                            <span className="font-semibold text-slate-800 dark:text-slate-100">{academicMins}m ({st.total_academic_seconds}s)</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Non-Academic Active:</span>
                            <span>{nonAcademicMins}m</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">System Idle Time:</span>
                            <span>{idleMins}m</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Application Switches:</span>
                            <span>{st.total_switches}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Policy Violations:</span>
                            <span className={st.total_policy_violations > 0 ? 'text-rose-600 font-bold' : ''}>
                              {st.total_policy_violations} ({st.violation_rate_per_hour}/hr)
                            </span>
                          </div>
                          <div className="flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-800 text-[11px]">
                            <span className="text-slate-400">5-Min Windows:</span>
                            <span>{st.window_count} {st.last_window_at ? `(last ${new Date(st.last_window_at).toLocaleTimeString()})` : ''}</span>
                          </div>
                        </div>
                      </div>

                      {/* Footer: Labelling Actions */}
                      <div className="pt-3 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between gap-2">
                        {isEnded ? (
                          <button
                            onClick={() => {
                              setLabellingStudent(st);
                              setSelectedLabel(st.label || 'High');
                              setLabelNotes('');
                            }}
                            className="w-full py-1.5 px-3 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 shadow-2xs cursor-pointer"
                          >
                            <Tag size={12} />
                            {st.label ? 'Update Ground Truth Label' : 'Assign Ground Truth Label'}
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-400 italic">
                            Ground truth labelling unlocks after session completion
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ─── Ground Truth Labelling Modal Dialog ──────────────────── */}
        {labellingStudent && (
          <div className="fixed inset-0 z-70 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-brand-500/30 shadow-2xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5 text-brand-600 dark:text-brand-400">
                  <Award size={22} />
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Ground Truth Engagement Labelling
                  </h3>
                </div>
                <button
                  onClick={() => setLabellingStudent(null)}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700 text-xs space-y-1">
                <p className="font-semibold text-slate-900 dark:text-white">
                  {labellingStudent.student_name}
                </p>
                <p className="text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                  {labellingStudent.student_email || labellingStudent.student_id}
                </p>
                <div className="pt-2 mt-2 border-t border-slate-200 dark:border-slate-700 grid grid-cols-2 gap-2 font-mono text-[11px] text-slate-600 dark:text-slate-300">
                  <span>Academic Time: {(labellingStudent.total_academic_seconds / 60).toFixed(1)}m</span>
                  <span>Focus Stability: {labellingStudent.focus_stability_index.toFixed(2)}</span>
                  <span>Idle Time: {(labellingStudent.total_idle_seconds / 60).toFixed(1)}m</span>
                  <span>App Switches: {labellingStudent.total_switches}</span>
                </div>
              </div>

              <form onSubmit={handleSaveLabel} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-2">
                    Select Human Ground Truth Label
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {(['High', 'Medium', 'Low'] as const).map((lvl) => (
                      <button
                        key={lvl}
                        type="button"
                        onClick={() => setSelectedLabel(lvl)}
                        className={`py-2 px-3 rounded-xl border text-xs font-bold transition-all cursor-pointer ${
                          selectedLabel === lvl
                            ? lvl === 'High'
                              ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                              : lvl === 'Medium'
                              ? 'bg-amber-500 text-white border-amber-500 shadow-sm'
                              : 'bg-rose-600 text-white border-rose-600 shadow-sm'
                            : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300'
                        }`}
                      >
                        {lvl === 'High' ? '🟢 High' : lvl === 'Medium' ? '🟡 Medium' : '🔴 Low'}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">
                    Professor Observational Notes (Optional)
                  </label>
                  <textarea
                    rows={2}
                    placeholder="e.g. Completed lab assignments promptly with high concentration"
                    value={labelNotes}
                    onChange={(e) => setLabelNotes(e.target.value)}
                    className="w-full text-xs px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setLabellingStudent(null)}
                    className="px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSavingLabel}
                    className="px-4 py-1.5 text-xs bg-brand-600 hover:bg-brand-700 text-white font-bold rounded-lg shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <CheckCircle2 size={13} />
                    {isSavingLabel ? 'Saving...' : 'Save Label'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ─── Advisory Prediction Review & Override Dialog ──────────── */}
        {reviewingStudent && (
          <div className="fixed inset-0 z-70 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-indigo-500/30 shadow-2xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5 text-indigo-600 dark:text-indigo-400">
                  <Brain size={22} />
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Review Advisory Engagement Prediction
                  </h3>
                </div>
                <button
                  onClick={() => setReviewingStudent(null)}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="p-3 bg-indigo-50 dark:bg-indigo-950/40 rounded-xl border border-indigo-100 dark:border-indigo-900/60 text-xs">
                <p className="font-semibold text-slate-800 dark:text-slate-100">
                  Student: {reviewingStudent.student_name}
                </p>
                <p className="text-slate-500 mt-0.5">
                  Model Estimated: <span className="font-bold text-indigo-600">{reviewingStudent.predicted_engagement}</span> ({Math.round((reviewingStudent.confidence || 0) * 100)}% confidence)
                </p>
                <p className="text-[11px] text-slate-400 mt-1 italic">
                  Note: Preliminary estimates never trigger auto-penalties, grading changes, or cheating flags. Your override is recorded for training feedback.
                </p>
              </div>

              <form onSubmit={handleSaveReview} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-2">
                    Override Engagement Rating
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {(['High', 'Medium', 'Low'] as const).map((lvl) => (
                      <button
                        key={lvl}
                        type="button"
                        onClick={() => setReviewOverrideLabel(lvl)}
                        className={`py-2 px-3 rounded-xl border text-xs font-bold transition-all cursor-pointer ${
                          reviewOverrideLabel === lvl
                            ? lvl === 'High'
                              ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                              : lvl === 'Medium'
                              ? 'bg-amber-500 text-white border-amber-500 shadow-sm'
                              : 'bg-rose-600 text-white border-rose-600 shadow-sm'
                            : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300'
                        }`}
                      >
                        {lvl === 'High' ? '🟢 High' : lvl === 'Medium' ? '🟡 Medium' : '🔴 Low'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setReviewingStudent(null)}
                    className="px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSavingReview}
                    className="px-4 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <CheckCircle2 size={13} />
                    {isSavingReview ? 'Saving...' : 'Confirm Review'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ─── Emergency Stop Modal ─────────────────────────────────── */}
        {isEmergencyModalOpen && (
          <div className="fixed inset-0 z-60 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-red-500/40 shadow-2xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
                <AlertOctagon size={28} />
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Authorized Emergency Stop</h3>
              </div>

              <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                Emergency Stop immediately terminates the classroom session, halts all endpoint restrictions, flushes hosts modifications, and restores student adapters without waiting for expiration.
              </p>

              <form onSubmit={handleEmergencyStop} className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">
                    Emergency Reason (Audited)
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Network infrastructure emergency / drill"
                    value={emergencyReason}
                    onChange={(e) => setEmergencyReason(e.target.value)}
                    className="w-full text-xs px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-red-500"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsEmergencyModalOpen(false)}
                    className="px-3 py-1.5 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isEmergencyStopping}
                    className="px-4 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <AlertOctagon size={13} />
                    {isEmergencyStopping ? 'Stopping...' : 'Confirm Emergency Stop'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
