import React from 'react';
import { Bell, Search, User } from 'lucide-react';

export const Navbar: React.FC = () => {
  const userName = localStorage.getItem('userName') || 'Dr. A. Turing';
  const userRole = localStorage.getItem('userRole') === 'student' ? 'Student' : 'Senior Admin';

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-6">
      {/* Search Bar */}
      <div className="flex w-full max-w-md items-center">
        <div className="relative w-full">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
            <Search size={18} />
          </span>
          <input
            type="text"
            placeholder="Search sessions, students, or logs..."
            className="w-full rounded-full border-none bg-slate-100 dark:bg-slate-800 py-2 pl-10 pr-4 text-sm text-slate-900 dark:text-white focus:ring-2 focus:ring-brand-500 placeholder-slate-500"
          />
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-4">
        <button className="relative rounded-full p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors">
          <Bell size={20} />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white dark:ring-slate-900"></span>
        </button>
        
        <div className="flex items-center gap-3 border-l border-slate-200 dark:border-slate-700 pl-4">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-medium text-slate-900 dark:text-white">{userName}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">{userRole}</p>
          </div>
          <div className="h-9 w-9 rounded-full bg-brand-100 dark:bg-brand-900 flex items-center justify-center text-brand-600 dark:text-brand-300 border border-brand-200 dark:border-brand-700">
            <User size={18} />
          </div>
        </div>
      </div>
    </header>
  );
};