import React, { useEffect } from 'react';
import { AlertTriangle, X, ExternalLink } from 'lucide-react';
import { AnomalyEvent } from '../types';

export interface AnomalyAlertProps {
  alerts: AnomalyEvent[];
  onDismiss: (id: string) => void;
  onViewStudent: (studentId: string) => void;
}

interface SingleAlertProps {
  alert: AnomalyEvent;
  onDismiss: (id: string) => void;
  onViewStudent: (studentId: string) => void;
}

const SingleAlert: React.FC<SingleAlertProps> = ({ alert, onDismiss, onViewStudent }) => {
  const isHigh = alert.severity === 'HIGH';
  const alertId = alert.id || `${alert.studentId}-${alert.detectedAt}`;

  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(alertId);
    }, 8000); // Auto-dismiss after 8 seconds

    return () => clearTimeout(timer);
  }, [alertId, onDismiss]);

  return (
    <div
      role="alert"
      className={`pointer-events-auto w-84 sm:w-96 p-4 rounded-xl border backdrop-blur-md shadow-xl transition-all duration-300 animate-slide-in ${
        isHigh
          ? 'border-rose-500/80 bg-white/95 dark:bg-slate-900/95 shadow-rose-500/10'
          : 'border-amber-500/80 bg-white/95 dark:bg-slate-900/95 shadow-amber-500/10'
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <AlertTriangle
            size={18}
            className={`shrink-0 ${isHigh ? 'text-rose-500' : 'text-amber-500'} animate-bounce-subtle`}
          />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white">
            Distraction Alert
          </h4>
          <span
            className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
              isHigh
                ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/80 dark:text-rose-300 border-rose-200 dark:border-rose-800'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-950/80 dark:text-amber-300 border-amber-200 dark:border-amber-800'
            }`}
          >
            {alert.severity}
          </span>
        </div>

        <button
          onClick={() => onDismiss(alertId)}
          aria-label="Dismiss alert"
          className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <X size={15} />
        </button>
      </div>

      <div className="pl-6 space-y-1">
        <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">
          {alert.studentName || alert.studentId} showing unusual activity
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-semibold text-slate-800 dark:text-slate-200">
            {alert.blockedAttempts} blocked attempts
          </span>{' '}
          vs class avg <span className="font-mono">{alert.classAverage}</span>
        </p>

        <div className="pt-2 flex items-center justify-between">
          <span className="text-[10px] text-slate-400 font-mono">
            {new Date(alert.detectedAt).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })}
          </span>
          <button
            onClick={() => onViewStudent(alert.studentId)}
            className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-900 dark:text-slate-100 transition-colors"
          >
            <ExternalLink size={12} />
            View Student
          </button>
        </div>
      </div>
    </div>
  );
};

export const AnomalyAlert: React.FC<AnomalyAlertProps> = ({
  alerts,
  onDismiss,
  onViewStudent,
}) => {
  if (!alerts || alerts.length === 0) return null;

  // Stack maximum 3 visible alerts
  const visibleAlerts = alerts.slice(0, 3);

  return (
    <div className="fixed top-6 right-6 z-[70] flex flex-col gap-2.5 pointer-events-none max-w-full">
      {visibleAlerts.map((alert) => {
        const id = alert.id || `${alert.studentId}-${alert.detectedAt}`;
        return (
          <SingleAlert
            key={id}
            alert={alert}
            onDismiss={onDismiss}
            onViewStudent={onViewStudent}
          />
        );
      })}
    </div>
  );
};

export default AnomalyAlert;
