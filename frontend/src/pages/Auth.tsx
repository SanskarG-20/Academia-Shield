import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ShieldCheck,
  UserCheck,
  GraduationCap,
  Briefcase,
  Lock,
  Mail,
  User,
  Building,
  IdCard,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  KeyRound
} from 'lucide-react';
import { login, registerStudent, registerProfessor, forgotPassword } from '../lib/api';

export const Auth: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  // Role state: 'student' or 'professor'
  const [role, setRole] = useState<'student' | 'professor'>('student');
  // Mode state: 'login' or 'register'
  const [mode, setMode] = useState<'login' | 'register'>('login');

  // Form states
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [institutionalId, setInstitutionalId] = useState('');
  const [department, setDepartment] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [acceptPolicy, setAcceptPolicy] = useState(false);

  // UI helpers
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Password reset modal
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotMsg, setForgotMsg] = useState('');

  const fromPath = (location.state as any)?.from?.pathname;

  React.useEffect(() => {
    if (location.pathname.includes('professor')) {
      setRole('professor');
    } else if (location.pathname.includes('student')) {
      setRole('student');
    }

    if (localStorage.getItem('isAuthenticated') === 'true') {
      const userRole = localStorage.getItem('userRole');
      const dest = fromPath || (userRole === 'student' ? '/student/session' : '/dashboard');
      navigate(dest, { replace: true });
    }
  }, [location.pathname, navigate, fromPath]);

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');
    setIsLoading(true);

    try {
      if (mode === 'login') {
        if (!email.trim() || !password) {
          throw new Error('Please fill in both institutional credentials and password.');
        }
        const data = await login(email.trim(), password);

        // Verify authenticated user role matches intent
        if (data.user.role !== role) {
          throw new Error(
            `Account role mismatch. This account is registered as a ${data.user.role}. Please switch to the ${data.user.role} role tab.`
          );
        }

        const dest = fromPath || (role === 'student' ? '/student/session' : '/dashboard');
        navigate(dest, { replace: true });
      } else {
        // Registration validations
        if (!fullName.trim() || !email.trim() || !institutionalId.trim() || !department.trim()) {
          throw new Error('All registration fields are required.');
        }
        if (password.length < 8) {
          throw new Error('Password must be at least 8 characters long.');
        }
        if (password !== confirmPassword) {
          throw new Error('Password and Confirm Password do not match.');
        }
        if (!acceptPolicy) {
          throw new Error('You must accept the academic-use and privacy notice to register.');
        }

        if (role === 'student') {
          await registerStudent({
            full_name: fullName.trim(),
            email: email.trim(),
            student_id: institutionalId.trim(),
            department: department.trim(),
            password,
            confirm_password: confirmPassword,
            accept_policy: acceptPolicy
          });
          navigate('/student/session', { replace: true });
        } else {
          await registerProfessor({
            full_name: fullName.trim(),
            email: email.trim(),
            employee_id: institutionalId.trim(),
            department: department.trim(),
            password,
            confirm_password: confirmPassword,
            accept_policy: acceptPolicy
          });
          navigate('/dashboard', { replace: true });
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'An unexpected authentication error occurred.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotMsg('');
    setForgotLoading(true);
    try {
      if (!forgotEmail.trim()) {
        throw new Error('Please enter your institutional email.');
      }
      const res = await forgotPassword(forgotEmail.trim());
      setForgotMsg(res.message);
    } catch (err: any) {
      setForgotMsg(err.message || 'Failed to submit reset request.');
    } finally {
      setForgotLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative overflow-hidden font-sans">
      {/* Dynamic visual ambient glows */}
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-indigo-600/15 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-sky-600/15 rounded-full blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center relative z-10">
        <div className="inline-flex items-center gap-3 px-4 py-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full mb-6 text-indigo-400 font-mono text-xs tracking-wider uppercase shadow-inner">
          <ShieldCheck className="w-4 h-4 text-indigo-400" />
          <span>Academia Shield Governance</span>
        </div>

        <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
          {mode === 'login' ? 'Sign in to Academia Shield' : 'Create Institutional Account'}
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Centralized policy enforcement & real-time session monitoring platform
        </p>
      </div>

      {/* Auth Container Card */}
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-xl relative z-10">
        <div className="bg-slate-900/90 backdrop-blur-xl border border-slate-800 py-8 px-6 shadow-2xl rounded-2xl sm:px-10">
          {/* Role Selector Tabs */}
          <div className="grid grid-cols-2 gap-2 p-1.5 bg-slate-950/80 rounded-xl border border-slate-800/80 mb-8">
            <button
              type="button"
              onClick={() => {
                setRole('student');
                setErrorMessage('');
              }}
              className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg font-medium text-sm transition-all duration-200 ${
                role === 'student'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/25 border border-indigo-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
              }`}
            >
              <GraduationCap className="w-4 h-4" />
              <span>I am a Student</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setRole('professor');
                setErrorMessage('');
              }}
              className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg font-medium text-sm transition-all duration-200 ${
                role === 'professor'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/25 border border-indigo-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
              }`}
            >
              <Briefcase className="w-4 h-4" />
              <span>I am a Professor</span>
            </button>
          </div>

          {/* Mode Switcher Header */}
          <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-6">
            <div>
              <h2 className="text-lg font-semibold text-slate-100 capitalize">
                {role} {mode === 'login' ? 'Sign In' : 'Registration'}
              </h2>
              <p className="text-xs text-slate-400">
                {role === 'student'
                  ? 'Access your active classes, assigned work, and local agent status'
                  : 'Manage class batches, session policies, and live student telemetry'}
              </p>
            </div>

            <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => {
                  setMode('login');
                  setErrorMessage('');
                }}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                  mode === 'login' ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode('register');
                  setErrorMessage('');
                }}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                  mode === 'register' ? 'bg-slate-800 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Register
              </button>
            </div>
          </div>

          {/* Inline Error Announcement */}
          {errorMessage && (
            <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start gap-3 text-rose-400 text-sm animate-in fade-in slide-in-from-top-2">
              <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
              <span className="leading-relaxed">{errorMessage}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleAuthSubmit} className="space-y-5">
            {mode === 'register' && (
              <>
                {/* Full Name */}
                <div>
                  <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider mb-1.5">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder={role === 'student' ? 'e.g. Jane Doe' : 'e.g. Dr. Alan Turing'}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                    />
                  </div>
                </div>

                {/* Institutional ID */}
                <div>
                  <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider mb-1.5">
                    {role === 'student' ? 'Student / Roll ID' : 'Employee / Faculty ID'}
                  </label>
                  <div className="relative">
                    <IdCard className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      required
                      value={institutionalId}
                      onChange={(e) => setInstitutionalId(e.target.value)}
                      placeholder={role === 'student' ? 'e.g. 60001234567' : 'e.g. FAC-99021'}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                    />
                  </div>
                </div>

                {/* Department */}
                <div>
                  <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider mb-1.5">
                    Department / Program
                  </label>
                  <div className="relative">
                    <Building className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      required
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                      placeholder="e.g. Computer Engineering"
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Email Field */}
            <div>
              <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider mb-1.5">
                {mode === 'login' ? 'Institutional Email or ID' : 'Institutional Email'}
              </label>
              <div className="relative">
                <Mail className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type={mode === 'login' ? 'text' : 'email'}
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={
                    role === 'student'
                      ? 'student@university.edu or Student ID'
                      : 'professor@university.edu or Employee ID'
                  }
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                />
              </div>
            </div>

            {/* Password Field */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Password
                </label>
                {mode === 'login' && (
                  <button
                    type="button"
                    onClick={() => {
                      setShowForgotModal(true);
                      setForgotMsg('');
                    }}
                    className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    Forgot Password?
                  </button>
                )}
              </div>
              <div className="relative">
                <Lock className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-12 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            {/* Confirm Password (Registration) */}
            {mode === 'register' && (
              <div>
                <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider mb-1.5">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="w-5 h-5 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl py-3 pl-11 pr-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                  />
                </div>
              </div>
            )}

            {/* Mandatory Policy Acceptance */}
            {mode === 'register' && (
              <div className="p-4 bg-slate-950/70 border border-slate-800/80 rounded-xl">
                <label className="flex items-start gap-3 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={acceptPolicy}
                    onChange={(e) => setAcceptPolicy(e.target.checked)}
                    className="mt-1 w-4 h-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-950"
                  />
                  <span className="text-xs text-slate-300 leading-relaxed">
                    I accept the <strong className="text-slate-100">Academic Governance & Privacy Notice</strong>. I understand that desktop activity monitoring <strong>only applies while a professor-authorized session is active</strong>.
                  </span>
                </label>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm rounded-xl transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/25 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <span>{mode === 'login' ? `Sign In as ${role === 'student' ? 'Student' : 'Professor'}` : `Create ${role === 'student' ? 'Student' : 'Professor'} Account`}</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Forgot Password Modal */}
      {showForgotModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl relative animate-in zoom-in-95">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2.5 bg-indigo-500/10 text-indigo-400 rounded-xl border border-indigo-500/20">
                <KeyRound className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-100">Reset Password</h3>
                <p className="text-xs text-slate-400">Request password reset link via institutional email</p>
              </div>
            </div>

            {forgotMsg && (
              <div className="mb-4 p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-300 text-xs">
                {forgotMsg}
              </div>
            )}

            <form onSubmit={handleForgotSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 uppercase tracking-wider mb-1">
                  Institutional Email
                </label>
                <input
                  type="email"
                  required
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  placeholder="your.email@university.edu"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl py-2.5 px-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForgotModal(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={forgotLoading}
                  className="px-4 py-2 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-all shadow-md shadow-indigo-600/20"
                >
                  {forgotLoading ? 'Submitting...' : 'Send Reset Link'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
