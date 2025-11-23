import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GraduationCap, Lock, Mail, ArrowRight, User, AlertCircle } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = (role: 'admin' | 'student') => {
    setError(null);

    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }

    // Role-based Credential Validation
    if (role === 'admin') {
      const isAdminEmail = email.toLowerCase().endsWith('@university.edu') && !email.toLowerCase().includes('student');
      if (!isAdminEmail) {
        setError('Access Denied: Faculty credentials required. Email must end in @university.edu');
        return;
      }
    }

    if (role === 'student') {
      const isStudentEmail = email.toLowerCase().endsWith('@student.university.edu');
      if (!isStudentEmail) {
        setError('Access Denied: Student credentials required. Email must end in @student.university.edu');
        return;
      }
    }

    setIsLoading(true);
    // Simulate API call
    setTimeout(() => {
      localStorage.setItem('isAuthenticated', 'true');
      localStorage.setItem('userRole', role);
      localStorage.setItem('userName', name || (role === 'admin' ? 'Dr. A. Turing' : 'Student User'));
      localStorage.setItem('userEmail', email);
      setIsLoading(false);
      navigate('/dashboard');
    }, 1000);
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-slate-100 via-slate-50 to-blue-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 relative overflow-hidden">
      
      {/* Abstract shapes */}
      <div className="absolute -top-40 -right-40 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl animate-pulse" />
      <div className="absolute top-40 -left-20 w-72 h-72 bg-blue-500/10 rounded-full blur-3xl" />

      <div className="relative w-full max-w-md p-8 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 dark:border-slate-700/50">
        <div className="flex flex-col items-center mb-8">
          <div className="bg-brand-600 p-3 rounded-xl shadow-lg shadow-brand-500/20 mb-4">
             <GraduationCap className="h-8 w-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">Academia Shield</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2">Secure Academic Integrity Portal</p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3 animate-fade-in">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
          </div>
        )}

        <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); handleLogin('admin'); }}>
          <Input 
            label="Full Name"
            type="text" 
            placeholder="e.g. Dr. Alan Turing"
            icon={<User size={16} />}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input 
            label="Institutional Email"
            type="email" 
            placeholder="admin@university.edu / student@student.university.edu"
            icon={<Mail size={16} />}
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (error) setError(null);
            }}
          />
          <Input 
            label="Password"
            type="password" 
            placeholder="••••••••"
            icon={<Lock size={16} />}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          
          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center text-slate-600 dark:text-slate-300 cursor-pointer">
              <input type="checkbox" className="rounded border-slate-300 text-brand-600 focus:ring-brand-500 mr-2" />
              Remember me
            </label>
            <a href="#" className="text-brand-600 hover:text-brand-500 font-medium">Forgot Password?</a>
          </div>

          <div className="space-y-3 pt-2">
            <Button 
              type="submit" 
              className="w-full" 
              size="lg" 
              disabled={isLoading}
              icon={isLoading ? null : <ArrowRight size={18} />}
            >
              {isLoading ? 'Authenticating...' : 'Login as Professor / Admin'}
            </Button>
            
            <Button 
              type="button" 
              variant="secondary" 
              className="w-full"
              onClick={() => handleLogin('student')}
              disabled={isLoading}
            >
              Login as Student
            </Button>
          </div>
        </form>

        <p className="mt-8 text-center text-xs text-slate-400">
          Protected by Academia Shield Security Systems v2.4
          <br/>Authorized personnel only.
        </p>
      </div>
    </div>
  );
};
