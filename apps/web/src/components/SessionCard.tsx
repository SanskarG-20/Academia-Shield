import React from 'react';
import { Calendar, Clock, AlertCircle, Sparkles, Trash2, Play, Square, XCircle } from 'lucide-react';
import { Session, SessionStatus } from '../types';
import { Button } from './ui/Button';
import { MOCK_BATCHES } from '../constants'; // Fallback for batch names

interface SessionCardProps {
  session: any; // Using any for fast iteration with both MongoDB _id and local id
  isStudent: boolean;
  onStatusChange: (id: string, newStatus: string) => Promise<void>;
  onGenerateSummary: (session: any) => void;
  onDeleteSession: (id: string) => void;
  currentTime: Date;
}

export const SessionCard: React.FC<SessionCardProps> = ({
  session,
  isStudent,
  onStatusChange,
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

  const sessionId = session._id || session.id;

  return (
    <tr className={`hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors ${session.status.toLowerCase() === 'active' ? 'bg-emerald-50/30 dark:bg-emerald-900/5' : ''}`}>
      <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
        {session.title}
        {session.status.toLowerCase() === 'active' && (
          <span className="ml-2 inline-flex items-center gap-1 bg-red-900/40 text-red-400 text-xs px-2 py-0.5 rounded-full border border-red-700 animate-pulse">
            🔴 LIVE
          </span>
        )}
      </td>
      <td className="px-6 py-4 text-slate-500 dark:text-slate-400">
        {session.course}
        {session.batchIds && session.batchIds.length > 0 && (
          <div className="flex gap-1 mt-1">
            {session.batchIds.map((bid: string) => {
              const b = MOCK_BATCHES.find(mb => mb.id === bid);
              return b ? (
                <span key={bid} className="text-[10px] px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded text-slate-500">
                  {b.name}
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
          <div className="flex justify-end items-center gap-2">
            {session.status.toLowerCase() === 'upcoming' && (
              <Button size="sm" variant="outline" className="h-8 !px-2" onClick={() => onStatusChange(sessionId, 'active')}>
                <Play size={14} className="mr-1" /> Start
              </Button>
            )}
            {session.status.toLowerCase() === 'active' && (
              <Button size="sm" variant="danger" className="h-8 !px-2" onClick={() => onStatusChange(sessionId, 'completed')}>
                <Square size={14} className="mr-1" /> End
              </Button>
            )}
            {session.status.toLowerCase() === 'upcoming' && (
              <Button size="sm" variant="ghost" className="h-8 !px-2 text-slate-500" onClick={() => onStatusChange(sessionId, 'cancelled')}>
                <XCircle size={14} className="mr-1" /> Cancel
              </Button>
            )}

            <button
              className="text-brand-600 hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-300 p-2 rounded-full hover:bg-brand-50 dark:hover:bg-brand-900/10 transition-colors ml-2"
              onClick={() => onGenerateSummary(session)}
              title="AI Summary"
            >
              <Sparkles size={18} />
            </button>
            <button
              className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors p-2 rounded-full hover:bg-red-50 dark:hover:bg-red-900/10"
              onClick={() => onDeleteSession(sessionId)}
              title="Delete Session"
            >
              <Trash2 size={18} />
            </button>
          </div>
        </td>
      )}
    </tr>
  );
};