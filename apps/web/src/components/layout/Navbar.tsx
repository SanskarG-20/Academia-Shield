import React from 'react';
import { Bell, Search, User, PanelLeftOpen, PanelLeftClose, GraduationCap } from 'lucide-react';

interface NavbarProps {
  toggleSidebar?: () => void;
  isSidebarOpen?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ toggleSidebar, isSidebarOpen = true }) => {
  const userName = localStorage.getItem('userName') || 'User';
  const role = localStorage.getItem('userRole');
  
  // Determine display role dynamically
  let displayRole = 'User';
  if (role === 'student') {
      displayRole = 'Student';
  } else if (role === 'admin' || role === 'professor') {
      const profProfileStr = localStorage.getItem('professorProfile');
      if (profProfileStr) {
          try {
             const prof = JSON.parse(profProfileStr);
             // Use designation if available
             displayRole = prof.designation || 'Faculty Admin';
          } catch (e) {
             displayRole = 'Faculty Admin';
          }
      } else {
          displayRole = 'Faculty Admin';
      }
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-6">
      {/* Left Actions & Logo & Search Bar */}
      <div className="flex w-full max-w-xl items-center gap-4">
        {toggleSidebar && (
          <button
            onClick={toggleSidebar}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors"
            title="Toggle Sidebar"
          >
            {isSidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
          </button>
        )}
        
        {/* Logo (Visible only when sidebar is closed) */}
        {!isSidebarOpen && (
          <div className="hidden sm:flex items-center gap-2 text-brand-600 dark:text-brand-400 mr-2 transition-all">
            <GraduationCap size={24} />
            <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
              Academia<span className="text-brand-500">Shield</span>
            </span>
          </div>
        )}

        <div className="relative w-full max-w-md">
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

        </button>
        
        <div className="flex items-center gap-3 border-l border-slate-200 dark:border-slate-700 pl-4">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-medium text-slate-900 dark:text-white">{userName}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">{displayRole}</p>
          </div>
          <div className="h-9 w-9 rounded-full bg-brand-100 dark:bg-brand-900 flex items-center justify-center text-brand-600 dark:text-brand-300 border border-brand-200 dark:border-brand-700">
            <User size={18} />
          </div>
        </div>
      </div>
    </header>
  );
};