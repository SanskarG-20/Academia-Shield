import React, { useEffect, useState } from 'react';
import { getSessionCoverage, SessionCoverage } from '../lib/api';
import { getSocket, joinSession } from '../lib/socket';

type CoverageStatus = SessionCoverage['students'][number]['status'];

const buckets: { status: CoverageStatus; label: string; color: string }[] = [
  { status: 'active', label: 'Active', color: 'text-emerald-600 dark:text-emerald-400' },
  { status: 'enrolled_silent', label: 'Enrolled but silent', color: 'text-amber-600 dark:text-amber-400' },
  { status: 'not_enrolled', label: 'Not enrolled', color: 'text-slate-600 dark:text-slate-300' },
];

export const SessionCoveragePanel: React.FC<{ sessionId: string }> = ({ sessionId }) => {
  const [coverage, setCoverage] = useState<SessionCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    const socket = getSocket();
    joinSession(sessionId);

    const refresh = async () => {
      try {
        const result = await getSessionCoverage(sessionId);
        if (mounted) { setCoverage(result); setError(''); }
      } catch (err: any) {
        if (mounted) setError(err.message || 'Unable to load coverage.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    const onCoverage = (result: SessionCoverage) => {
      if (result.sessionId !== sessionId) return;
      setCoverage(result);
      setLoading(false);
      setError('');
    };
    const onConnect = () => { void refresh(); };
    socket.on('session_coverage', onCoverage);
    socket.on('connect', onConnect);
    void refresh();
    const poll = setInterval(() => {
      if (!socket.connected) void refresh();
    }, 20_000);

    return () => {
      mounted = false;
      clearInterval(poll);
      socket.off('session_coverage', onCoverage);
      socket.off('connect', onConnect);
    };
  }, [sessionId]);

  return (
    <section aria-label="Session coverage" className="mb-6 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Coverage</h3>
        {coverage && <span className="text-xs text-slate-500">{coverage.summary.total} students · {coverage.summary.joined} marked attendance</span>}
      </div>
      {loading && <p className="text-sm text-slate-500" role="status">Loading coverage...</p>}
      {error && <p className="text-sm text-rose-600 dark:text-rose-400 mb-3" role="alert">{error}</p>}
      {coverage && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {buckets.map(bucket => {
            const students = coverage.students.filter(student => student.status === bucket.status);
            return (
              <div key={bucket.status} className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 p-4">
                <div className="flex items-center justify-between gap-2">
                  <h4 className={`text-sm font-semibold ${bucket.color}`}>{bucket.label}</h4>
                  <span className={`text-lg font-bold ${bucket.color}`}>{coverage.summary[bucket.status]}</span>
                </div>
                {students.length ? (
                  <ul className="mt-3 space-y-1 text-sm text-slate-700 dark:text-slate-200">
                    {students.map(student => <li key={student.studentId}>{student.name || student.sapId || 'Student'}{student.joined ? ' · attended' : ''}</li>)}
                  </ul>
                ) : <p className="mt-3 text-xs text-slate-500">No students</p>}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
