import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { School, ArrowRight, AlertCircle, Mail, Lock, User } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { professorLogin } from '../lib/api';

export const LoginProfessor: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }

    setIsLoading(true);
    try {
      const res = await professorLogin(email, password);
      if (res.requiresProfileSetup) {
        navigate('/professor/profile');
      } else {
        navigate('/dashboard');
      }
    } catch (err: any) {
      setError(err.message || 'Invalid credentials');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden px-4">
      {/* Decorative Background */}
      <div className="absolute top-0 left-0 w-full h-64 bg-blue-600 dark:bg-blue-900" />
      <div className="absolute top-48 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-white dark:bg-slate-800 rounded-full opacity-10 blur-3xl" />

      <div className="relative z-10 w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-2xl shadow-slate-200/50 dark:shadow-none border border-slate-100 dark:border-slate-700 p-8">
        
        {/* Logo Section */}
        <div className="flex justify-center -mt-16 mb-6">
          <div className="bg-white dark:bg-slate-800 p-4 rounded-full shadow-lg ring-4 ring-slate-50 dark:ring-slate-900">
            <div className="bg-blue-600 p-3 rounded-full text-white">
              <School size={32} />
            </div>
          </div>
        </div>

        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Faculty Login & Registration</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2">
            Enter your faculty credentials. New accounts require an approved institutional email domain.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3 animate-fade-in">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
          </div>
        )}

        <form className="space-y-6" onSubmit={handleLogin}>
          <div className="space-y-4">
            <Input 
              label="Email Address"
              type="email" 
              placeholder="admin@university.edu"
              icon={<Mail size={16} />}
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (error) setError(null);
              }}
            />
            
            <div>
              <Input 
                label="Password"
                type="password" 
                placeholder="••••••••"
                icon={<Lock size={16} />}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <div className="flex items-center justify-between text-sm mt-2">
                <label className="flex items-center text-slate-500 dark:text-slate-400 cursor-pointer hover:text-slate-700 dark:hover:text-slate-300 transition-colors">
                  <input type="checkbox" className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 mr-2" />
                  Remember me
                </label>
                <span className="text-slate-400 cursor-not-allowed font-medium transition-colors" title="Contact your institution administrator">Forgot Password?</span>
              </div>
            </div>
          </div>

          <Button 
            type="submit" 
            className="w-full py-3 text-base bg-blue-600 hover:bg-blue-700 focus:ring-blue-500" 
            size="lg" 
            disabled={isLoading}
            icon={isLoading ? null : <ArrowRight size={18} />}
          >
            {isLoading ? 'Authenticating...' : 'Sign In / Register'}
          </Button>

          {error && (
            <p className="text-red-400 text-sm mt-2 text-center">{error}</p>
          )}
        </form>

        <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700 text-center">
          {/* Demo credentials removed for production */}
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
            Not a professor?
          </p>
          <Link 
            to="/login/student" 
            className="text-sm font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 hover:underline inline-flex items-center gap-1"
          >
            Switch to Student Login <User size={14} />
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
