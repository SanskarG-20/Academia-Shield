import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
  BarChart3,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Filter,
  RefreshCw,
  Users,
  Info,
  ChevronDown,
  X,
  Search,
  Check,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
  ArrowUpDown,
  Laptop,
  Globe,
  Flame,
  HelpCircle,
  Cpu,
  Sparkles,
} from 'lucide-react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip as RechartsTooltip,
  Legend,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts';
import {
  fetchProfessorEngagementBatches,
  fetchProfessorEngagementBatchSessions,
  fetchProfessorSessionEngagement,
  fetchProfessorStudentPredictionHistory,
  reviewEngagementPrediction,
  getMLModels,
  trainMLModel,
  approveMLModel,
  MLModelInfo,
  EngagementBatchItem,
  EngagementSessionItem,
  StudentEngagementRowItem,
  SessionEngagementDetailResponse,
  StudentPredictionHistoryItem,
} from '../lib/api';
import { getSocket, subscribeEngagement } from '../lib/socket';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';

// Storage key for harmless UI filter preferences
const STORAGE_STATUS_FILTER_KEY = 'engagement_ui_status_filter';

export const StudentEngagement: React.FC = () => {
  // ---------------------------------------------------------------------------
  // 1. Filter Control Panel State
  // ---------------------------------------------------------------------------
  const [batches, setBatches] = useState<EngagementBatchItem[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<string>('');
  const [sessions, setSessions] = useState<EngagementSessionItem[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'All' | 'Active' | 'Completed'>(() => {
    const saved = localStorage.getItem(STORAGE_STATUS_FILTER_KEY);
    return saved === 'Active' || saved === 'Completed' || saved === 'All' ? saved : 'All';
  });
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  // ---------------------------------------------------------------------------
  // 2. Data & Loading States
  // ---------------------------------------------------------------------------
  const [loadingBatches, setLoadingBatches] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingEngagement, setLoadingEngagement] = useState(false);
  const [sessionDetail, setSessionDetail] = useState<SessionEngagementDetailResponse | null>(null);
  const [students, setStudents] = useState<StudentEngagementRowItem[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // 3. Real-time Telemetry & WebSocket State
  // ---------------------------------------------------------------------------
  const [socketConnected, setSocketConnected] = useState(false);
  const [lastLiveEventAt, setLastLiveEventAt] = useState<Date | null>(null);
  const [recentlyUpdatedStudentId, setRecentlyUpdatedStudentId] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // 4. Student Detail Drawer State
  // ---------------------------------------------------------------------------
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedStudentForDrawer, setSelectedStudentForDrawer] = useState<StudentEngagementRowItem | null>(null);
  const [studentHistory, setStudentHistory] = useState<StudentPredictionHistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // ---------------------------------------------------------------------------
  // 5. Professor Review Modal State
  // ---------------------------------------------------------------------------
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [selectedStudentForReview, setSelectedStudentForReview] = useState<StudentEngagementRowItem | null>(null);
  const [reviewAction, setReviewAction] = useState<'confirm' | 'override'>('confirm');
  const [overrideLabel, setOverrideLabel] = useState<'High' | 'Medium' | 'Low'>('High');
  const [reviewNotes, setReviewNotes] = useState<string>('');
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewSuccessMessage, setReviewSuccessMessage] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // 5b. ML Model Selection & Management Modal State
  // ---------------------------------------------------------------------------
  const [showModelModal, setShowModelModal] = useState(false);
  const [mlModels, setMlModels] = useState<MLModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelActionId, setModelActionId] = useState<string | null>(null);
  const [trainingNewModel, setTrainingNewModel] = useState(false);
  const [modelFeedbackMsg, setModelFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadModels = useCallback(async () => {
    setLoadingModels(true);
    try {
      const list = await getMLModels();
      setMlModels(Array.isArray(list) ? list : []);
    } catch (err: any) {
      console.error('Failed to load ML models:', err);
    } finally {
      setLoadingModels(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // 6. Table Search, Filter, Sort, & Pagination State
  // ---------------------------------------------------------------------------
  const [tableSearch, setTableSearch] = useState<string>('');
  const [tableEngagementFilter, setTableEngagementFilter] = useState<'All' | 'High' | 'Medium' | 'Low' | 'Waiting'>('All');
  const [sortBy, setSortBy] = useState<'confidence' | 'idle_time' | 'blocked_attempts' | 'last_update'>('confidence');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);

  // Remember harmless UI filter preference
  const handleStatusFilterChange = (filter: 'All' | 'Active' | 'Completed') => {
    setStatusFilter(filter);
    try {
      localStorage.setItem(STORAGE_STATUS_FILTER_KEY, filter);
    } catch {
      // ignore
    }
  };

  // ---------------------------------------------------------------------------
  // API Fetch 1: Batches owned by professor
  // ---------------------------------------------------------------------------
  const loadBatches = useCallback(() => {
    setLoadingBatches(true);
    setErrorMessage(null);
    fetchProfessorEngagementBatches()
      .then((data) => {
        setBatches(data);
        if (data.length > 0) {
          setSelectedBatchId((prev) => (prev && data.some((b) => b.id === prev) ? prev : data[0].id));
        } else {
          setSelectedBatchId('');
        }
      })
      .catch((err) => {
        console.error('Failed to load professor batches:', err);
        setErrorMessage(err.message || 'Failed to load batches');
      })
      .finally(() => {
        setLoadingBatches(false);
      });
  }, []);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  // ---------------------------------------------------------------------------
  // API Fetch 2: Sessions for selected batch
  // ---------------------------------------------------------------------------
  const loadSessions = useCallback(() => {
    if (!selectedBatchId) {
      setSessions([]);
      setSelectedSessionId('');
      return;
    }

    setLoadingSessions(true);
    setErrorMessage(null);

    fetchProfessorEngagementBatchSessions(
      selectedBatchId,
      statusFilter,
      startDate || undefined,
      endDate || undefined
    )
      .then((sessList) => {
        setSessions(sessList);

        if (sessList.length === 0) {
          setSelectedSessionId('');
          setSessionDetail(null);
          setStudents([]);
          return;
        }

        // Default behavior: Select professor's most recent active session if exists, otherwise most recent completed
        setSelectedSessionId((prev) => {
          if (prev && sessList.some((s) => s.id === prev)) {
            return prev;
          }
          const mostRecentActive = sessList.find(
            (s) => s.is_active || s.status.toLowerCase() === 'active'
          );
          return mostRecentActive ? mostRecentActive.id : sessList[0].id;
        });
      })
      .catch((err) => {
        console.error('Failed to load batch sessions:', err);
        setErrorMessage(err.message || 'Failed to load batch sessions');
      })
      .finally(() => {
        setLoadingSessions(false);
      });
  }, [selectedBatchId, statusFilter, startDate, endDate]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // ---------------------------------------------------------------------------
  // API Fetch 3: Session Engagement Detail
  // ---------------------------------------------------------------------------
  const loadSessionEngagement = useCallback((sessionId: string) => {
    if (!sessionId) {
      setSessionDetail(null);
      setStudents([]);
      return;
    }

    setLoadingEngagement(true);
    setErrorMessage(null);

    fetchProfessorSessionEngagement(sessionId)
      .then((detail) => {
        setSessionDetail(detail);
        setStudents(detail.students || []);
        setCurrentPage(1);
      })
      .catch((err) => {
        console.error('Failed to load session engagement:', err);
        setErrorMessage(err.message || 'Failed to load session engagement');
        setSessionDetail(null);
        setStudents([]);
      })
      .finally(() => {
        setLoadingEngagement(false);
      });
  }, []);

  useEffect(() => {
    if (selectedSessionId) {
      loadSessionEngagement(selectedSessionId);
    }
  }, [selectedSessionId, loadSessionEngagement]);

  const handleApproveModel = async (modelId: string) => {
    setModelActionId(modelId);
    setModelFeedbackMsg(null);
    try {
      await approveMLModel(modelId);
      setModelFeedbackMsg({ type: 'success', text: 'Model successfully approved and activated for live engagement inference!' });
      await loadModels();
      if (selectedSessionId) {
        loadSessionEngagement(selectedSessionId);
      }
    } catch (err: any) {
      setModelFeedbackMsg({ type: 'error', text: err.message || 'Failed to approve model' });
    } finally {
      setModelActionId(null);
    }
  };

  const handleTrainBestModel = async () => {
    setTrainingNewModel(true);
    setModelFeedbackMsg(null);
    try {
      const newModel = await trainMLModel({ n_estimators: 100, version_tag: `rf-v${Date.now().toString().slice(-4)}-optimal` });
      if (newModel && newModel.id) {
        await approveMLModel(newModel.id);
      }
      setModelFeedbackMsg({ type: 'success', text: 'Trained and activated optimal RandomForest engagement model!' });
      await loadModels();
      if (selectedSessionId) {
        loadSessionEngagement(selectedSessionId);
      }
    } catch (err: any) {
      setModelFeedbackMsg({ type: 'error', text: err.message || 'Failed to train model' });
    } finally {
      setTrainingNewModel(false);
    }
  };

  // ---------------------------------------------------------------------------
  // WebSocket Live Subscription for Active Sessions
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!selectedSessionId) return;

    const socket = getSocket();
    setSocketConnected(socket.connected);

    const onConnect = () => {
      setSocketConnected(true);
      subscribeEngagement(selectedSessionId);
    };

    const onDisconnect = () => {
      setSocketConnected(false);
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);

    // Subscribe immediately
    subscribeEngagement(selectedSessionId);

    // Real-time prediction event handler
    const handlePredictionUpdate = (payload: any) => {
      if (!payload || String(payload.session_id) !== String(selectedSessionId)) {
        return;
      }

      setLastLiveEventAt(new Date());
      const studentId = payload.student_id;
      const predData = payload.prediction || {};
      const safeMetrics = payload.safe_metrics || {};

      setRecentlyUpdatedStudentId(studentId);
      setTimeout(() => setRecentlyUpdatedStudentId(null), 3000);

      setStudents((prev) => {
        const studentExists = prev.some((s) => s.student_id === studentId);
        if (!studentExists) {
          // Student joined or received prediction but is not yet in table, refresh
          loadSessionEngagement(selectedSessionId);
          return prev;
        }

        return prev.map((s) => {
          if (s.student_id !== studentId) return s;

          return {
            ...s,
            allowed_academic_application_active_seconds:
              safeMetrics.allowed_academic_application_active_seconds !== undefined
                ? Number(safeMetrics.allowed_academic_application_active_seconds)
                : s.allowed_academic_application_active_seconds,
            allowed_academic_website_active_seconds:
              safeMetrics.allowed_academic_website_active_seconds !== undefined
                ? Number(safeMetrics.allowed_academic_website_active_seconds)
                : s.allowed_academic_website_active_seconds,
            allowed_academic_active_seconds:
              safeMetrics.allowed_academic_active_seconds !== undefined
                ? Number(safeMetrics.allowed_academic_active_seconds)
                : s.allowed_academic_active_seconds,
            academic_activity_seconds:
              safeMetrics.allowed_academic_active_seconds !== undefined
                ? Number(safeMetrics.allowed_academic_active_seconds)
                : safeMetrics.academic_active_seconds !== undefined
                ? Number(safeMetrics.academic_active_seconds)
                : s.academic_activity_seconds,
            non_academic_activity_seconds:
              safeMetrics.non_academic_active_seconds !== undefined
                ? Number(safeMetrics.non_academic_active_seconds)
                : s.non_academic_activity_seconds,
            idle_seconds:
              safeMetrics.idle_seconds !== undefined
                ? Number(safeMetrics.idle_seconds)
                : s.idle_seconds,
            unknown_or_unavailable_seconds:
              safeMetrics.unknown_or_unavailable_seconds !== undefined
                ? Number(safeMetrics.unknown_or_unavailable_seconds)
                : s.unknown_or_unavailable_seconds,
            feature_completeness_percent:
              safeMetrics.feature_completeness_percent !== undefined
                ? Number(safeMetrics.feature_completeness_percent)
                : s.feature_completeness_percent,
            approved_apps_summary:
              safeMetrics.approved_resources_breakdown?.applications ||
              safeMetrics.approved_apps_summary ||
              s.approved_apps_summary,
            approved_websites_summary:
              safeMetrics.approved_resources_breakdown?.websites ||
              safeMetrics.approved_websites_summary ||
              s.approved_websites_summary,
            application_switch_count:
              safeMetrics.application_switch_count !== undefined
                ? Number(safeMetrics.application_switch_count)
                : s.application_switch_count,
            blocked_website_attempt_count:
              safeMetrics.blocked_website_attempt_count !== undefined
                ? Number(safeMetrics.blocked_website_attempt_count)
                : s.blocked_website_attempt_count,
            unauthorized_application_attempt_count:
              safeMetrics.unauthorized_application_attempt_count !== undefined
                ? Number(safeMetrics.unauthorized_application_attempt_count)
                : s.unauthorized_application_attempt_count,
            policy_violation_count:
              safeMetrics.policy_violation_count !== undefined
                ? Number(safeMetrics.policy_violation_count)
                : s.policy_violation_count,
            engagement_estimate:
              predData.prediction !== undefined ? predData.prediction : s.engagement_estimate,
            confidence:
              predData.confidence !== undefined ? predData.confidence : s.confidence,
            probability_high:
              predData.probability_high !== undefined ? predData.probability_high : s.probability_high,
            probability_medium:
              predData.probability_medium !== undefined ? predData.probability_medium : s.probability_medium,
            probability_low:
              predData.probability_low !== undefined ? predData.probability_low : s.probability_low,
            collection_status:
              predData.collection_status || s.collection_status,
            prediction_type:
              predData.prediction_type === 'final' ? 'Final' : 'Live Preliminary',
            prediction_available:
              predData.prediction_available !== undefined
                ? Boolean(predData.prediction_available)
                : s.prediction_available,
            prediction_reason:
              predData.reason !== undefined ? predData.reason : s.prediction_reason,
            last_updated_time: payload.last_updated || new Date().toISOString(),
            prediction_id: predData.id || s.prediction_id,
            model_version: predData.model_version_tag || s.model_version,
          };
        });
      });
    };

    // Real-time student joined and presence update handlers
    const handleStudentJoinedOrPresence = (payload: any) => {
      if (!payload) return;
      const sId = payload.session_id || (payload.room && payload.room.replace('session_', ''));
      if (!sId || String(sId) === String(selectedSessionId)) {
        loadSessionEngagement(selectedSessionId);
      }
    };

    // Real-time policy violation event handler for instant live counting
    const handlePolicyViolationOrLog = (payload: any) => {
      if (!payload) return;
      const isViol = Boolean(
        payload.isViolation ||
        payload.is_violation ||
        payload.type === 'VIOLATION' ||
        String(payload.action || '').toLowerCase() === 'blocked'
      );
      if (!isViol) return;

      const sId = payload.sessionId || payload.session_id;
      if (sId && selectedSessionId && String(sId).trim() !== String(selectedSessionId).trim()) {
        return;
      }

      setLastLiveEventAt(new Date());

      const studentId = payload.studentId || payload.student_id;
      const studentName = String(payload.studentName || payload.student_name || '').toLowerCase();
      const resLower = String(
        payload.resource || payload.activeApp || payload.action || payload.domain || payload.target_value || ''
      ).toLowerCase();
      const catLower = String(payload.category || payload.violation_type || '').toLowerCase();

      const isProc = catLower === 'process' || resLower.endsWith('.exe') || payload.is_proc || payload.violation_type === 'process';
      const isWeb = !isProc && (catLower === 'web' || resLower.includes('.') || resLower.includes('://') || payload.is_web || payload.violation_type === 'web');

      let matchedId: string | null = null;

      setStudents((prev) => {
        let found = false;
        const updated = prev.map((s) => {
          const isMatch =
            (studentId && s.student_id === studentId) ||
            (studentName && s.student_name.toLowerCase() === studentName);

          if (isMatch) {
            found = true;
            matchedId = s.student_id;
            return {
              ...s,
              policy_violation_count: (s.policy_violation_count || 0) + 1,
              unauthorized_application_attempt_count:
                (s.unauthorized_application_attempt_count || 0) + (isProc ? 1 : 0),
              blocked_website_attempt_count:
                (s.blocked_website_attempt_count || 0) + (isWeb ? 1 : 0),
              session_status: 'Joined',
              last_updated_time: payload.timestamp || new Date().toISOString(),
            };
          }
          return s;
        });

        if (!found) {
          // If student wasn't loaded in local state yet, trigger a refresh
          if (selectedSessionId) {
            loadSessionEngagement(selectedSessionId);
          }
          return prev;
        }

        return updated;
      });

      if (matchedId) {
        setRecentlyUpdatedStudentId(matchedId);
        setTimeout(() => setRecentlyUpdatedStudentId(null), 3500);
      }
    };

    const handleCollectionStarted = (payload: any) => {
      if (!payload || String(payload.session_id) !== String(selectedSessionId)) return;
      setLastLiveEventAt(new Date());
      const studentId = payload.student_id;
      setStudents((prev) =>
        prev.map((s) => {
          if (s.student_id !== studentId) return s;
          return {
            ...s,
            collection_status: 'collecting',
            prediction_type: 'Collecting',
            prediction_available: false,
            engagement_estimate: null,
            confidence: null,
            prediction_reason: payload.message || 'Collecting live engagement data. Calculating estimate from active telemetry...',
            valid_windows_received: payload.valid_windows_received ?? s.valid_windows_received,
            session_elapsed_seconds: payload.session_elapsed_seconds ?? s.session_elapsed_seconds,
            last_updated_time: payload.last_telemetry_at || new Date().toISOString(),
          };
        })
      );
    };

    const handleDataInsufficient = (payload: any) => {
      if (!payload || String(payload.session_id) !== String(selectedSessionId)) return;
      setLastLiveEventAt(new Date());
      const studentId = payload.student_id;
      setStudents((prev) =>
        prev.map((s) => {
          if (s.student_id !== studentId) return s;
          return {
            ...s,
            collection_status: 'data_insufficient',
            prediction_available: false,
            engagement_estimate: null,
            confidence: null,
            prediction_reason: payload.reason || 'More valid activity data is required for an estimate.',
            last_updated_time: payload.last_telemetry_at || new Date().toISOString(),
          };
        })
      );
    };

    const handleFeaturesUpdated = (payload: any) => {
      if (!payload || String(payload.session_id) !== String(selectedSessionId)) return;
      setLastLiveEventAt(new Date());
      const stud = payload.student;
      if (!stud) return;
      setStudents((prev) =>
        prev.map((s) => {
          if (s.student_id !== stud.student_id) return s;
          return {
            ...s,
            allowed_academic_application_active_seconds: stud.allowed_academic_application_active_seconds ?? s.allowed_academic_application_active_seconds,
            allowed_academic_website_active_seconds: stud.allowed_academic_website_active_seconds ?? s.allowed_academic_website_active_seconds,
            allowed_academic_active_seconds: stud.total_academic_seconds ?? s.allowed_academic_active_seconds,
            academic_activity_seconds: stud.total_academic_seconds ?? s.academic_activity_seconds,
            non_academic_activity_seconds: stud.total_non_academic_seconds ?? s.non_academic_activity_seconds,
            idle_seconds: stud.total_idle_seconds ?? s.idle_seconds,
            unknown_or_unavailable_seconds: stud.unknown_or_unavailable_seconds ?? s.unknown_or_unavailable_seconds,
            feature_completeness_percent: stud.feature_completeness_percent ?? s.feature_completeness_percent,
            approved_apps_summary: stud.approved_apps_summary ?? s.approved_apps_summary,
            approved_websites_summary: stud.approved_websites_summary ?? s.approved_websites_summary,
            application_switch_count: stud.total_switches ?? s.application_switch_count,
            unauthorized_application_attempt_count: stud.total_unauthorized_attempts ?? s.unauthorized_application_attempt_count,
            blocked_website_attempt_count: stud.total_blocked_website_attempts ?? s.blocked_website_attempt_count,
            policy_violation_count: stud.total_policy_violations ?? s.policy_violation_count,
            last_updated_time: payload.timestamp || new Date().toISOString(),
          };
        })
      );
    };

    const handlePredictionFinalized = (payload: any) => {
      if (!payload || String(payload.session_id) !== String(selectedSessionId)) return;
      setLastLiveEventAt(new Date());
      const studentId = payload.student_id;
      setStudents((prev) =>
        prev.map((s) => {
          if (s.student_id !== studentId) return s;
          return {
            ...s,
            engagement_estimate: payload.prediction,
            confidence: payload.confidence,
            probability_high: payload.probability_high,
            probability_medium: payload.probability_medium,
            probability_low: payload.probability_low,
            prediction_type: 'Final',
            collection_status: 'final_prediction',
            prediction_available: true,
            prediction_reason: null,
            prediction_id: payload.prediction_id || s.prediction_id,
            last_updated_time: payload.last_updated || new Date().toISOString(),
          };
        })
      );
    };

    const handleModelStatusChanged = (payload: any) => {
      if (payload?.status === 'approved') {
        setSessionDetail((prev) => (prev ? { ...prev, has_active_model: true, model_version_tag: payload.version_tag } : prev));
      }
      loadModels();
    };

    socket.on('engagement_prediction_updated', handlePredictionUpdate);
    socket.on('engagement_collection_started', handleCollectionStarted);
    socket.on('engagement_data_insufficient', handleDataInsufficient);
    socket.on('engagement_features_updated', handleFeaturesUpdated);
    socket.on('engagement_prediction_finalized', handlePredictionFinalized);
    socket.on('engagement_model_status_changed', handleModelStatusChanged);
    socket.on('student_joined', handleStudentJoinedOrPresence);
    socket.on('presence_updated', handleStudentJoinedOrPresence);
    socket.on('student_presence_updated', handleStudentJoinedOrPresence);
    socket.on('policy_violation', handlePolicyViolationOrLog);
    socket.on('live_log_update', handlePolicyViolationOrLog);
    socket.on('student_telemetry', handlePolicyViolationOrLog);

    // Live session periodic poll interval (4s) for seamless sync
    const pollInterval = setInterval(() => {
      if (selectedSessionId) {
        loadSessionEngagement(selectedSessionId);
      }
    }, 4000);

    return () => {
      clearInterval(pollInterval);
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('engagement_prediction_updated', handlePredictionUpdate);
      socket.off('engagement_collection_started', handleCollectionStarted);
      socket.off('engagement_data_insufficient', handleDataInsufficient);
      socket.off('engagement_features_updated', handleFeaturesUpdated);
      socket.off('engagement_prediction_finalized', handlePredictionFinalized);
      socket.off('engagement_model_status_changed', handleModelStatusChanged);
      socket.off('student_joined', handleStudentJoinedOrPresence);
      socket.off('presence_updated', handleStudentJoinedOrPresence);
      socket.off('student_presence_updated', handleStudentJoinedOrPresence);
      socket.off('policy_violation', handlePolicyViolationOrLog);
      socket.off('live_log_update', handlePolicyViolationOrLog);
      socket.off('student_telemetry', handlePolicyViolationOrLog);
    };
  }, [selectedSessionId]);

  // ---------------------------------------------------------------------------
  // Student Detail Drawer: Open & Load History
  // ---------------------------------------------------------------------------
  const handleOpenDrawer = (student: StudentEngagementRowItem) => {
    setSelectedStudentForDrawer(student);
    setDrawerOpen(true);
    setLoadingHistory(true);
    setStudentHistory([]);

    if (selectedSessionId) {
      fetchProfessorStudentPredictionHistory(selectedSessionId, student.student_id)
        .then((hist) => {
          setStudentHistory(hist);
        })
        .catch((err) => {
          console.warn('Failed to load student prediction history:', err);
        })
        .finally(() => {
          setLoadingHistory(false);
        });
    } else {
      setLoadingHistory(false);
    }
  };

  const handleCloseDrawer = () => {
    setDrawerOpen(false);
    setSelectedStudentForDrawer(null);
  };

  // Close drawer on ESC
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && drawerOpen) {
        handleCloseDrawer();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // ---------------------------------------------------------------------------
  // Review Modal Handlers
  // ---------------------------------------------------------------------------
  const handleOpenReviewModal = (student: StudentEngagementRowItem, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSelectedStudentForReview(student);
    setReviewAction(student.professor_review_status === 'overridden' ? 'override' : 'confirm');
    setOverrideLabel(
      (student.professor_override_label as 'High' | 'Medium' | 'Low') ||
        (student.engagement_estimate as 'High' | 'Medium' | 'Low') ||
        'High'
    );
    setReviewNotes('');
    setReviewSuccessMessage(null);
    setReviewModalOpen(true);
  };

  const handleSubmitReview = async () => {
    if (!selectedStudentForReview?.prediction_id) return;
    setSubmittingReview(true);
    setReviewSuccessMessage(null);

    try {
      const res = await reviewEngagementPrediction(selectedStudentForReview.prediction_id, {
        action: reviewAction,
        override_label: reviewAction === 'override' ? overrideLabel : undefined,
        notes: reviewNotes.trim() || undefined,
      });

      // Immediately update local students list
      setStudents((prev) =>
        prev.map((s) =>
          s.prediction_id === selectedStudentForReview.prediction_id
            ? {
                ...s,
                professor_review_status: res.professor_review_status,
                professor_override_label: res.professor_override_label,
              }
            : s
        )
      );

      // Also update drawer if active
      if (
        selectedStudentForDrawer &&
        selectedStudentForDrawer.prediction_id === selectedStudentForReview.prediction_id
      ) {
        setSelectedStudentForDrawer((prev) =>
          prev
            ? {
                ...prev,
                professor_review_status: res.professor_review_status,
                professor_override_label: res.professor_override_label,
              }
            : null
        );
      }

      setReviewSuccessMessage('Review saved successfully!');
      setTimeout(() => {
        setReviewModalOpen(false);
        setReviewSuccessMessage(null);
      }, 1200);
    } catch (err: any) {
      alert(err.message || 'Failed to submit review');
    } finally {
      setSubmittingReview(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Formatter Helpers
  // ---------------------------------------------------------------------------
  const formatSeconds = (sec: number): string => {
    if (!sec || sec <= 0) return '0 min';
    const totalMinutes = Math.round(sec / 60);
    if (totalMinutes < 60) return `${totalMinutes} min`;
    const hours = Math.floor(totalMinutes / 60);
    const mins = totalMinutes % 60;
    return `${hours}h ${mins}m`;
  };

  const formatTimeOnly = (isoString?: string | null): string => {
    if (!isoString) return '--:--:--';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return '--:--:--';
    }
  };

  const getInitials = (name: string): string => {
    if (!name) return 'ST';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  const getLiveActivityStatusText = (st: StudentEngagementRowItem) => {
    if (
      st.collection_status === 'data_insufficient' ||
      (st.feature_completeness_percent !== undefined && st.feature_completeness_percent < 80)
    ) {
      return {
        text: 'Activity data unavailable',
        badgeClass: 'bg-amber-50 text-amber-800 border-amber-200',
        icon: 'alert' as const,
      };
    }
    if (
      !st.prediction_available &&
      (st.collection_status === 'collecting' || (st.valid_windows_received !== undefined && st.valid_windows_received === 0))
    ) {
      return {
        text: 'Collecting live activity data',
        badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
        icon: 'clock' as const,
      };
    }
    const acadTime = (st.allowed_academic_active_seconds ?? st.academic_activity_seconds) || 0;
    const idleTime = st.idle_seconds || 0;
    const hasApprovedApps = st.approved_apps_summary && Object.keys(st.approved_apps_summary).length > 0;
    const hasApprovedWebs = st.approved_websites_summary && Object.keys(st.approved_websites_summary).length > 0;

    if (idleTime > 60 && (hasApprovedApps || hasApprovedWebs) && idleTime >= acadTime) {
      return {
        text: 'Allowed app open, but student is idle',
        badgeClass: 'bg-amber-50 text-amber-800 border-amber-200',
        icon: 'idle' as const,
      };
    }
    if (acadTime > 0 && acadTime >= idleTime) {
      return {
        text: 'Actively using approved resource',
        badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
        icon: 'active' as const,
      };
    }
    return {
      text: st.prediction_reason || 'Collecting live activity data',
      badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
      icon: 'clock' as const,
    };
  };

  // ---------------------------------------------------------------------------
  // Current Session & Summaries
  // ---------------------------------------------------------------------------
  const currentSession = useMemo(() => {
    return sessions.find((s) => s.id === selectedSessionId);
  }, [sessions, selectedSessionId]);

  const isActiveSession = Boolean(currentSession?.is_active || currentSession?.status.toLowerCase() === 'active');

  // Stats for the 4 overview cards
  const stats = useMemo(() => {
    const total = students.length;
    const evaluated = students.filter((s) => s.prediction_available).length;
    const high = students.filter(
      (s) => (s.professor_override_label || s.engagement_estimate) === 'High'
    ).length;
    const med = students.filter(
      (s) => (s.professor_override_label || s.engagement_estimate) === 'Medium'
    ).length;
    const low = students.filter(
      (s) => (s.professor_override_label || s.engagement_estimate) === 'Low'
    ).length;
    const waiting = total - evaluated;

    const reviewed = students.filter(
      (s) => s.professor_review_status && s.professor_review_status !== 'pending'
    ).length;
    const reviewPct = total > 0 ? Math.round((reviewed / total) * 100) : 0;

    return { total, evaluated, high, med, low, waiting, reviewed, reviewPct };
  }, [students]);

  // Chart Data for Donut Chart (strictly High / Medium / Low per spec 8D)
  const chartData = useMemo(() => {
    return [
      { name: 'High Engagement', value: stats.high, color: '#10b981' }, // Emerald-500
      { name: 'Medium Engagement', value: stats.med, color: '#f59e0b' }, // Amber-500
      { name: 'Low Engagement', value: stats.low, color: '#f43f5e' }, // Rose-500
    ].filter((item) => item.value > 0);
  }, [stats]);

  // ---------------------------------------------------------------------------
  // Filtered, Sorted, & Paginated Students
  // ---------------------------------------------------------------------------
  const filteredAndSortedStudents = useMemo(() => {
    let result = [...students];

    // 1. Search filter
    if (tableSearch.trim()) {
      const q = tableSearch.toLowerCase().trim();
      result = result.filter(
        (s) =>
          s.student_name.toLowerCase().includes(q) ||
          s.student_id.toLowerCase().includes(q) ||
          (s.student_email && s.student_email.toLowerCase().includes(q))
      );
    }

    // 2. Engagement level filter
    if (tableEngagementFilter !== 'All') {
      if (tableEngagementFilter === 'Waiting') {
        result = result.filter((s) => !s.prediction_available);
      } else {
        result = result.filter(
          (s) =>
            s.prediction_available &&
            (s.professor_override_label || s.engagement_estimate) === tableEngagementFilter
        );
      }
    }

    // 3. Sorting
    result.sort((a, b) => {
      let valA = 0;
      let valB = 0;

      if (sortBy === 'confidence') {
        valA = a.confidence !== null && a.confidence !== undefined ? a.confidence : -1;
        valB = b.confidence !== null && b.confidence !== undefined ? b.confidence : -1;
      } else if (sortBy === 'idle_time') {
        valA = a.idle_seconds || 0;
        valB = b.idle_seconds || 0;
      } else if (sortBy === 'blocked_attempts') {
        valA =
          (a.blocked_website_attempt_count || 0) +
          (a.unauthorized_application_attempt_count || 0);
        valB =
          (b.blocked_website_attempt_count || 0) +
          (b.unauthorized_application_attempt_count || 0);
      } else if (sortBy === 'last_update') {
        valA = a.last_updated_time ? new Date(a.last_updated_time).getTime() : 0;
        valB = b.last_updated_time ? new Date(b.last_updated_time).getTime() : 0;
      }

      return sortOrder === 'asc' ? valA - valB : valB - valA;
    });

    return result;
  }, [students, tableSearch, tableEngagementFilter, sortBy, sortOrder]);

  // Pagination calculation
  const totalPages = Math.ceil(filteredAndSortedStudents.length / pageSize) || 1;
  const paginatedStudents = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredAndSortedStudents.slice(start, start + pageSize);
  }, [filteredAndSortedStudents, currentPage, pageSize]);

  const toggleSort = (field: 'confidence' | 'idle_time' | 'blocked_attempts' | 'last_update') => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  // ---------------------------------------------------------------------------
  // Time-Series Chart Data for Student Detail Drawer
  // ---------------------------------------------------------------------------
  const studentTimelineData = useMemo(() => {
    if (!studentHistory || studentHistory.length === 0) return [];
    return studentHistory.map((item, idx) => {
      const conf = item.confidence !== null && item.confidence !== undefined ? Math.round(item.confidence * 100) : 50;
      const score = item.prediction === 'High' ? 90 : item.prediction === 'Medium' ? 60 : 30;
      const timeStr = item.window_end_at
        ? new Date(item.window_end_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : `W${idx + 1}`;
      return {
        name: timeStr,
        engagementScore: score,
        confidence: conf,
        label: item.prediction,
      };
    });
  }, [studentHistory]);

  return (
    <div className="space-y-6 pb-16 bg-slate-50 min-h-screen text-slate-900">
      {/* -------------------------------------------------------------------- */}
      {/* 1. Page Header with Title & Model Status Badges */}
      {/* -------------------------------------------------------------------- */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-50 text-blue-600 border border-blue-200 shadow-xs">
              <BarChart3 size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                  Student Engagement
                </h1>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                  Professor Access Only
                </span>
              </div>
              <p className="text-sm text-slate-500 mt-0.5">
                Live and historical engagement insights for your sessions.
              </p>
            </div>
          </div>
        </div>

        {/* Right side model status badge */}
        <div className="flex flex-wrap items-center gap-2.5">
          {sessionDetail?.has_active_model ? (
            <button
              type="button"
              onClick={() => {
                setShowModelModal(true);
                loadModels();
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-xs hover:bg-emerald-100/80 transition-all cursor-pointer group"
              title={`Active Model: ${sessionDetail.model_version_tag || 'Approved'}. Click to manage or switch models.`}
            >
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>ML Model Active: <strong>{sessionDetail.model_version_tag || 'Approved'}</strong></span>
              <ChevronDown size={13} className="text-emerald-500 group-hover:translate-y-0.5 transition-transform" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setShowModelModal(true);
                loadModels();
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 shadow-xs hover:bg-amber-100/80 transition-all cursor-pointer group"
              title="Click to select or train an ML model."
            >
              <HelpCircle size={14} className="text-amber-500" />
              <span>No Approved Model — Click to Select</span>
              <ChevronDown size={13} className="text-amber-500 group-hover:translate-y-0.5 transition-transform" />
            </button>
          )}

          {isActiveSession && (
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold shadow-xs ${
                socketConnected
                  ? 'bg-sky-50 text-sky-700 border border-sky-200'
                  : 'bg-rose-50 text-rose-700 border border-rose-200'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  socketConnected ? 'bg-sky-500 animate-ping' : 'bg-rose-500'
                }`}
              />
              {socketConnected ? 'Live Data Updating' : 'Reconnecting Telemetry...'}
            </span>
          )}
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* 2. Filter Control Panel Card */}
      {/* -------------------------------------------------------------------- */}
      <Card noPadding className="border-slate-200 shadow-xs">
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-4 items-end">
            {/* Batch Selector (Col 4) */}
            <div className="lg:col-span-4">
              <label
                htmlFor="batch-selector"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                Batch
              </label>
              <div className="relative">
                <select
                  id="batch-selector"
                  value={selectedBatchId}
                  onChange={(e) => setSelectedBatchId(e.target.value)}
                  disabled={loadingBatches || batches.length === 0}
                  className="w-full appearance-none rounded-xl bg-white border border-slate-300 px-3.5 py-2.5 text-sm font-medium text-slate-900 shadow-xs focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:bg-slate-100 disabled:text-slate-400"
                >
                  {batches.length === 0 ? (
                    <option value="">No batches owned</option>
                  ) : (
                    batches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.student_count} students)
                      </option>
                    ))
                  )}
                </select>
                <ChevronDown
                  size={16}
                  className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
              </div>
            </div>

            {/* Session Selector (Col 4 - disabled until Batch selected) */}
            <div className="lg:col-span-4">
              <label
                htmlFor="session-selector"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                Session
              </label>
              <div className="relative">
                <select
                  id="session-selector"
                  value={selectedSessionId}
                  onChange={(e) => setSelectedSessionId(e.target.value)}
                  disabled={!selectedBatchId || loadingSessions || sessions.length === 0}
                  className="w-full appearance-none rounded-xl bg-white border border-slate-300 px-3.5 py-2.5 text-sm font-medium text-slate-900 shadow-xs focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:bg-slate-100 disabled:text-slate-400"
                >
                  {!selectedBatchId ? (
                    <option value="">Select a batch first</option>
                  ) : sessions.length === 0 ? (
                    <option value="">No sessions found</option>
                  ) : (
                    sessions.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.title} ({s.is_active ? 'Active' : s.status})
                      </option>
                    ))
                  )}
                </select>
                <ChevronDown
                  size={16}
                  className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
              </div>
            </div>

            {/* Status Filter (Col 4) */}
            <div className="lg:col-span-4">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Session Status Filter
              </label>
              <div className="grid grid-cols-3 gap-1 p-1 rounded-xl bg-slate-100 border border-slate-200">
                {(['Active', 'Completed', 'All'] as const).map((filter) => (
                  <button
                    key={filter}
                    onClick={() => handleStatusFilterChange(filter)}
                    className={`py-1.5 text-xs font-semibold rounded-lg transition-all ${
                      statusFilter === filter
                        ? 'bg-white text-blue-700 shadow-xs border border-slate-200'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {filter}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Date range & refresh bar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-slate-100">
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <span className="text-xs font-semibold text-slate-500 whitespace-nowrap">Date Filter:</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="rounded-lg bg-white border border-slate-300 px-2.5 py-1.5 text-xs text-slate-800 shadow-xs focus:border-blue-600 focus:outline-none"
                title="Start Date"
              />
              <span className="text-slate-400 text-xs">-</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="rounded-lg bg-white border border-slate-300 px-2.5 py-1.5 text-xs text-slate-800 shadow-xs focus:border-blue-600 focus:outline-none"
                title="End Date"
              />
              {(startDate || endDate) && (
                <button
                  onClick={() => {
                    setStartDate('');
                    setEndDate('');
                  }}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                  title="Clear Dates"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
              {currentSession && (
                <div className="text-xs text-slate-600 hidden md:block">
                  Selected:{' '}
                  <strong className="text-slate-900">{sessionDetail?.batch_name || '...'}</strong> •{' '}
                  <strong className="text-slate-900">{currentSession.title}</strong>
                </div>
              )}
              <Button
                variant="secondary"
                size="sm"
                icon={<RefreshCw size={14} className={loadingEngagement ? 'animate-spin' : ''} />}
                onClick={() => selectedSessionId && loadSessionEngagement(selectedSessionId)}
                disabled={!selectedSessionId || loadingEngagement}
              >
                Refresh
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* -------------------------------------------------------------------- */}
      {/* 3. Session Overview Cards */}
      {/* -------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Card 1: Students Evaluated */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">
              Students Evaluated
            </span>
            <div className="p-2 rounded-xl bg-blue-50 text-blue-600">
              <Users size={18} />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-slate-900">
              {stats.evaluated}
              <span className="text-sm font-medium text-slate-600 ml-1.5">/ {stats.total} joined</span>
            </div>
            <div className="mt-2 pt-2 border-t border-slate-100 text-xs text-slate-600">
              {isActiveSession ? (
                <div className="flex items-center gap-1.5 text-sky-700 font-medium truncate">
                  <span className="h-2 w-2 rounded-full bg-sky-500 animate-pulse" />
                  Live Updates Active
                </div>
              ) : (
                <div className="text-slate-600 truncate">
                  Final Model: {sessionDetail?.model_version_tag || 'Calibrated RF'}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Card 2: High Engagement */}
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-800 uppercase tracking-wider">
              High Engagement
            </span>
            <div className="p-2 rounded-xl bg-emerald-100 text-emerald-700">
              <Flame size={18} />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-emerald-900">
              {stats.high}
              <span className="text-sm font-medium text-emerald-700 ml-1.5">
                ({stats.total > 0 ? Math.round((stats.high / stats.total) * 100) : 0}%)
              </span>
            </div>
            <div className="mt-2 pt-2 border-t border-emerald-100 text-xs text-emerald-700 truncate">
              {isActiveSession ? (
                <span>Last update: {lastLiveEventAt ? formatTimeOnly(lastLiveEventAt.toISOString()) : 'Active'}</span>
              ) : (
                <span>Review completed: {stats.reviewPct}%</span>
              )}
            </div>
          </div>
        </div>

        {/* Card 3: Medium Engagement */}
        <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-amber-800 uppercase tracking-wider">
              Medium Engagement
            </span>
            <div className="p-2 rounded-xl bg-amber-100 text-amber-700">
              <BarChart3 size={18} />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-amber-900">
              {stats.med}
              <span className="text-sm font-medium text-amber-700 ml-1.5">
                ({stats.total > 0 ? Math.round((stats.med / stats.total) * 100) : 0}%)
              </span>
            </div>
            <div className="mt-2 pt-2 border-t border-amber-100 text-xs text-amber-700 truncate">
              Model: {sessionDetail?.model_version_tag || 'Approved RF'}
            </div>
          </div>
        </div>

        {/* Card 4: Low Engagement */}
        <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-800 uppercase tracking-wider">
              Low Engagement
            </span>
            <div className="p-2 rounded-xl bg-rose-100 text-rose-700">
              <Clock size={18} />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-rose-900">
              {stats.low}
              <span className="text-sm font-medium text-rose-700 ml-1.5">
                ({stats.total > 0 ? Math.round((stats.low / stats.total) * 100) : 0}%)
              </span>
            </div>
            <div className="mt-2 pt-2 border-t border-rose-100 text-xs text-rose-700 truncate">
              Advisory: Check-in recommended
            </div>
          </div>
        </div>

        {/* Card 5: Collecting Data */}
        <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Collecting Data
            </span>
            <div className="p-2 rounded-xl bg-slate-200 text-slate-700">
              <Clock size={18} />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-3xl font-extrabold text-slate-800">
              {stats.waiting}
              <span className="text-sm font-medium text-slate-600 ml-1.5">
                ({stats.total > 0 ? Math.round((stats.waiting / stats.total) * 100) : 0}%)
              </span>
            </div>
            <div className="mt-2 pt-2 border-t border-slate-200 text-xs text-slate-600 truncate">
              {isActiveSession ? (
                <span>Real-time live updates</span>
              ) : (
                <span>Unassessed / Insufficient</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* 4. Engagement Distribution Chart & Analytical Context */}
      {/* -------------------------------------------------------------------- */}
      {selectedSessionId && students.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Visual Donut Chart (Col 7) */}
          <div className="lg:col-span-7">
            <Card title="Engagement Distribution" className="h-full border-slate-200 shadow-xs">
              {chartData.length > 0 ? (
                <div className="flex flex-col sm:flex-row items-center justify-around gap-4 py-2">
                  <div className="w-full sm:w-64 h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={chartData}
                          innerRadius={55}
                          outerRadius={80}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          {chartData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <RechartsTooltip
                          formatter={(value: any, name: any) => {
                            const pct = stats.total > 0 ? Math.round((Number(value) / stats.total) * 100) : 0;
                            return [`${value} students (${pct}%)`, name];
                          }}
                          contentStyle={{
                            backgroundColor: '#ffffff',
                            borderRadius: '12px',
                            border: '1px solid #e2e8f0',
                            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                          }}
                        />
                        <Legend verticalAlign="bottom" height={36} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Summary Breakdown Pills */}
                  <div className="space-y-2.5 w-full sm:w-56 text-xs">
                    <div className="flex items-center justify-between p-2.5 rounded-xl bg-emerald-50 border border-emerald-100">
                      <span className="font-semibold text-emerald-800">High:</span>
                      <span className="font-bold text-emerald-900">
                        {stats.high} ({stats.total > 0 ? Math.round((stats.high / stats.total) * 100) : 0}%)
                      </span>
                    </div>
                    <div className="flex items-center justify-between p-2.5 rounded-xl bg-amber-50 border border-amber-100">
                      <span className="font-semibold text-amber-800">Medium:</span>
                      <span className="font-bold text-amber-900">
                        {stats.med} ({stats.total > 0 ? Math.round((stats.med / stats.total) * 100) : 0}%)
                      </span>
                    </div>
                    <div className="flex items-center justify-between p-2.5 rounded-xl bg-rose-50 border border-rose-100">
                      <span className="font-semibold text-rose-800">Low:</span>
                      <span className="font-bold text-rose-900">
                        {stats.low} ({stats.total > 0 ? Math.round((stats.low / stats.total) * 100) : 0}%)
                      </span>
                    </div>
                    {stats.waiting > 0 && (
                      <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                        <span className="font-semibold text-slate-700">Waiting for Data:</span>
                        <span className="font-bold text-slate-900">{stats.waiting}</span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="py-12 text-center text-slate-600 space-y-2">
                  <Clock size={36} className="mx-auto text-slate-600" />
                  <h4 className="text-sm font-semibold text-slate-800">Waiting for live student telemetry</h4>
                  <p className="text-xs max-w-sm mx-auto">
                    The machine learning inference engine calculates predictions continuously as approved applications and websites are actively used.
                  </p>
                </div>
              )}
            </Card>
          </div>

          {/* Analytical Governance Card (Col 5) */}
          <div className="lg:col-span-5">
            <Card title="Advisory Intelligence Governance" className="h-full border-slate-200 shadow-xs">
              <div className="space-y-3.5 text-xs text-slate-600">
                <div className="flex items-start gap-2.5 p-3 rounded-xl bg-blue-50/70 border border-blue-200 text-blue-900">
                  <Info size={18} className="text-blue-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold">Strict Non-Punitive Analytical Framework:</span> Engagement estimates
                    are purely advisory decision support metrics. System policy strictly prohibits automated blocking,
                    penalties, grading deductions, or punitive actions based on these metrics.
                  </div>
                </div>

                <div className="space-y-2 pt-1">
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500 font-medium">Session Mode</span>
                    <span className="font-semibold text-slate-800">
                      {isActiveSession ? 'Live Stream' : 'Archived Historical'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500 font-medium">Model Deployment Tag</span>
                    <span className="font-mono font-semibold text-blue-600">
                      {sessionDetail?.model_version_tag || 'Calibrated RF-v1.0'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500 font-medium">Human Ground Truth Reviews</span>
                    <span className="font-semibold text-slate-800">
                      {stats.reviewed} / {stats.total} ({stats.reviewPct}%)
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1.5">
                    <span className="text-slate-500 font-medium">Privacy Protection</span>
                    <span className="font-semibold text-emerald-600">No keystrokes, URLs, or files</span>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* 9. Polished Empty, Loading, and Error States */}
      {/* -------------------------------------------------------------------- */}
      {errorMessage && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 flex items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-2.5">
            <AlertTriangle size={20} className="text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="border-rose-300 text-rose-700 hover:bg-rose-100"
            onClick={() => selectedSessionId && loadSessionEngagement(selectedSessionId)}
          >
            Retry
          </Button>
        </div>
      )}

      {batches.length === 0 && !loadingBatches && (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-slate-500 shadow-xs">
          <Users size={44} className="mx-auto text-slate-400 mb-3" />
          <h3 className="text-lg font-bold text-slate-800">No Batches Available</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            You do not own any batches yet. Create a batch first in the Batches tab to begin tracking sessions.
          </p>
        </div>
      )}

      {batches.length > 0 && sessions.length === 0 && !loadingSessions && (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-slate-500 shadow-xs">
          <Clock size={44} className="mx-auto text-slate-400 mb-3" />
          <h3 className="text-lg font-bold text-slate-800">No Sessions Found</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            There are no {statusFilter !== 'All' ? statusFilter.toLowerCase() : ''} sessions recorded for this batch.
            Schedule a session in the Sessions tab to view student telemetry.
          </p>
        </div>
      )}

      {selectedSessionId && students.length === 0 && !loadingEngagement && (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center text-slate-500 shadow-xs">
          <Users size={44} className="mx-auto text-slate-400 mb-3" />
          <h3 className="text-lg font-bold text-slate-800">No Students Joined This Session</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            No enrolled students joined or sent telemetry data for this session. When students connect, their engagement
            telemetry will automatically appear here.
          </p>
        </div>
      )}

      {/* Loading Skeleton */}
      {loadingEngagement && (
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-xs space-y-4 animate-pulse">
          <div className="h-6 w-1/4 bg-slate-200 rounded-md" />
          <div className="h-4 w-1/2 bg-slate-100 rounded-md" />
          <div className="space-y-2 pt-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-slate-100 rounded-xl" />
            ))}
          </div>
        </div>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* 5. Student Engagement Table */}
      {/* -------------------------------------------------------------------- */}
      {selectedSessionId && students.length > 0 && !loadingEngagement && (
        <Card noPadding className="border-slate-200 shadow-xs overflow-hidden">
          {/* Table Toolbar: Search, Engagement Filter, and Sort */}
          <div className="p-4 border-b border-slate-200 bg-slate-50/70 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex flex-col sm:flex-row items-center gap-3 w-full md:w-auto">
              {/* Search */}
              <div className="relative w-full sm:w-64">
                <Search
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="text"
                  placeholder="Search student or ID..."
                  value={tableSearch}
                  onChange={(e) => {
                    setTableSearch(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-full rounded-xl bg-white border border-slate-300 pl-9 pr-4 py-2 text-xs text-slate-900 shadow-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
                />
                {tableSearch && (
                  <button
                    onClick={() => setTableSearch('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              {/* Engagement Level Filter */}
              <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider mr-1 hidden sm:inline">
                  Filter:
                </span>
                {(['All', 'High', 'Medium', 'Low', 'Waiting'] as const).map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => {
                      setTableEngagementFilter(lvl);
                      setCurrentPage(1);
                    }}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all whitespace-nowrap ${
                      tableEngagementFilter === lvl
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                    }`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>
            </div>

            {/* Sort & Row count */}
            <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-end text-xs text-slate-600">
              <span className="font-medium">
                Showing {filteredAndSortedStudents.length} of {students.length} students
              </span>

              <div className="flex items-center gap-1.5">
                <span className="text-slate-600 font-semibold">Sort by:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as any)}
                  className="rounded-lg bg-white border border-slate-300 px-2.5 py-1 text-xs text-slate-800 shadow-xs focus:border-blue-600 focus:outline-none"
                >
                  <option value="confidence">Confidence</option>
                  <option value="idle_time">Idle Time</option>
                  <option value="blocked_attempts">Blocked Attempts</option>
                  <option value="last_update">Last Update</option>
                </select>
                <button
                  onClick={() => setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
                  className="p-1 rounded-lg hover:bg-slate-200 text-slate-600"
                  title={`Sort ${sortOrder === 'asc' ? 'Ascending' : 'Descending'}`}
                >
                  <ArrowUpDown size={14} />
                </button>
              </div>
            </div>
          </div>

          {/* Sticky Header Table */}
          <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table className="w-full text-left text-sm text-slate-700">
              <thead className="sticky top-0 z-10 bg-slate-100 text-[11px] font-bold text-slate-600 uppercase tracking-wider border-b border-slate-200 shadow-xs">
                <tr>
                  <th className="px-5 py-3.5">Student</th>
                  <th className="px-4 py-3.5">Presence</th>
                  <th className="px-4 py-3.5">Policy</th>
                  <th className="px-4 py-3.5">Academic</th>
                  <th
                    className="px-4 py-3.5 cursor-pointer hover:text-blue-600"
                    onClick={() => toggleSort('idle_time')}
                    title="Click to sort by idle time"
                  >
                    <div className="flex items-center gap-1">
                      Idle
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th
                    className="px-4 py-3.5 cursor-pointer hover:text-blue-600"
                    onClick={() => toggleSort('blocked_attempts')}
                    title="Click to sort by blocked attempts"
                  >
                    <div className="flex items-center gap-1">
                      Blocked
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="px-5 py-3.5">Engagement Estimate</th>
                  <th
                    className="px-4 py-3.5 cursor-pointer hover:text-blue-600"
                    onClick={() => toggleSort('confidence')}
                    title="Click to sort by model confidence"
                  >
                    <div className="flex items-center gap-1">
                      Confidence
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="px-4 py-3.5">Prediction Type</th>
                  <th
                    className="px-4 py-3.5 cursor-pointer hover:text-blue-600"
                    onClick={() => toggleSort('last_update')}
                    title="Click to sort by update time"
                  >
                    <div className="flex items-center gap-1">
                      Update Time
                      <ArrowUpDown size={12} />
                    </div>
                  </th>
                  <th className="px-4 py-3.5 text-right">Review</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-normal bg-white">
                {paginatedStudents.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-6 py-12 text-center text-slate-500">
                      No students match your filter criteria.
                    </td>
                  </tr>
                ) : (
                  paginatedStudents.map((st) => {
                    const isRecentlyUpdated = recentlyUpdatedStudentId === st.student_id;
                    const displayEstimate = st.professor_override_label || st.engagement_estimate;

                    return (
                      <tr
                        key={st.student_id}
                        onClick={() => handleOpenDrawer(st)}
                        className={`cursor-pointer transition-colors duration-200 ${
                          isRecentlyUpdated
                            ? 'bg-blue-50/80 animate-pulse'
                            : 'hover:bg-slate-50'
                        }`}
                        title="Click to inspect detailed engagement telemetry"
                      >
                        {/* Student Initials, Name, ID */}
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-3">
                            <div className="h-9 w-9 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-xs shrink-0 border border-blue-200">
                              {getInitials(st.student_name)}
                            </div>
                            <div>
                              <div className="font-semibold text-slate-900 leading-tight">
                                {st.student_name}
                              </div>
                              <div className="text-[11px] text-slate-600 font-mono mt-0.5 truncate max-w-[140px]">
                                {st.student_email || st.student_id}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Presence: Online, Offline, Left */}
                        <td className="px-4 py-3.5">
                          {st.session_status === 'Joined' ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Online
                            </span>
                          ) : st.session_status === 'Left' ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                              Left
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                              Offline
                            </span>
                          )}
                        </td>

                        {/* Policy Status: Active, Restored, Failed */}
                        <td className="px-4 py-3.5">
                          {st.policy_status === 'Active' ? (
                            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              Active
                            </span>
                          ) : st.policy_status === 'Restored' ? (
                            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                              Restored
                            </span>
                          ) : (
                            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                              Failed
                            </span>
                          )}
                        </td>

                        {/* Academic Time */}
                        <td className="px-4 py-3.5">
                          <div className="font-mono text-xs font-bold text-emerald-800">
                            {formatSeconds(st.allowed_academic_active_seconds ?? st.academic_activity_seconds)}
                          </div>
                          <div className="flex flex-col gap-0.5 mt-0.5 text-[10px] text-slate-500">
                            {(st.allowed_academic_application_active_seconds ?? 0) > 0 && (
                              <span className="flex items-center gap-1 text-slate-700" title="Approved Applications Foreground Active Time">
                                <Laptop size={10} className="text-blue-600 shrink-0" />
                                {formatSeconds(st.allowed_academic_application_active_seconds || 0)}
                              </span>
                            )}
                            {(st.allowed_academic_website_active_seconds ?? 0) > 0 && (
                              <span className="flex items-center gap-1 text-slate-700" title="Approved Websites Foreground Active Time">
                                <Globe size={10} className="text-emerald-600 shrink-0" />
                                {formatSeconds(st.allowed_academic_website_active_seconds || 0)}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Idle Time */}
                        <td className="px-4 py-3.5 font-mono text-xs text-slate-600">
                          {formatSeconds(st.idle_seconds)}
                        </td>

                        {/* Blocked Attempts */}
                        <td className="px-4 py-3.5 font-mono text-xs">
                          {st.blocked_website_attempt_count + st.unauthorized_application_attempt_count > 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 font-bold border border-amber-200">
                              {st.blocked_website_attempt_count + st.unauthorized_application_attempt_count}
                            </span>
                          ) : (
                            <span className="text-slate-600">0</span>
                          )}
                        </td>

                        {/* Engagement Estimate */}
                        <td className="px-5 py-3.5">
                          {st.collection_status === 'data_insufficient' ? (
                            <span
                              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200"
                              title={st.prediction_reason || "More valid activity data is required for an estimate."}
                            >
                              <AlertTriangle size={12} className="text-amber-600" />
                              Data Insufficient
                            </span>
                          ) : st.prediction_available && displayEstimate ? (
                            <div className="flex flex-col gap-0.5">
                              <span
                                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-bold w-fit shadow-xs ${
                                  displayEstimate === 'High'
                                    ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                                    : displayEstimate === 'Medium'
                                    ? 'bg-amber-50 text-amber-800 border border-amber-200'
                                    : 'bg-rose-50 text-rose-800 border border-rose-200'
                                }`}
                              >
                                {displayEstimate === 'High' ? 'High Engagement' : displayEstimate === 'Medium' ? 'Medium Engagement' : displayEstimate === 'Low' ? 'Low Engagement' : displayEstimate}
                              </span>
                              {st.professor_override_label && (
                                <span className="text-[10px] text-slate-600">
                                  Model: {st.engagement_estimate}
                                </span>
                              )}
                              {(() => {
                                const statusInfo = getLiveActivityStatusText(st);
                                return (
                                  <span
                                    className="text-[10.5px] font-medium text-slate-500 mt-0.5 block truncate max-w-[170px]"
                                    title={statusInfo.text}
                                  >
                                    {statusInfo.text}
                                  </span>
                                );
                              })()}
                            </div>
                          ) : (
                            <div
                              className="flex items-center gap-1.5 text-xs text-slate-600 italic"
                              title={st.prediction_reason || "Collecting live activity data"}
                            >
                              <Clock size={13} className="text-slate-500 animate-spin" />
                              <span>{st.prediction_reason || "Collecting live activity data"}</span>
                            </div>
                          )}
                        </td>

                        {/* Confidence Progress Bar */}
                        <td className="px-4 py-3.5 font-mono text-xs">
                          {st.prediction_available && st.confidence !== null && st.confidence !== undefined ? (
                            <div title="Model dynamic prediction confidence score">
                              <div className="flex items-center justify-between text-[11px] font-bold text-slate-700 mb-1">
                                <span>{Math.round(st.confidence * 100)}%</span>
                              </div>
                              <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    (st.confidence || 0) > 0.7
                                      ? 'bg-emerald-500'
                                      : (st.confidence || 0) > 0.4
                                      ? 'bg-amber-500'
                                      : 'bg-rose-500'
                                  }`}
                                  style={{ width: `${Math.round((st.confidence || 0) * 100)}%` }}
                                />
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-400 font-mono text-xs">—</span>
                          )}
                        </td>

                        {/* Prediction Type */}
                        <td className="px-4 py-3.5">
                          <span
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                              st.prediction_type === 'Final'
                                ? 'bg-purple-50 text-purple-700 border border-purple-200'
                                : st.prediction_type === 'Collecting' || (!st.prediction_available && st.collection_status === 'collecting')
                                ? 'bg-slate-100 text-slate-700 border border-slate-200'
                                : 'bg-blue-50 text-blue-700 border border-blue-200'
                            }`}
                          >
                            {st.prediction_type || (st.prediction_available ? 'Live Preliminary' : 'Collecting')}
                          </span>
                        </td>

                        {/* Update Time */}
                        <td className="px-4 py-3.5 text-xs font-mono text-slate-600 whitespace-nowrap">
                          {formatTimeOnly(st.last_updated_time)}
                        </td>

                        {/* Review Action */}
                        <td className="px-4 py-3.5 text-right">
                          {st.professor_review_status === 'overridden' ? (
                            <span
                              onClick={(e) => handleOpenReviewModal(st, e)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100"
                              title="Professor override applied"
                            >
                              <CheckCircle2 size={12} />
                              Override: {st.professor_override_label}
                            </span>
                          ) : st.professor_review_status === 'confirmed' ? (
                            <span
                              onClick={(e) => handleOpenReviewModal(st, e)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200 hover:bg-emerald-100"
                              title="Estimate confirmed by professor"
                            >
                              <CheckCircle2 size={12} />
                              Reviewed
                            </span>
                          ) : (
                            <button
                              onClick={(e) => handleOpenReviewModal(st, e)}
                              disabled={!st.prediction_available}
                              className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-blue-50 text-blue-700 border border-slate-300 hover:border-blue-300 shadow-xs transition-all disabled:opacity-30 disabled:pointer-events-none"
                            >
                              Review
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="p-4 border-t border-slate-200 bg-white flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <span>Rows per page:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="rounded-lg bg-white border border-slate-300 px-2 py-1 text-xs text-slate-800"
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
              </div>

              <div className="flex items-center gap-2">
                <span>
                  Page {currentPage} of {totalPages}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="p-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40"
                    title="Previous Page"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="p-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40"
                    title="Next Page"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* 6. Student Detail Drawer (Sliding in from Right) */}
      {/* -------------------------------------------------------------------- */}
      {drawerOpen && selectedStudentForDrawer && (
        <div className="fixed inset-0 z-50 overflow-hidden animate-fade-in">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-slate-900/50 backdrop-blur-xs transition-opacity"
            onClick={handleCloseDrawer}
          />

          {/* Sliding Panel */}
          <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-screen max-w-md bg-white shadow-2xl flex flex-col justify-between border-l border-slate-200">
              {/* Drawer Header */}
              <div className="p-6 border-b border-slate-200 bg-slate-50/70">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm border border-blue-200">
                      {getInitials(selectedStudentForDrawer.student_name)}
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-slate-900 leading-tight">
                        {selectedStudentForDrawer.student_name}
                      </h3>
                      <p className="text-xs text-slate-500 font-mono mt-0.5">
                        {selectedStudentForDrawer.student_email || selectedStudentForDrawer.student_id}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={handleCloseDrawer}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors"
                  >
                    <X size={20} />
                  </button>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                  <span className="px-2.5 py-1 rounded-md bg-white border border-slate-200 font-medium text-slate-700">
                    Batch: {sessionDetail?.batch_name}
                  </span>
                  <span className="px-2.5 py-1 rounded-md bg-white border border-slate-200 font-medium text-slate-700">
                    Session: {sessionDetail?.session_title}
                  </span>
                </div>
              </div>

              {/* Drawer Body (Scrollable) */}
              <div className="p-6 overflow-y-auto space-y-6 flex-1 text-slate-800">
                {/* Live Activity State Banner */}
                {(() => {
                  const statusInfo = getLiveActivityStatusText(selectedStudentForDrawer);
                  return (
                    <div className={`p-3.5 rounded-xl border flex items-center justify-between text-xs font-semibold ${statusInfo.badgeClass}`}>
                      <div className="flex items-center gap-2">
                        {statusInfo.icon === 'active' && <Sparkles size={15} className="text-emerald-600 shrink-0" />}
                        {statusInfo.icon === 'idle' && <Clock size={15} className="text-amber-600 shrink-0" />}
                        {statusInfo.icon === 'alert' && <AlertTriangle size={15} className="text-amber-600 shrink-0" />}
                        {statusInfo.icon === 'clock' && <Clock size={15} className="text-slate-500 animate-spin shrink-0" />}
                        <span>{statusInfo.text}</span>
                      </div>
                      <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-white/60">
                        {selectedStudentForDrawer.collection_status || 'Live'}
                      </span>
                    </div>
                  );
                })()}

                {/* Current Estimate & Confidence Meter */}
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                      Current Engagement
                    </span>
                    <span
                      className={`px-3 py-1 rounded-xl text-xs font-bold ${
                        (selectedStudentForDrawer.professor_override_label ||
                          selectedStudentForDrawer.engagement_estimate) === 'High'
                          ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                          : (selectedStudentForDrawer.professor_override_label ||
                              selectedStudentForDrawer.engagement_estimate) === 'Medium'
                          ? 'bg-amber-100 text-amber-800 border border-amber-200'
                          : 'bg-rose-100 text-rose-800 border border-rose-200'
                      }`}
                    >
                      {selectedStudentForDrawer.professor_override_label ||
                        selectedStudentForDrawer.engagement_estimate ||
                        'Waiting for data'}
                    </span>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-600">Model Confidence:</span>
                      <span className="font-mono font-bold text-slate-900">
                        {selectedStudentForDrawer.confidence !== null && selectedStudentForDrawer.confidence !== undefined
                          ? `${Math.round(selectedStudentForDrawer.confidence * 100)}%`
                          : 'N/A'}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          (selectedStudentForDrawer.confidence || 0) > 0.7
                            ? 'bg-emerald-500'
                            : (selectedStudentForDrawer.confidence || 0) > 0.4
                            ? 'bg-amber-500'
                            : 'bg-rose-500'
                        }`}
                        style={{
                          width: `${Math.round((selectedStudentForDrawer.confidence || 0) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-200 text-slate-500">
                    <span>Model: {selectedStudentForDrawer.model_version || 'Production'}</span>
                    <span>Status: {selectedStudentForDrawer.prediction_type}</span>
                  </div>
                </div>

                {/* Safe Feature Summary Grid */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Approved Academic Activity
                    </h4>
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800">
                      Completeness: {selectedStudentForDrawer.feature_completeness_percent ?? 100}%
                    </span>
                  </div>

                  {/* Primary Academic Metrics */}
                  <div className="grid grid-cols-2 gap-3 text-xs mb-3">
                    <div className="p-3 rounded-xl border border-blue-200 bg-blue-50/50">
                      <div className="flex items-center gap-1.5 text-blue-700 font-semibold mb-1">
                        <Laptop size={14} />
                        <span>Approved Apps</span>
                      </div>
                      <span className="font-bold text-blue-950 text-base block font-mono">
                        {formatSeconds(selectedStudentForDrawer.allowed_academic_application_active_seconds || 0)}
                      </span>
                      <span className="text-[10px] text-blue-700/80 mt-0.5 block">Foreground active only</span>
                    </div>

                    <div className="p-3 rounded-xl border border-emerald-200 bg-emerald-50/50">
                      <div className="flex items-center gap-1.5 text-emerald-700 font-semibold mb-1">
                        <Globe size={14} />
                        <span>Approved Websites</span>
                      </div>
                      <span className="font-bold text-emerald-950 text-base block font-mono">
                        {formatSeconds(selectedStudentForDrawer.allowed_academic_website_active_seconds || 0)}
                      </span>
                      <span className="text-[10px] text-emerald-700/80 mt-0.5 block">Foreground active only</span>
                    </div>
                  </div>

                  {/* Approved Applications Breakdown (if any) */}
                  {selectedStudentForDrawer.approved_apps_summary && Object.keys(selectedStudentForDrawer.approved_apps_summary).length > 0 && (
                    <div className="p-3 mb-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-[11px] font-bold text-slate-700 block mb-1.5">Approved Applications Breakdown:</span>
                      <div className="space-y-1">
                        {Object.entries(selectedStudentForDrawer.approved_apps_summary).map(([appName, sec]) => (
                          <div key={appName} className="flex items-center justify-between text-xs py-0.5 border-b border-slate-50 last:border-0">
                            <span className="text-slate-600 truncate max-w-[200px]">{appName}</span>
                            <span className="font-mono font-bold text-slate-800">{formatSeconds(Number(sec))}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Approved Websites Breakdown (if any) */}
                  {selectedStudentForDrawer.approved_websites_summary && Object.keys(selectedStudentForDrawer.approved_websites_summary).length > 0 && (
                    <div className="p-3 mb-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-[11px] font-bold text-slate-700 block mb-1.5">Approved Websites Breakdown:</span>
                      <div className="space-y-1">
                        {Object.entries(selectedStudentForDrawer.approved_websites_summary).map(([domain, sec]) => (
                          <div key={domain} className="flex items-center justify-between text-xs py-0.5 border-b border-slate-50 last:border-0">
                            <span className="text-slate-600 truncate max-w-[200px]">{domain}</span>
                            <span className="font-mono font-bold text-slate-800">{formatSeconds(Number(sec))}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Secondary Context Metrics */}
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-slate-500 block">Total Academic Time</span>
                      <span className="font-bold text-slate-900 text-sm mt-0.5 block font-mono">
                        {formatSeconds(
                          selectedStudentForDrawer.allowed_academic_active_seconds ??
                          selectedStudentForDrawer.academic_activity_seconds
                        )}
                      </span>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-slate-500 block">Idle Time</span>
                      <span className="font-bold text-slate-900 text-sm mt-0.5 block font-mono">
                        {formatSeconds(selectedStudentForDrawer.idle_seconds)}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-0.5 block">Idle & background apps</span>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-slate-500 block">Non-Academic Time</span>
                      <span className="font-bold text-slate-900 text-sm mt-0.5 block font-mono">
                        {formatSeconds(selectedStudentForDrawer.non_academic_activity_seconds)}
                      </span>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-slate-500 block">Unverified Domain Time</span>
                      <span className="font-bold text-slate-900 text-sm mt-0.5 block font-mono">
                        {formatSeconds(selectedStudentForDrawer.unknown_or_unavailable_seconds || 0)}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-0.5 block">Not a violation</span>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-slate-500 block">App Switches</span>
                      <span className="font-bold text-slate-900 text-sm mt-0.5 block font-mono">
                        {selectedStudentForDrawer.application_switch_count}
                      </span>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-white">
                      <span className="text-slate-500 block">Blocked Attempts</span>
                      <span className="font-bold text-slate-900 text-sm mt-0.5 block font-mono">
                        {selectedStudentForDrawer.blocked_website_attempt_count +
                          selectedStudentForDrawer.unauthorized_application_attempt_count}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Privacy Guarantee Notice */}
                <div className="p-3 rounded-xl bg-slate-100 border border-slate-200 text-[11px] text-slate-600 flex items-start gap-2">
                  <Laptop size={16} className="text-slate-500 shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-slate-800">Privacy Safeguard:</strong> Telemetry is strictly aggregated.
                    Keystrokes, screen recordings, files, and personal URLs are never monitored or stored.
                  </div>
                </div>

                {/* Mini Time-Series Timeline Chart */}
                <div>
                  <h4 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
                    Engagement Timeline (Live Windows)
                  </h4>
                  {studentTimelineData.length > 0 ? (
                    <div className="h-44 w-full bg-white border border-slate-200 rounded-xl p-2">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={studentTimelineData}>
                          <defs>
                            <linearGradient id="colorEng" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                          <YAxis domain={[0, 100]} hide />
                          <RechartsTooltip
                            formatter={(value: any) => [`${value}%`, 'Score']}
                            contentStyle={{
                              fontSize: '11px',
                              borderRadius: '8px',
                              border: '1px solid #e2e8f0',
                            }}
                          />
                          <Area
                            type="monotone"
                            dataKey="engagementScore"
                            stroke="#2563eb"
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorEng)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-center text-xs text-slate-500">
                      {loadingHistory ? 'Loading historical timeline...' : 'No historical window records available yet.'}
                    </div>
                  )}
                </div>

                {/* Historical Window Log */}
                {studentHistory.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">
                      Window Prediction History
                    </h4>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {studentHistory.map((h, i) => (
                        <div
                          key={h.id || i}
                          className="flex items-center justify-between p-2.5 rounded-lg border border-slate-200 bg-white text-xs"
                        >
                          <div>
                            <span className="font-semibold text-slate-800">
                              {h.window_end_at ? formatTimeOnly(h.window_end_at) : `Window ${i + 1}`}
                            </span>
                            <span className="text-[10px] text-slate-400 block font-mono">
                              {h.prediction_type}
                            </span>
                          </div>
                          <div className="text-right">
                            <span
                              className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                                h.prediction === 'High'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : h.prediction === 'Medium'
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-rose-100 text-rose-800'
                              }`}
                            >
                              {h.prediction}
                            </span>
                            <span className="text-[10px] text-slate-500 block font-mono">
                              {h.confidence !== null ? `${Math.round((h.confidence || 0) * 100)}%` : ''}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Drawer Footer Actions */}
              <div className="p-5 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
                <Button variant="ghost" size="sm" onClick={handleCloseDrawer}>
                  Close
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleOpenReviewModal(selectedStudentForDrawer)}
                  disabled={!selectedStudentForDrawer.prediction_available}
                >
                  Professor Review
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* 7. Professor Review Modal */}
      {/* -------------------------------------------------------------------- */}
      <Modal
        isOpen={reviewModalOpen}
        onClose={() => setReviewModalOpen(false)}
        title="Professor Engagement Review"
        footer={
          <div className="flex items-center justify-end gap-3 w-full">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setReviewModalOpen(false)}
              disabled={submittingReview}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSubmitReview}
              disabled={submittingReview}
              icon={submittingReview ? <RefreshCw size={14} className="animate-spin" /> : undefined}
            >
              Submit Review
            </Button>
          </div>
        }
      >
        {selectedStudentForReview && (
          <div className="space-y-4 text-xs text-slate-700">
            {reviewSuccessMessage && (
              <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-center gap-2 font-medium">
                <CheckCircle2 size={16} className="text-emerald-600" />
                <span>{reviewSuccessMessage}</span>
              </div>
            )}

            {/* Target Student Header */}
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between">
              <div>
                <span className="font-bold text-slate-900 block text-sm">
                  {selectedStudentForReview.student_name}
                </span>
                <span className="text-slate-500 font-mono text-[11px]">
                  ID: {selectedStudentForReview.student_id}
                </span>
              </div>
              <div className="text-right">
                <span className="text-slate-500 block text-[11px]">Model Estimate</span>
                <span className="font-bold text-blue-700 font-mono text-sm">
                  {selectedStudentForReview.engagement_estimate || 'Pending'}
                </span>
              </div>
            </div>

            {/* Safe Feature Summary Snapshot */}
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Academic</span>
                <span className="font-bold text-slate-800">
                  {formatSeconds(selectedStudentForReview.academic_activity_seconds)}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Idle</span>
                <span className="font-bold text-slate-800">
                  {formatSeconds(selectedStudentForReview.idle_seconds)}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Blocked/Violations</span>
                <span className="font-bold text-slate-800">
                  {selectedStudentForReview.blocked_website_attempt_count +
                    selectedStudentForReview.unauthorized_application_attempt_count}
                </span>
              </div>
            </div>

            {/* Review Options: Confirm or Override */}
            <div className="space-y-2 pt-2">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                Review Decision
              </label>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setReviewAction('confirm')}
                  className={`p-3 rounded-xl text-left border transition-all ${
                    reviewAction === 'confirm'
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-900 font-semibold ring-1 ring-emerald-500'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span>Confirm Estimate</span>
                    {reviewAction === 'confirm' && <Check size={16} className="text-emerald-600" />}
                  </div>
                  <div className="text-[11px] font-normal text-slate-500 mt-0.5">
                    Model estimate is accurate.
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setReviewAction('override')}
                  className={`p-3 rounded-xl text-left border transition-all ${
                    reviewAction === 'override'
                      ? 'border-blue-600 bg-blue-50 text-blue-900 font-semibold ring-1 ring-blue-600'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span>Override Estimate</span>
                    {reviewAction === 'override' && <Check size={16} className="text-blue-600" />}
                  </div>
                  <div className="text-[11px] font-normal text-slate-500 mt-0.5">
                    Correct based on classroom observation.
                  </div>
                </button>
              </div>

              {/* Override Choice: High, Medium, Low */}
              {reviewAction === 'override' && (
                <div className="pt-2 space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-600">Select Corrected Label:</label>
                  <div className="grid grid-cols-3 gap-2">
                    {(['High', 'Medium', 'Low'] as const).map((label) => (
                      <button
                        key={label}
                        type="button"
                        onClick={() => setOverrideLabel(label)}
                        className={`py-2 text-xs font-bold rounded-xl border transition-all ${
                          overrideLabel === label
                            ? label === 'High'
                              ? 'bg-emerald-100 text-emerald-800 border-emerald-500 ring-1 ring-emerald-500'
                              : label === 'Medium'
                              ? 'bg-amber-100 text-amber-800 border-amber-500 ring-1 ring-amber-500'
                              : 'bg-rose-100 text-rose-800 border-rose-500 ring-1 ring-rose-500'
                            : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Reason / Notes field with character limit */}
              <div className="pt-2">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">
                    Reason / Observation Note (Optional):
                  </label>
                  <span
                    className={`text-[10px] ${
                      reviewNotes.length > 230 ? 'text-rose-600 font-bold' : 'text-slate-400'
                    }`}
                  >
                    {reviewNotes.length} / 250
                  </span>
                </div>
                <textarea
                  value={reviewNotes}
                  maxLength={250}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  placeholder="e.g. Student actively answered oral questions during the lecture..."
                  rows={2}
                  className="w-full rounded-xl bg-white border border-slate-300 p-2.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
                />
              </div>

              {/* Immutability Notice */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-500">
                <strong className="text-slate-700">Audit Guarantee:</strong> The original ML model prediction is
                permanently preserved. Your review is stored separately as verified ground truth for model retraining.
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* --------------------------------------------------------------------- */}
      {/* 9. ML Model Selection & Management Modal                              */}
      {/* --------------------------------------------------------------------- */}
      <Modal
        isOpen={showModelModal}
        onClose={() => {
          setShowModelModal(false);
          setModelFeedbackMsg(null);
        }}
        title="Student Engagement ML Model Management"
      >
        <div className="space-y-4 max-w-xl">
          {modelFeedbackMsg && (
            <div
              className={`p-3 rounded-xl text-xs font-medium flex items-center justify-between ${
                modelFeedbackMsg.type === 'success'
                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                  : 'bg-rose-50 text-rose-800 border border-rose-200'
              }`}
            >
              <span>{modelFeedbackMsg.text}</span>
              <button
                onClick={() => setModelFeedbackMsg(null)}
                className="text-slate-400 hover:text-slate-600 font-bold ml-2"
              >
                ×
              </button>
            </div>
          )}

          {/* Active Model Overview Card */}
          <div className="p-4 rounded-xl bg-gradient-to-br from-slate-50 to-blue-50/40 border border-blue-100 dark:border-slate-800">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Cpu className="text-blue-600" size={18} />
                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Active Production Model
                </span>
              </div>
              {sessionDetail?.has_active_model ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 animate-pulse" />
                  Live & Serving
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800">
                  Heuristic Fallback
                </span>
              )}
            </div>
            <p className="text-xs text-slate-600">
              Current Model Version:{' '}
              <strong className="text-slate-900 font-mono">
                {sessionDetail?.model_version_tag || 'None Approved'}
              </strong>
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              Provides privacy-preserving real-time engagement classification (High, Medium, Low) for student sessions without screen or keystroke tracking.
            </p>
          </div>

          {/* Available Models List */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                Available ML Models ({mlModels.length})
              </h4>
              <button
                type="button"
                onClick={handleTrainBestModel}
                disabled={trainingNewModel}
                className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
              >
                <Sparkles size={13} />
                {trainingNewModel ? 'Training Optimal Model...' : 'Train & Activate Best Model'}
              </button>
            </div>

            {loadingModels ? (
              <div className="py-8 text-center text-xs text-slate-400">Loading model registry...</div>
            ) : mlModels.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400 border border-dashed rounded-xl p-4">
                No models currently registered in the database.
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {mlModels.map((m) => {
                  const isCurrentActive = m.status === 'approved';
                  const accuracy = m.metrics_json?.accuracy != null ? Math.round(m.metrics_json.accuracy * 100) : null;
                  const f1 = m.metrics_json?.f1_macro != null ? Math.round(m.metrics_json.f1_macro * 100) : null;

                  return (
                    <div
                      key={m.id}
                      className={`p-3 rounded-xl border transition-all flex items-center justify-between gap-3 ${
                        isCurrentActive
                          ? 'bg-emerald-50/60 border-emerald-300 ring-1 ring-emerald-300'
                          : 'bg-white border-slate-200 hover:border-slate-300'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-slate-900 truncate">
                            {m.version_tag}
                          </span>
                          {isCurrentActive && (
                            <span className="text-[10px] font-bold px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded-full">
                              Active
                            </span>
                          )}
                          {m.status === 'draft' && (
                            <span className="text-[10px] font-bold px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">
                              Draft
                            </span>
                          )}
                          {m.status === 'retired' && (
                            <span className="text-[10px] font-bold px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full">
                              Retired
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-1">
                          <span>{m.algorithm}</span>
                          {accuracy !== null && (
                            <span>Accuracy: <strong className="text-slate-700">{accuracy}%</strong></span>
                          )}
                          {f1 !== null && (
                            <span>Macro F1: <strong className="text-slate-700">{f1}%</strong></span>
                          )}
                        </div>
                      </div>

                      <div>
                        {isCurrentActive ? (
                          <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700 px-3 py-1 bg-emerald-100 rounded-lg">
                            <Check size={14} /> Active
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleApproveModel(m.id)}
                            disabled={modelActionId === m.id}
                            className="text-xs font-semibold px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors cursor-pointer disabled:opacity-50"
                          >
                            {modelActionId === m.id ? 'Activating...' : 'Select & Activate'}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
};
