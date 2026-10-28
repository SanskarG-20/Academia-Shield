import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import {
  Plus,
  Users,
  Copy,
  ArrowRight,
  Hash,
  Shield,
  RefreshCw,
  UserCheck,
  Calendar,
  Loader2 as Spinner,
} from 'lucide-react';
import { createBatch, getBatches, getStudentBatches, joinStudentBatch } from '../lib/api';

export const Batches: React.FC = () => {
  const navigate = useNavigate();
  const userRole = localStorage.getItem('userRole') || 'professor';
  const isStudent = userRole === 'student';

  const [batches, setBatches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Professor Modal state
  const [isProfModalOpen, setIsProfModalOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [newBatch, setNewBatch] = useState({
    name: '',
    department: 'CE',
    year: '1',
    code: '',
  });

  // Student Modal state
  const [isStudentModalOpen, setIsStudentModalOpen] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [joinLoading, setJoinLoading] = useState(false);
  const [joinError, setJoinError] = useState('');

  const generateBatchCode = (dept: string) => {
    const random = Math.random().toString(36).substring(2, 6).toUpperCase();
    return `${dept.substring(0, 3).toUpperCase()}-${random}`;
  };

  async function fetchBatches() {
    try {
      setLoading(true);
      if (isStudent) {
        // Fetch ONLY from getStudentBatches (/api/v1/student/batches)
        const data = await getStudentBatches();
        setBatches(data);
      } else {
        const data = await getBatches();
        setBatches(data);
      }
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load batches.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchBatches();
  }, []);

  useEffect(() => {
    if (isProfModalOpen && !newBatch.code) {
      setNewBatch((prev) => ({ ...prev, code: generateBatchCode(prev.department) }));
    }
  }, [isProfModalOpen]);

  const handleCreateBatch = async () => {
    if (!newBatch.name || !newBatch.code) return;
    try {
      await createBatch({
        name: newBatch.name,
        code: newBatch.code,
        department: newBatch.department,
        year: newBatch.year,
      });

      setIsProfModalOpen(false);
      setNewBatch({ name: '', department: 'CE', year: '1', code: '' });
      await fetchBatches();
    } catch (err: any) {
      alert(err.message || 'Failed to create batch.');
    }
  };

  const handleJoinBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!joinCode.trim()) return;
    try {
      setJoinLoading(true);
      setJoinError('');
      await joinStudentBatch(joinCode.trim());
      setIsStudentModalOpen(false);
      setJoinCode('');
      // Refresh ONLY student batch list
      await fetchBatches();
    } catch (err: any) {
      setJoinError(err.message || 'Failed to join batch. Please verify the code.');
    } finally {
      setJoinLoading(false);
    }
  };

  const copyToClipboard = (code: string, id: string) => {
    navigator.clipboard.writeText(code);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {isStudent ? 'My Batches' : 'Class Management'}
          </h1>
          <p className="text-slate-500 dark:text-slate-400">
            {isStudent ? 'Batches you have joined' : 'Create and manage student batches'}
          </p>
        </div>
        {isStudent ? (
          <Button icon={<Plus size={18} />} onClick={() => setIsStudentModalOpen(true)}>
            Join New Batch
          </Button>
        ) : (
          <Button icon={<Plus size={18} />} onClick={() => setIsProfModalOpen(true)}>
            Create New Class
          </Button>
        )}
      </div>

      {error && (
        <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>
      )}

      {batches.length === 0 ? (
        <Card className="p-8 text-center space-y-4">
          <div className="mx-auto w-12 h-12 rounded-full bg-brand-50 dark:bg-brand-900/20 flex items-center justify-center text-brand-600 dark:text-brand-400">
            <Users size={24} />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">
              {isStudent ? 'You have not joined any batch yet.' : 'No classes created yet.'}
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {isStudent
                ? 'Enter a batch code provided by your professor to get started.'
                : 'Create your first class batch to start assigning monitoring sessions.'}
            </p>
          </div>
          {isStudent && (
            <div className="pt-2">
              <Button icon={<Plus size={18} />} onClick={() => setIsStudentModalOpen(true)}>
                Join New Batch
              </Button>
            </div>
          )}
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {batches.map((batch) => (
            <div
              key={batch._id || batch.id}
              className="group bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col overflow-hidden"
            >
              <div className="p-6 flex-1">
                <div className="flex justify-between items-start mb-4">
                  <div className="p-2.5 bg-brand-50 dark:bg-brand-900/20 rounded-lg text-brand-600 dark:text-brand-400">
                    <Users size={24} />
                  </div>
                  {isStudent ? (
                    <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 flex items-center gap-1">
                      <UserCheck size={12} /> Active Member
                    </span>
                  ) : (
                    <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                      {batch.students?.length || 0} Students
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">{batch.name}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                  {batch.department} • Year {batch.year}
                </p>

                {isStudent ? (
                  <div className="space-y-2 text-sm text-slate-600 dark:text-slate-300 pt-2 border-t border-slate-100 dark:border-slate-700">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-400">Professor:</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">
                        {batch.professor_name || batch.professorName || 'Professor'}
                      </span>
                    </div>
                    {batch.joined_at && (
                      <div className="flex justify-between items-center text-xs">
                        <span className="text-slate-400">Joined Date:</span>
                        <span>{new Date(batch.joined_at).toLocaleDateString()}</span>
                      </div>
                    )}
                    <div className="flex justify-between items-center text-xs pt-1">
                      <span className="text-slate-400">Sessions:</span>
                      <span className="font-medium text-brand-600 dark:text-brand-400">
                        {batch.active_session_count || 0} Active • {batch.upcoming_session_count || 0} Upcoming
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-100 dark:border-slate-700 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Hash size={14} className="text-slate-400" />
                      <div>
                        <p className="text-xs text-slate-500">Batch Code</p>
                        <p className="text-sm font-mono font-bold text-slate-900 dark:text-white tracking-wider">
                          {batch.code || batch.batch_code}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => copyToClipboard(batch.code || batch.batch_code, batch._id || batch.id)}
                      className="p-2 text-slate-400 hover:text-brand-600 hover:bg-white dark:hover:bg-slate-800 rounded-md transition-colors"
                      title="Copy Code"
                    >
                      {copiedId === (batch._id || batch.id) ? (
                        <span className="text-xs font-bold text-emerald-500">Copied!</span>
                      ) : (
                        <Copy size={16} />
                      )}
                    </button>
                  </div>
                )}
              </div>

              <div className="px-6 py-3 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 flex justify-end">
                <button
                  onClick={() => navigate(`/batches/${batch._id || batch.id}`)}
                  className="text-sm font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 flex items-center gap-1"
                >
                  View Details <ArrowRight size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Professor Create Batch Modal */}
      {!isStudent && (
        <Modal
          isOpen={isProfModalOpen}
          onClose={() => setIsProfModalOpen(false)}
          title="Create New Class Batch"
          footer={
            <>
              <Button variant="secondary" onClick={() => setIsProfModalOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateBatch}>Create Batch</Button>
            </>
          }
        >
          <div className="space-y-4">
            <Input
              label="Batch Name"
              placeholder="e.g. CS 301 - Data Structures"
              value={newBatch.name}
              onChange={(e) => setNewBatch({ ...newBatch, name: e.target.value })}
            />

            <div className="grid grid-cols-2 gap-4">
              <Select
                label="Department"
                value={newBatch.department}
                onChange={(e) => {
                  const dept = e.target.value;
                  setNewBatch({ ...newBatch, department: dept, code: generateBatchCode(dept) });
                }}
                options={[
                  { value: 'CE', label: 'Computer Engineering (CE)' },
                  { value: 'IT', label: 'Information Tech (IT)' },
                  { value: 'AIDS', label: 'AI & Data Science (AIDS)' },
                  { value: 'EXTC', label: 'Electronics & Telecomm (EXTC)' },
                ]}
              />

              <Select
                label="Academic Year"
                value={newBatch.year}
                onChange={(e) => setNewBatch({ ...newBatch, year: e.target.value })}
                options={[
                  { value: '1', label: 'Year 1 (FE)' },
                  { value: '2', label: 'Year 2 (SE)' },
                  { value: '3', label: 'Year 3 (TE)' },
                  { value: '4', label: 'Year 4 (BE)' },
                ]}
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  Batch Code (Share with Students)
                </label>
                <button
                  type="button"
                  onClick={() =>
                    setNewBatch((prev) => ({ ...prev, code: generateBatchCode(prev.department) }))
                  }
                  className="text-xs text-brand-600 hover:text-brand-700 flex items-center gap-1"
                >
                  <RefreshCw size={12} /> Regenerate
                </button>
              </div>
              <Input
                value={newBatch.code}
                onChange={(e) => setNewBatch({ ...newBatch, code: e.target.value.toUpperCase() })}
                placeholder="CE-X9Y2"
              />
            </div>
          </div>
        </Modal>
      )}

      {/* Student Join Batch Modal */}
      {isStudent && (
        <Modal
          isOpen={isStudentModalOpen}
          onClose={() => {
            setIsStudentModalOpen(false);
            setJoinError('');
          }}
          title="Join New Batch"
          footer={
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setIsStudentModalOpen(false);
                  setJoinError('');
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleJoinBatch} disabled={joinLoading}>
                {joinLoading ? 'Joining...' : 'Join Batch'}
              </Button>
            </>
          }
        >
          <form onSubmit={handleJoinBatch} className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Enter the unique 6-character Batch Code provided by your professor.
            </p>
            <Input
              label="Batch Code"
              placeholder="e.g. ABC123"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              autoFocus
            />
            {joinError && (
              <p className="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 p-2.5 rounded-lg border border-red-200 dark:border-red-800">
                {joinError}
              </p>
            )}
          </form>
        </Modal>
      )}
    </div>
  );
};
