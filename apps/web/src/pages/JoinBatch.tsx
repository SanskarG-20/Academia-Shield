import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, ArrowRight, ShieldCheck, GraduationCap, Loader2, CheckCircle2 } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Batch } from '../types';
import { getAvailableBatches, joinAvailableBatch, joinBatch } from '../lib/api';

export const JoinBatch: React.FC = () => {
  const navigate = useNavigate();
  const [joinCode, setJoinCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [availableBatches, setAvailableBatches] = useState<Batch[]>([]);
  const [isLoadingBatches, setIsLoadingBatches] = useState(true);
  const [batchListError, setBatchListError] = useState<string | null>(null);
  const [joiningBatchId, setJoiningBatchId] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadAvailableBatches = async () => {
    try {
      setIsLoadingBatches(true);
      setBatchListError(null);
      setAvailableBatches(await getAvailableBatches());
    } catch (err: any) {
      setBatchListError(err.message || 'Could not load batches for your department.');
    } finally {
      setIsLoadingBatches(false);
    }
  };

  useEffect(() => {
    void loadAvailableBatches();
  }, []);

  const handleQuickJoin = async (batch: Batch) => {
    try {
      setJoiningBatchId(batch._id);
      setBatchListError(null);
      setSuccessMessage(null);
      await joinAvailableBatch(batch._id);
      setAvailableBatches((current) => current.filter((item) => item._id !== batch._id));
      setSuccessMessage(`You joined ${batch.name}.`);
    } catch (err: any) {
      setBatchListError(err.message || 'Could not join this batch.');
    } finally {
      setJoiningBatchId(null);
    }
  };

  const handleJoinBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await joinBatch(joinCode.toUpperCase());
      navigate('/student/session');
    } catch (err: any) {
      setError(err.message || 'Invalid Batch Code. Please check with your professor.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkip = () => {
    navigate('/student/session');
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden px-4">
      {/* Decorative Background */}
      <div className="absolute top-0 left-0 w-full h-64 bg-slate-800 dark:bg-slate-950" />
      
      <div className="relative z-10 my-8 w-full max-w-3xl bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8">
        
        <div className="flex justify-center mb-6">
           <div className="bg-brand-50 dark:bg-brand-900/30 p-4 rounded-full">
              <Users size={32} className="text-brand-600 dark:text-brand-400" />
           </div>
        </div>

        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Join Your Class Batches</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2">
            Choose a batch from your department or enter a code provided by your professor.
          </p>
        </div>

        {successMessage && (
          <div className="mb-6 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400">
            <CheckCircle2 size={17} className="shrink-0" />
            {successMessage}
          </div>
        )}

        <section aria-labelledby="available-batches-heading">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 id="available-batches-heading" className="font-semibold text-slate-900 dark:text-white">
                Available in your department
              </h3>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                These suggestions use the department saved in your profile.
              </p>
            </div>
            {!isLoadingBatches && batchListError && (
              <Button type="button" variant="ghost" size="sm" onClick={() => void loadAvailableBatches()}>
                Retry
              </Button>
            )}
          </div>

          {isLoadingBatches ? (
            <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
              <Loader2 size={18} className="animate-spin" /> Loading matching batches...
            </div>
          ) : batchListError ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
              {batchListError}
            </div>
          ) : availableBatches.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center dark:border-slate-700 dark:bg-slate-900/40">
              <GraduationCap size={24} className="mx-auto mb-2 text-slate-400" />
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">No new department batches available</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">You can still join a class using its code below.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {availableBatches.map((batch) => (
                <article key={batch._id} className="flex flex-col justify-between rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-900/40">
                  <div>
                    <div className="flex items-start gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300">
                        <Users size={17} />
                      </span>
                      <div className="min-w-0">
                        <h4 className="truncate font-semibold text-slate-900 dark:text-white">{batch.name}</h4>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          {batch.department} · Year {batch.year}
                        </p>
                      </div>
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    className="mt-4 w-full"
                    disabled={joiningBatchId !== null}
                    onClick={() => void handleQuickJoin(batch)}
                    icon={joiningBatchId === batch._id ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
                  >
                    {joiningBatchId === batch._id ? 'Joining...' : 'Join batch'}
                  </Button>
                </article>
              ))}
            </div>
          )}
        </section>

        <div className="my-7 flex items-center gap-3" aria-hidden="true">
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
          <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Or use a code</span>
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
            {error}
          </div>
        )}

        <form onSubmit={handleJoinBatch} className="space-y-6">
          <Input 
             placeholder="ENTER CODE (e.g. CE-SY-2024)"
             className="text-center text-2xl tracking-widest font-mono uppercase h-14"
             value={joinCode}
             onChange={e => setJoinCode(e.target.value.toUpperCase())}
             autoFocus
          />

          <Button 
            type="submit" 
            className="w-full py-3" 
            size="lg"
            disabled={isLoading || joinCode.length < 3}
            icon={isLoading ? null : <ArrowRight size={18} />}
          >
            {isLoading ? 'Verifying...' : 'Join Class'}
          </Button>

          <div className="text-center">
             <button 
               type="button"
               onClick={handleSkip}
               className="text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
             >
               Continue to Dashboard
             </button>
          </div>
        </form>

        <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700 flex items-center justify-center gap-2 text-xs text-slate-400">
          <ShieldCheck size={14} /> Secure Access Point
        </div>
      </div>
    </div>
  );
};
