import React from 'react';
import { useNavigate } from 'react-router-dom';
import { GraduationCap, School, ChevronRight, ShieldCheck, Download } from 'lucide-react';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { BlurText } from '../components/ui/BlurText';

export const SelectUser: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden font-sans">
      {/* Animated Background Grid */}
      <div className="absolute inset-0 z-0">
         <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
         <div className="absolute left-0 right-0 top-0 -z-10 m-auto h-[310px] w-[310px] rounded-full bg-brand-500 opacity-20 blur-[100px]"></div>
         <div className="absolute right-0 bottom-0 -z-10 m-auto h-[310px] w-[310px] rounded-full bg-blue-600 opacity-20 blur-[100px]"></div>
      </div>

      <div className="relative z-10 max-w-4xl w-full px-6 py-12 flex flex-col items-center">
        {/* Header */}
        <div className="mb-12 text-center flex flex-col items-center">
          <div className="inline-flex items-center justify-center p-3 bg-white dark:bg-slate-800 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-none mb-6 ring-1 ring-slate-100 dark:ring-slate-700 animate-bounce-slow">
            <ShieldCheck className="w-8 h-8 text-brand-600 dark:text-brand-400" />
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-slate-900 dark:text-white tracking-tight mb-4 flex gap-2">
            <BlurText text="Academia" delay={0.1} />
            <BlurText text="Shield" delay={0.3} className="text-brand-600 dark:text-brand-400" />
          </h1>
          <p className="text-lg text-slate-500 dark:text-slate-400 max-w-lg mx-auto leading-relaxed animate-fade-in opacity-0" style={{animationDelay: '0.6s', animationFillMode: 'forwards'}}>
            Enterprise-grade academic integrity portal. <br className="hidden sm:block"/>Please select your role to continue.
          </p>
        </div>

        {/* Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-3xl">
          {/* Student Card */}
          <SpotlightCard 
            className="cursor-pointer group"
            onClick={() => navigate('/login/student')}
          >
            <div className="flex flex-col items-center p-8 text-center h-full">
              <div className="w-20 h-20 rounded-full bg-brand-50 dark:bg-brand-900/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                <GraduationCap className="w-10 h-10 text-brand-600 dark:text-brand-400" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Student</h2>
              <p className="text-slate-500 dark:text-slate-400 mb-8 text-sm">
                Access your exams, view active sessions, and track your attendance records.
              </p>
              <div className="mt-auto flex items-center font-semibold text-brand-600 dark:text-brand-400 group-hover:translate-x-1 transition-transform">
                Login with SAP ID <ChevronRight className="ml-1 w-4 h-4" />
              </div>
            </div>
          </SpotlightCard>

          {/* Professor Card */}
          <SpotlightCard 
            className="cursor-pointer group"
            onClick={() => navigate('/login/professor')}
            spotlightColor="rgba(37, 99, 235, 0.15)" // Blue-600 spotlight
          >
            <div className="flex flex-col items-center p-8 text-center h-full">
              <div className="w-20 h-20 rounded-full bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                <School className="w-10 h-10 text-blue-600 dark:text-blue-400" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Professor / Admin</h2>
              <p className="text-slate-500 dark:text-slate-400 mb-8 text-sm">
                Manage courses, monitor live sessions, configure rules, and view analytics.
              </p>
              <div className="mt-auto flex items-center font-semibold text-blue-600 dark:text-blue-400 group-hover:translate-x-1 transition-transform">
                Login with Credentials <ChevronRight className="ml-1 w-4 h-4" />
              </div>
            </div>
          </SpotlightCard>
        </div>

        {!window.academiaDesktop && <div className="mt-8 w-full max-w-3xl rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Student device agent</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Download for Windows, then sign in to get a one-time device enrollment code. Installation and hosts-file access require administrator rights.
            </p>
          </div>
          <a
            href="https://github.com/SanskarG-20/Academia-Shield/releases/download/nightly/AcademiaShieldSetup.exe"
            className="shrink-0 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-slate-800 transition-colors"
          >
            <Download size={16} aria-hidden="true" />
            Download Windows app (.exe)
          </a>
        </div>}

        {/* Footer */}
        <div className="mt-16 text-center">
          <p className="text-xs text-slate-400 font-medium tracking-wide uppercase animate-pulse">
            Protected by Academia Shield v2.4
          </p>
        </div>
      </div>
    </div>
  );
};
