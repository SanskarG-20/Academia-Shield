import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  CalendarDays, 
  ShieldCheck, 
  Activity, 
  Settings, 
  LogOut,
  GraduationCap,
  Users,
  Wifi
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const userRole = localStorage.getItem('userRole');
  const isStudent = userRole === 'student';

  const handleLogout = () => {
    localStorage.removeItem('isAuthenticated');
    localStorage.removeItem('userRole');
    localStorage.removeItem('userName');
    localStorage.removeItem('userEmail');
    localStorage.removeItem('studentProfile');
    localStorage.removeItem('professorProfile');
    localStorage.removeItem('tempSapId');
    localStorage.removeItem('tempPhoneNumber');
    navigate('/');
  };

  const navItems = [
    { icon: <LayoutDashboard size={20} />, label: 'Dashboard', path: '/dashboard' },
    { icon: <CalendarDays size={20} />, label: 'Sessions', path: '/sessions' },
    // Only show Classes/Batches for Admins/Professors
    ...(!isStudent ? [
      { icon: <Users size={20} />, label: 'Classes', path: '/batches' },
      { icon: <Wifi size={20} />, label: 'Live Monitor', path: '/logs/live' },
    ] : []),
    // Only show Rules and Logs for admins
    ...(!isStudent ? [
      { icon: <ShieldCheck size={20} />, label: 'Rules & Policy', path: '/rules' },
      { icon: <Activity size={20} />, label: 'Logs & Analytics', path: '/logs' },
    ] : []),
    { icon: <Settings size={20} />, label: 'Settings', path: '/settings' },
  ];

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 transition-transform">
      <div className="flex h-16 items-center border-b border-slate-200 dark:border-slate-700 px-6">
        <div className="flex items-center gap-2 text-brand-600 dark:text-brand-400">
          <GraduationCap size={28} />
          <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
            Academia<span className="text-brand-500">Shield</span>
          </span>
        </div>
      </div>

      <div className="h-[calc(100vh-4rem)] overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
                   ${isActive 
                     ? 'bg-brand-50 text-brand-600 dark:bg-brand-900/20 dark:text-brand-400' 
                     : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white'
                   }`
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="absolute bottom-4 left-0 w-full px-3">
           <button 
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/10 transition-colors"
           >
             <LogOut size={20} />
             Sign Out
           </button>
        </div>
      </div>
    </aside>
  );
};