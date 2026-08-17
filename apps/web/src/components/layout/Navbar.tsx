import React, { useState, useEffect, useRef } from 'react';
import { Bell, Search, User, PanelLeftOpen, PanelLeftClose, GraduationCap, Calendar, Users as UsersIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getSessions, getBatches, getMyBatches } from '../../lib/api';
import { Session, Batch } from '../../types';

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

  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isFocused && sessions.length === 0) {
      getSessions().then(setSessions).catch(() => {});
      if (role === 'student') {
         getMyBatches().then(setBatches).catch(() => {});
      } else {
         getBatches().then(setBatches).catch(() => {});
      }
    }
  }, [isFocused, role, sessions.length]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsFocused(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filteredSessions = searchQuery.trim() ? sessions.filter(s => s.title.toLowerCase().includes(searchQuery.toLowerCase()) || s.course.toLowerCase().includes(searchQuery.toLowerCase())).slice(0, 5) : [];
  const filteredBatches = searchQuery.trim() ? batches.filter(b => b.name.toLowerCase().includes(searchQuery.toLowerCase()) || b.code.toLowerCase().includes(searchQuery.toLowerCase())).slice(0, 5) : [];
  const showDropdown = isFocused && searchQuery.trim().length > 0;

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

        <div className="relative w-full max-w-md" ref={wrapperRef}>
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
            <Search size={18} />
          </span>
          <input
            type="text"
            placeholder="Search sessions or classes..."
            className="w-full rounded-full border-none bg-slate-100 dark:bg-slate-800 py-2 pl-10 pr-4 text-sm text-slate-900 dark:text-white focus:ring-2 focus:ring-brand-500 placeholder-slate-500"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setIsFocused(true)}
          />

          {/* Search Dropdown */}
          {showDropdown && (
            <div className="absolute top-full mt-2 w-full bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50 animate-fade-in max-h-96 overflow-y-auto">
              {filteredSessions.length === 0 && filteredBatches.length === 0 ? (
                <div className="p-4 text-center text-sm text-slate-500 dark:text-slate-400">
                  No results found for "{searchQuery}"
                </div>
              ) : (
                <div className="py-2">
                  {filteredSessions.length > 0 && (
                    <div className="mb-2">
                      <div className="px-4 py-1 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider bg-slate-50 dark:bg-slate-900/50">
                        Sessions
                      </div>
                      {filteredSessions.map(session => (
                        <button
                          key={session._id}
                          onClick={() => {
                            navigate('/sessions');
                            setIsFocused(false);
                            setSearchQuery('');
                          }}
                          className="w-full text-left px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700/50 flex items-center gap-3 transition-colors"
                        >
                          <div className="p-1.5 rounded-md bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                            <Calendar size={16} />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-slate-900 dark:text-white">{session.title}</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400">{session.course}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}

                  {filteredBatches.length > 0 && (
                    <div>
                      <div className="px-4 py-1 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider bg-slate-50 dark:bg-slate-900/50">
                        Classes / Batches
                      </div>
                      {filteredBatches.map(batch => (
                        <button
                          key={batch._id}
                          onClick={() => {
                            navigate(role === 'student' ? '/student/session' : '/batches');
                            setIsFocused(false);
                            setSearchQuery('');
                          }}
                          className="w-full text-left px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700/50 flex items-center gap-3 transition-colors"
                        >
                          <div className="p-1.5 rounded-md bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400">
                            <UsersIcon size={16} />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-slate-900 dark:text-white">{batch.name}</p>
                            <p className="text-xs font-mono text-slate-500 dark:text-slate-400">{batch.code}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
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