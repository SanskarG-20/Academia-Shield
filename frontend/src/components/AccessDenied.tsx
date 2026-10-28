import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert, ArrowLeft, LayoutDashboard } from 'lucide-react';

interface AccessDeniedProps {
  requiredRole: 'student' | 'professor' | string;
}

export const AccessDenied: React.FC<AccessDeniedProps> = ({ requiredRole }) => {
  const navigate = useNavigate();
  const currentRole = localStorage.getItem('userRole') || 'unauthenticated';

  const dashboardPath = currentRole === 'student' ? '/student/session' : '/dashboard';
  const roleTitle = requiredRole === 'professor' ? 'Professor Command Center' : (requiredRole === 'student' ? 'Student Portal' : requiredRole);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center shadow-2xl relative overflow-hidden">
        {/* Glow backdrop */}
        <div className="absolute -top-24 -left-24 w-48 h-48 bg-rose-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl" />

        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/20 mb-6">
          <ShieldAlert className="w-8 h-8" />
        </div>

        <span className="inline-block px-3 py-1 bg-rose-500/10 text-rose-400 text-xs font-mono font-semibold rounded-full border border-rose-500/20 mb-3">
          403 FORBIDDEN
        </span>

        <h1 className="text-2xl font-bold text-slate-100 mb-2">
          Access Restricted
        </h1>

        <p className="text-slate-400 text-sm mb-6 leading-relaxed">
          This route requires <strong className="text-slate-200 capitalize">{roleTitle}</strong> permissions. Your account is currently authenticated as a <strong className="text-indigo-400 capitalize">{currentRole}</strong>.
        </p>

        <div className="space-y-3">
          <button
            onClick={() => navigate(dashboardPath)}
            className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20"
          >
            <LayoutDashboard className="w-4 h-4" />
            Return to My Authorized Dashboard
          </button>

          <button
            onClick={() => navigate(-1)}
            className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-xl transition-all duration-200 flex items-center justify-center gap-2 border border-slate-700"
          >
            <ArrowLeft className="w-4 h-4" />
            Go Back
          </button>
        </div>
      </div>
    </div>
  );
};
