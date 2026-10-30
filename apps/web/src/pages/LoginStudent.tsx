import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { GraduationCap, AlertCircle, Send, Hash } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { requestStudentOtp } from '../lib/api';

export const LoginStudent: React.FC = () => {
  const navigate = useNavigate();
  const [sapId, setSapId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // SAP ID Validation (11 digits)
    if (!sapId.trim() || sapId.length !== 11 || !/^\d+$/.test(sapId)) {
      setError('Invalid SAP ID. Please enter exactly 11 digits.');
      return;
    }

    setIsLoading(true);

    try {
      const response = await requestStudentOtp(sapId);
      localStorage.setItem('tempSapId', sapId);
      if (response?.mockOtp) {
        localStorage.setItem('tempMockOtp', response.mockOtp);
      } else {
        localStorage.removeItem('tempMockOtp');
      }
      navigate('/login/student/otp');
    } catch (err: any) {
      setError(err.message || 'Failed to send verification code.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden px-4">
      {/* Decorative Background */}
      <div className="absolute top-0 left-0 w-full h-64 bg-brand-600 dark:bg-brand-900" />
      <div className="absolute top-48 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-white dark:bg-slate-800 rounded-full opacity-10 blur-3xl" />

      <div className="relative z-10 w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-2xl shadow-slate-200/50 dark:shadow-none border border-slate-100 dark:border-slate-700 p-8">
        
        {/* Logo Section */}
        <div className="flex justify-center -mt-16 mb-6">
          <div className="bg-white dark:bg-slate-800 p-4 rounded-full shadow-lg ring-4 ring-slate-50 dark:ring-slate-900">
            <div className="bg-brand-600 p-3 rounded-full text-white">
              <GraduationCap size={32} />
            </div>
          </div>
        </div>

        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Student Login & Registration</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2">
            Enter your SAP ID to request a verification code.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3 animate-fade-in">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
          </div>
        )}

        <form onSubmit={handleRequestOtp} className="space-y-6">
          <div className="space-y-4">
            <Input 
              label="SAP ID (11 Digits)"
              type="text"
              placeholder="e.g. 60000001234"
              value={sapId}
              onChange={(e) => setSapId(e.target.value)}
              icon={<Hash size={16} />}
              maxLength={11}
              autoFocus
            />

          </div>

          <Button 
            type="submit" 
            className="w-full py-3 text-base" 
            disabled={isLoading || sapId.length !== 11}
            icon={isLoading ? null : <Send size={18} />}
          >
            {isLoading ? 'Sending Code...' : 'Login / Register'}
          </Button>
        </form>

        <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700 text-center">
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
            Not a student?
          </p>
          <Link 
            to="/login/professor" 
            className="text-sm font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 hover:underline"
          >
            Switch to Professor / Admin Login
          </Link>
        </div>
      </div>
      
      <div className="absolute bottom-6 w-full text-center">
        <Link to="/select-user" className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-sm transition-colors">
          ← Back to Role Selection
        </Link>
      </div>
    </div>
  );
};
