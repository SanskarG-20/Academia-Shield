import React from 'react';
import { Calendar, Clock, AlertCircle, Sparkles, Trash2, Play, Square, XCircle, Eye } from 'lucide-react';
import { Session, SessionStatus } from '../types';
import { Button } from './ui/Button';

interface SessionCardProps {
  session: Session;
  isStudent: boolean;
  batchNameById?: Record<string, string>;
  onStatusChange: (id: string, newStatus: string) => Promise<void>;
  onOpenMonitor?: (session: Session) => void;
  onOpenSummary?: (session: Session) => void;
  onGenerateSummary: (session: Session) => void;
  onDeleteSession: (id: string) => void;
  currentTime: Date;
}

export const SessionCard: React.FC<SessionCardProps> = ({
  session,
  isStudent,
  batchNameById = {},
  onStatusChange,
  onOpenMonitor,
  onOpenSummary,
  onGenerateSummary,
  onDeleteSession,
  currentTime,
}) => {
  const isStartingSoon = (s: Session) => {
    const start = new Date(s.startTime);
    const diff = start.getTime() - currentTime.getTime();
    return s.status === SessionStatus.UPCOMING && diff > 0 && diff <= 15 * 60 * 1000;
  };

  const getStatusBadge = (s: Session) => {
    if (isStartingSoon(s)) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 border border-amber-200 animate-pulse">
          <AlertCircle size={12} className="mr-1" />
          Starting Soon
        </span>
      );
    }

    switch (s.status.toLowerCase()) {
      case 'active':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 border border-emerald-200 shadow-sm">
            <span className="relative flex h-2 w-2 mr-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Active Now
          </span>
        );
      case 'upcoming':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800">Upcoming</span>;
      case 'completed':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700">Completed</span>;
      case 'cancelled':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-600 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800">Cancelled</span>;
      default:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">Unknown</span>;
    }
  };

  const sessionId = session._id;

  return (
    <tr className={`hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors ${session.status.toLowerCase() === 'active' ? 'bg-emerald-50/30 dark:bg-emerald-900/5' : ''}`}>
      <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
        {session.title}
        {session.status.toLowerCase() === 'active' && (
          <span className="ml-2.5 inline-flex items-center gap-1.5 bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 text-xs font-semibold px-2.5 py-0.5 rounded-full border border-rose-300 dark:border-rose-800 shadow-xs">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
            </span>
            LIVE
          </span>
        )}
      </td>
      <td className="px-6 py-4 text-slate-500 dark:text-slate-400">
        {session.course}
        {session.batchIds && session.batchIds.length > 0 && (
          <div className="flex gap-1 mt-1">
            {session.batchIds.map((bid: string) => {
              const batchName = batchNameById[bid];
              return batchName ? (
                <span key={bid} className="text-[10px] px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded text-slate-500">
                  {batchName}
                </span>
              ) : null;
            })}
          </div>
        )}
      </td>
      <td className="px-6 py-4">
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300">
          {session.type}
        </span>
      </td>
      <td className="px-6 py-4 text-slate-500 dark:text-slate-400">
        <div className="flex flex-col text-xs">
          <span className="flex items-center gap-1"><Calendar size={12}/> {new Date(session.startTime).toLocaleDateString()}</span>
          <span className="flex items-center gap-1"><Clock size={12}/> {new Date(session.startTime).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
        </div>
      </td>
      <td className="px-6 py-4">
        {getStatusBadge(session)}
      </td>
      {!isStudent && (
        <td className="px-6 py-4 text-right">
          <div className="flex flex-col items-end gap-1.5">
            <div className="flex justify-end items-center gap-2">
              {session.status.toLowerCase() === 'upcoming' && (
                <Button size="sm" variant="outline" className="h-8 !px-2" onClick={() => onStatusChange(sessionId, 'active')}>
                  <Play size={14} className="mr-1" /> Start
                </Button>
              )}
              {session.status.toLowerCase() === 'active' && (
                <>
                  <Button size="sm" variant="outline" className="h-8 !px-2 !border-brand-500 !text-brand-600 dark:!text-brand-400" onClick={() => onOpenMonitor?.(session)}>
                    <Eye size={14} className="mr-1" /> Live Monitor
                  </Button>
                  <Button size="sm" variant="danger" className="h-8 !px-2" onClick={() => onStatusChange(sessionId, 'completed')}>
                    <Square size={14} className="mr-1" /> End
                  </Button>
                </>
              )}
              {session.status.toLowerCase() === 'upcoming' && (
                <Button size="sm" variant="ghost" className="h-8 !px-2 text-slate-500" onClick={() => onStatusChange(sessionId, 'cancelled')}>
                  <XCircle size={14} className="mr-1" /> Cancel
                </Button>
              )}

              <button
                className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors p-2 rounded-full hover:bg-red-50 dark:hover:bg-red-900/10"
                onClick={() => onDeleteSession(sessionId)}
                title="Delete Session"
              >
                <Trash2 size={18} />
              </button>
            </div>

            {session.status.toLowerCase() === 'completed' && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 !px-2 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950/40"
                onClick={() => (onOpenSummary ? onOpenSummary(session) : onGenerateSummary(session))}
              >
                <Sparkles size={13} className="mr-1 text-brand-500" /> View AI Summary
              </Button>
            )}
          </div>
        </td>
      )}
    </tr>
  );
};
