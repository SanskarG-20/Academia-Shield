import React, { useEffect, useState, useRef } from 'react';
import { X, Sparkles, AlertCircle, Loader2, Users, ShieldAlert, Clock, AlertTriangle } from 'lucide-react';
import { Session, SessionSummaryResponse } from '../types';
import { getSessionSummary } from '../lib/api';
import { Button } from './ui/Button';

interface SessionSummaryModalProps {
  isOpen: boolean;
  onClose: () => void;
  session: Session;
}

export const SessionSummaryModal: React.FC<SessionSummaryModalProps> = ({
  isOpen,
  onClose,
  session,
}) => {
  const [summaryData, setSummaryData] = useState<SessionSummaryResponse | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'generating' | 'unavailable'>('loading');
  const retryCountRef = useRef(0);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Calculate formatted date and duration
  const sessionDate = session.startTime
    ? new Date(session.startTime).toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Recent Session';

  const durationMin =
    session.startTime && session.endTime
      ? Math.max(
          1,
          Math.round(
            (new Date(session.endTime).getTime() - new Date(session.startTime).getTime()) / 60000
          )
        )
      : 60;

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    if (!isOpen) {
      stopPolling();
      return;
    }

    // Reset state on open
    setSummaryData(null);
    setStatus('loading');
    retryCountRef.current = 0;
    stopPolling();

    const fetchSummary = async (isInitial = false) => {
      try {
        const res = await getSessionSummary(session._id);
        if (res && res.aiSummary && res.aiSummary.trim().length > 0) {
          setSummaryData(res);
          setStatus('ready');
          stopPolling();
          return true;
        }
      } catch (err) {
        console.warn('[SessionSummaryModal] Error fetching summary:', err);
      }

      if (isInitial) {
        setStatus('generating');
        // Start polling every 5 seconds, max 30s (6 retries)
        pollIntervalRef.current = setInterval(async () => {
          retryCountRef.current += 1;
          if (retryCountRef.current >= 6) {
            stopPolling();
            setStatus('unavailable');
            return;
          }
          await fetchSummary(false);
        }, 5000);
      }
      return false;
    };

    fetchSummary(true);

    return () => {
      stopPolling();
    };
  }, [isOpen, session._id]);

  // Handle escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 animate-fade-in">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-2xl transform rounded-2xl bg-white dark:bg-dark-card shadow-2xl border border-slate-200/80 dark:border-slate-800 transition-all flex flex-col max-h-[90vh] overflow-hidden animate-scale-in">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4 bg-slate-50/50 dark:bg-slate-800/30">
          <div>
            <div className="flex items-center gap-2 text-brand-600 dark:text-brand-400 font-bold text-lg">
              <Sparkles size={20} className="text-brand-500" />
              <span>Session Summary</span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
              {session.title} · {sessionDate} · {durationMin} mins
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {status === 'loading' && (
            <div className="space-y-3 py-4 animate-pulse">
              <div className="h-4 bg-slate-200 dark:bg-slate-700/60 rounded w-full"></div>
              <div className="h-4 bg-slate-200 dark:bg-slate-700/60 rounded w-11/12"></div>
              <div className="h-4 bg-slate-200 dark:bg-slate-700/60 rounded w-4/5"></div>
            </div>
          )}

          {status === 'generating' && (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <Loader2 className="animate-spin text-brand-600 dark:text-brand-400 mb-3" size={32} />
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                Summary is being generated...
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Aggregating available classroom activity and compiling the report.
              </p>
              <div className="w-48 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full mt-4 overflow-hidden">
                <div className="h-full bg-brand-500 rounded-full animate-pulse w-full"></div>
              </div>
            </div>
          )}

          {status === 'unavailable' && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <AlertCircle className="text-amber-500 mb-2" size={32} />
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                Summary unavailable
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                Could not generate or retrieve summary for this session. Please try again later.
              </p>
            </div>
          )}

          {status === 'ready' && summaryData?.aiSummary && (
            <>
              {/* Summary Text Card */}
              <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
                <div className="flex flex-col gap-1 border-b border-slate-200/70 bg-brand-50/70 px-5 py-3 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800 dark:bg-brand-950/30">
                  <div className="flex items-center gap-2 text-sm font-semibold text-brand-700 dark:text-brand-300">
                    <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-100 text-brand-600 dark:bg-brand-900/50 dark:text-brand-300">
                      <Sparkles size={15} />
                    </span>
                    <span>AI Analysis</span>
                  </div>
                  {summaryData.generatedAt && (
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      Generated {new Date(summaryData.generatedAt).toLocaleString([], {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </span>
                  )}
                </div>
                <div className="border-l-4 border-l-brand-500 px-5 py-4 sm:px-6 sm:py-5">
                  <p className="max-w-prose whitespace-pre-wrap text-[15px] leading-7 text-slate-700 dark:text-slate-200">
                    {summaryData.aiSummary}
                  </p>
                </div>
              </div>

              {/* 2x2 Key Stats Grid */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3">
                  Key Session Metrics
                </h4>
                <div className="grid grid-cols-2 gap-3.5">
                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-dark-card border border-slate-200/60 dark:border-slate-800/80">
                    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 mb-1">
                      <Users size={15} className="text-brand-500" />
                      <span className="text-xs font-medium">Total Students</span>
                    </div>
                    <p className="text-2xl font-bold text-slate-900 dark:text-white">
                      {summaryData.stats?.totalStudents ??
                        (session.batchIds ? session.batchIds.length : '--')}
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-dark-card border border-slate-200/60 dark:border-slate-800/80">
                    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 mb-1">
                      <ShieldAlert size={15} className="text-rose-500" />
                      <span className="text-xs font-medium">Blocked Attempts</span>
                    </div>
                    <p className="text-2xl font-bold text-rose-600 dark:text-rose-400">
                      {summaryData.stats?.totalBlockedAttempts ?? 0}
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-dark-card border border-slate-200/60 dark:border-slate-800/80">
                    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 mb-1">
                      <Clock size={15} className="text-indigo-500" />
                      <span className="text-xs font-medium">Peak Distraction Time</span>
                    </div>
                    <p className="text-base font-bold text-indigo-600 dark:text-indigo-400 truncate">
                      {summaryData.stats?.peakDistractionWindow || 'None recorded'}
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-dark-card border border-slate-200/60 dark:border-slate-800/80">
                    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 mb-1">
                      <AlertTriangle size={15} className="text-amber-500" />
                      <span className="text-xs font-medium">Flagged Students</span>
                    </div>
                    <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                      {summaryData.stats?.anomalousStudents ?? 0}
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
          <span className="text-xs text-slate-400 dark:text-slate-500">
            Academia Shield Analytics
          </span>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
};

export default SessionSummaryModal;
