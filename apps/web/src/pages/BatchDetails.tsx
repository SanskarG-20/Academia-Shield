import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Batch, Session, SessionStatus, SessionType } from '../types';
import {
  Users,
  ArrowLeft,
  Search,
  Calendar,
  Hash,
  Copy,
  UserPlus,
  History,
  PlusCircle,
  Loader2 as Spinner,
} from 'lucide-react';
import { getBatchById, getSessions } from '../lib/api';

export const BatchDetails: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [batch, setBatch] = useState<Batch | null>(null);
  const [activeSessions, setActiveSessions] = useState<Session[]>([]);
  const [pastSessions, setPastSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function fetchData() {
      if (!id) return;

      try {
        setLoading(true);
        const [batchData, sessionsData] = await Promise.all([getBatchById(id), getSessions()]);
        setBatch(batchData);

        const batchSessions = sessionsData.filter((session) => session.batchIds?.includes(batchData._id));
        const now = new Date();

        const activeOrUpcoming = batchSessions.filter((session) => {
          const isPast = new Date(session.endTime) < now;
          return !isPast && String(session.status).toLowerCase() !== String(SessionStatus.COMPLETED).toLowerCase();
        });

        const completedOrPast = batchSessions.filter((session) => {
          const isPast = new Date(session.endTime) < now;
          return isPast || String(session.status).toLowerCase() === String(SessionStatus.COMPLETED).toLowerCase();
        });

        setActiveSessions(activeOrUpcoming);
        setPastSessions(completedOrPast);
        setError('');
      } catch (err: any) {
        setError(err.message || 'Failed to load class details.');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [id]);

  const copyCode = () => {
    if (!batch) return;
    navigator.clipboard.writeText(batch.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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

  if (!batch) {
    return <div className="p-6">Class not found.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <button
          onClick={() => navigate('/batches')}
          className="flex items-center text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
        >
          <ArrowLeft size={18} className="mr-2" /> Back to Classes
        </button>
        <Button onClick={() => navigate('/sessions')} icon={<PlusCircle size={18} />}>
          Assign Session
        </Button>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm relative overflow-hidden">
        <div className="absolute top-0 right-0 p-3 opacity-5">
          <Users size={120} />
        </div>
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold text-slate-900 dark:text-white">{batch.name}</h1>
              <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-brand-50 text-brand-700 border border-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:border-brand-800">
                {batch.department} - Year {batch.year}
              </span>
            </div>
            <p className="text-slate-500 dark:text-slate-400">Students: {batch.students?.length || 0}</p>
          </div>

          <div className="flex flex-col items-end">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">Class Code</span>
            <button
              onClick={copyCode}
              className="group flex items-center gap-3 bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-4 py-2 rounded-lg font-mono text-xl font-bold hover:shadow-lg transition-all active:scale-95"
            >
              <Hash size={20} className="opacity-50" />
              {batch.code}
              {copied ? (
                <span className="ml-2 text-sm text-emerald-400 dark:text-emerald-600">Copied!</span>
              ) : (
                <Copy size={18} className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card
            title={`Students (${batch.students?.length || 0})`}
            action={<div className="w-48"><Input placeholder="Search student..." className="mb-0 h-9 text-sm" icon={<Search size={14} />} /></div>}
            noPadding
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700">
                  <tr>
                    <th className="px-6 py-3 font-medium text-slate-500">Name</th>
                    <th className="px-6 py-3 font-medium text-slate-500">Roll No.</th>
                    <th className="px-6 py-3 font-medium text-slate-500">SAP ID</th>
                    <th className="px-6 py-3 font-medium text-slate-500">Email</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {(batch.students || []).map((student) => (
                    <tr key={student._id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                      <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">{student.name}</td>
                      <td className="px-6 py-4 text-slate-500 font-mono text-xs">{student.rollNumber}</td>
                      <td className="px-6 py-4 text-slate-500 font-mono text-xs">{student.sapId}</td>
                      <td className="px-6 py-4 text-slate-500">{student.email || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Active & Upcoming Sessions">
            {activeSessions.length > 0 ? (
              <div className="space-y-3">
                {activeSessions.map((session) => (
                  <div
                    key={session._id}
                    className="p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 hover:border-brand-200 transition-colors cursor-pointer"
                    onClick={() => navigate('/sessions')}
                  >
                    <h4 className="font-medium text-sm text-slate-900 dark:text-white truncate">{session.title}</h4>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs text-slate-500">{new Date(session.startTime).toLocaleDateString()}</span>
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          String(session.status).toLowerCase() === 'active'
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-blue-50 text-blue-600'
                        }`}
                      >
                        {session.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-slate-500">
                <Calendar className="w-10 h-10 mx-auto mb-2 opacity-20" />
                <p className="text-sm">No active sessions.</p>
                <Button variant="ghost" size="sm" className="mt-2 text-brand-600" onClick={() => navigate('/sessions')}>
                  Assign Session
                </Button>
              </div>
            )}
          </Card>

          <Card title="Session History">
            {pastSessions.length > 0 ? (
              <div className="space-y-4">
                {pastSessions.map((session) => (
                  <div
                    key={session._id}
                    className="flex items-start gap-3 pb-3 border-b border-slate-100 dark:border-slate-700 last:border-0 last:pb-0"
                  >
                    <div className="p-2 bg-slate-100 dark:bg-slate-800 rounded text-slate-400 mt-0.5">
                      <History size={14} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-start">
                        <h4 className="font-medium text-sm text-slate-900 dark:text-slate-300 truncate pr-2">{session.title}</h4>
                        <span className="text-[10px] text-slate-400 whitespace-nowrap mt-0.5">
                          {new Date(session.endTime).toLocaleDateString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${
                            session.type === SessionType.EXAM
                              ? 'bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800'
                              : session.type === SessionType.LAB
                              ? 'bg-purple-50 text-purple-700 border-purple-100 dark:bg-purple-900/20 dark:text-purple-400 dark:border-purple-800'
                              : 'bg-blue-50 text-blue-700 border-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800'
                          }`}
                        >
                          {session.type}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-slate-400 text-sm italic">No past session history available.</div>
            )}
          </Card>

          <div className="bg-gradient-to-br from-brand-500 to-blue-600 rounded-xl p-6 text-white shadow-lg">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-brand-100 text-sm font-medium mb-1">Invite Students</p>
                <h3 className="text-2xl font-bold mb-4">Share Code</h3>
                <p className="text-sm text-brand-100/80 leading-relaxed">
                  Share the class code <strong>{batch.code}</strong> with your students. They can join via their dashboard.
                </p>
              </div>
              <div className="bg-white/20 p-3 rounded-lg backdrop-blur-sm">
                <UserPlus size={24} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
