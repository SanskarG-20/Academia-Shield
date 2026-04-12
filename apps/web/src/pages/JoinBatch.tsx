import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, ArrowRight, ShieldCheck } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { MOCK_BATCHES } from '../constants';

export const JoinBatch: React.FC = () => {
  const navigate = useNavigate();
  const [joinCode, setJoinCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleJoinBatch = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    setTimeout(() => {
      // Validate code against mock batches
      const batch = MOCK_BATCHES.find(b => b.code === joinCode.toUpperCase());
      
      if (batch) {
        const currentJoined = JSON.parse(localStorage.getItem('joinedBatches') || '[]');
        if (!currentJoined.includes(batch.id)) {
          localStorage.setItem('joinedBatches', JSON.stringify([...currentJoined, batch.id]));
        }
        setIsLoading(false);
        navigate('/student/session');
      } else {
        setIsLoading(false);
        setError('Invalid Batch Code. Please check with your professor.');
      }
    }, 1000);
  };

  const handleSkip = () => {
    navigate('/student/session');
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden px-4">
      {/* Decorative Background */}
      <div className="absolute top-0 left-0 w-full h-64 bg-slate-800 dark:bg-slate-950" />
      
      <div className="relative z-10 w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 p-8">
        
        <div className="flex justify-center mb-6">
           <div className="bg-brand-50 dark:bg-brand-900/30 p-4 rounded-full">
              <Users size={32} className="text-brand-600 dark:text-brand-400" />
           </div>
        </div>

        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Join a Class Batch</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2">
            Enter the 6-character code provided by your professor to join your class.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
            {error}
          </div>
        )}

        <form onSubmit={handleJoinBatch} className="space-y-6">
          <Input 
             placeholder="ENTER CODE (e.g. CSE24X)"
             className="text-center text-2xl tracking-widest font-mono uppercase h-14"
             maxLength={8}
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
               Skip for now (Go to Dashboard)
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