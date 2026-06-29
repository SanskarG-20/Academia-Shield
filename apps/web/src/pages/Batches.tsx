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
  Loader2 as Spinner,
} from 'lucide-react';
import { Batch } from '../types';
import { createBatch, getBatches } from '../lib/api';

export const Batches: React.FC = () => {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [newBatch, setNewBatch] = useState({
    name: '',
    department: 'CE',
    year: '1',
    code: '',
  });

  const generateBatchCode = (dept: string) => {
    const random = Math.random().toString(36).substring(2, 6).toUpperCase();
    return `${dept.substring(0, 3).toUpperCase()}-${random}`;
  };

  async function fetchBatches() {
    try {
      setLoading(true);
      const data = await getBatches();
      setBatches(data);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to load classes.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchBatches();
  }, []);

  useEffect(() => {
    if (isModalOpen && !newBatch.code) {
      setNewBatch((prev) => ({ ...prev, code: generateBatchCode(prev.department) }));
    }
  }, [isModalOpen]);

  const handleCreateBatch = async () => {
    if (!newBatch.name || !newBatch.code) {
      return;
    }

    try {
      await createBatch({
        name: newBatch.name,
        code: newBatch.code,
        department: newBatch.department,
        year: newBatch.year,
      });

      setIsModalOpen(false);
      setNewBatch({ name: '', department: 'CE', year: '1', code: '' });
      await fetchBatches();
    } catch (err: any) {
      alert(err.message || 'Failed to create class.');
    }
  };

  const copyToClipboard = (code: string, id: string) => {
    navigator.clipboard.writeText(code);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const calculateCodeStrength = (code: string) => {
    if (!code) return { score: 0, label: 'Empty', color: 'bg-slate-200' };
    let score = 0;
    if (code.length >= 6) score += 40;
    if (/[A-Z]/.test(code)) score += 20;
    if (/[0-9]/.test(code)) score += 20;
    if (code.length > 7) score += 20;

    if (code.length < 6) return { score: 20, label: 'Too Short', color: 'bg-red-500' };
    if (score >= 80) return { score: 100, label: 'Strong', color: 'bg-emerald-500' };
    if (score >= 60) return { score: 70, label: 'Medium', color: 'bg-yellow-500' };
    return { score: 40, label: 'Weak', color: 'bg-orange-500' };
  };

  const strength = calculateCodeStrength(newBatch.code);

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
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Class Management</h1>
          <p className="text-slate-500 dark:text-slate-400">Create and manage student batches.</p>
        </div>
        <Button icon={<Plus size={18} />} onClick={() => setIsModalOpen(true)}>
          Create New Class
        </Button>
      </div>

      {error && (
        <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>
      )}

      {batches.length === 0 ? (
        <Card>
          <p className="text-slate-500">No classes created yet. Create your first class to get started.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {batches.map((batch) => (
            <div
              key={batch._id}
              className="group bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col overflow-hidden"
            >
              <div className="p-6 flex-1">
                <div className="flex justify-between items-start mb-4">
                  <div className="p-2.5 bg-brand-50 dark:bg-brand-900/20 rounded-lg text-brand-600 dark:text-brand-400">
                    <Users size={24} />
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                    {batch.students?.length || 0} Students
                  </span>
                </div>

                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">{batch.name}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                  {batch.department} • Year {batch.year}
                </p>

                <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-100 dark:border-slate-700 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Hash size={14} className="text-slate-400" />
                    <div>
                      <p className="text-xs text-slate-500">Batch Code</p>
                      <p className="text-sm font-mono font-bold text-slate-900 dark:text-white tracking-wider">
                        {batch.code}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => copyToClipboard(batch.code, batch._id)}
                    className="p-2 text-slate-400 hover:text-brand-600 hover:bg-white dark:hover:bg-slate-800 rounded-md transition-colors"
                    title="Copy Code"
                  >
                    {copiedId === batch._id ? (
                      <span className="text-xs font-bold text-emerald-500">Copied!</span>
                    ) : (
                      <Copy size={16} />
                    )}
                  </button>
                </div>
              </div>

              <div className="px-6 py-3 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 flex justify-end">
                <button
                  onClick={() => navigate(`/batches/${batch._id}`)}
                  className="text-sm font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 flex items-center gap-1"
                >
                  View Details <ArrowRight size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Create New Class Batch"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateBatch} disabled={strength.label === 'Too Short' || !newBatch.name}>
              Create Class
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Batch Name"
            placeholder="e.g. CSE-A 2024"
            value={newBatch.name}
            onChange={(e) => setNewBatch({ ...newBatch, name: e.target.value })}
            autoFocus
          />
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Department"
              options={[
                { value: 'CE', label: 'Computer Engineering' },
                { value: 'IT', label: 'Information Technology' },
                { value: 'AIDS', label: 'AI & Data Science' },
                { value: 'AIML', label: 'AI & Machine Learning' },
                { value: 'CSE_ICB', label: 'CSE (ICB)' },
                { value: 'CSE_DS', label: 'CSE (DS)' },
                { value: 'MECH', label: 'Mechanical Engineering' },
                { value: 'EXTC', label: 'EXTC' },
              ]}
              value={newBatch.department}
              onChange={(e) => {
                setNewBatch((prev) => ({
                  ...prev,
                  department: e.target.value,
                  code: generateBatchCode(e.target.value),
                }));
              }}
            />
            <Select
              label="Year"
              options={[
                { value: '1', label: '1st Year' },
                { value: '2', label: '2nd Year' },
                { value: '3', label: '3rd Year' },
                { value: '4', label: '4th Year' },
              ]}
              value={newBatch.year}
              onChange={(e) => setNewBatch({ ...newBatch, year: e.target.value })}
            />
          </div>

          <div className="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-lg border border-blue-100 dark:border-blue-900/30">
            <div className="flex justify-between items-center mb-2">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 flex items-center gap-2">
                <Shield size={14} className="text-brand-600" />
                Class Access Code
              </label>
              <button
                onClick={() => setNewBatch((prev) => ({ ...prev, code: generateBatchCode(prev.department) }))}
                className="text-xs text-brand-600 hover:text-brand-700 dark:text-brand-400 flex items-center gap-1"
              >
                <RefreshCw size={12} /> Auto-generate
              </button>
            </div>

            <Input
              value={newBatch.code}
              onChange={(e) =>
                setNewBatch((prev) => ({
                  ...prev,
                  code: e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, ''),
                }))
              }
              placeholder="ENTER CODE"
              maxLength={12}
              className="font-mono tracking-widest text-center uppercase text-lg font-bold"
            />

            <div className="mt-3">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-500">Security Strength</span>
                <span className={`font-bold ${strength.color.replace('bg-', 'text-')}`}>{strength.label}</span>
              </div>
              <div className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                <div className={`h-full transition-all duration-500 ${strength.color}`} style={{ width: `${strength.score}%` }} />
              </div>
              <p className="text-[10px] text-slate-400 mt-1.5">Recommended: 6+ alphanumeric characters.</p>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};
