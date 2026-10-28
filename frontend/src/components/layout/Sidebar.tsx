import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  CalendarDays, 
  ShieldCheck, 
  Shield,
  Activity, 
  Settings, 
  LogOut,
  GraduationCap,
  Users,
  Wifi,
  BookOpen,
  Sparkles,
  BarChart3
} from 'lucide-react';
import { logout } from '../../lib/api';

export const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const userRole = localStorage.getItem('userRole');
  const isStudent = userRole === 'student';

  const handleLogout = async () => {
    await logout();
    navigate('/auth', { replace: true });
  };

  const navItems = isStudent
    ? [
        { icon: <Users size={20} />, label: 'My Batches', path: '/student/batches' },
        { icon: <BookOpen size={20} />, label: 'My Sessions', path: '/student/session' },
        { icon: <Settings size={20} />, label: 'Settings', path: '/settings' },
      ]
    : [
        { icon: <LayoutDashboard size={20} />, label: 'Dashboard', path: '/dashboard' },
        { icon: <CalendarDays size={20} />, label: 'Sessions', path: '/sessions' },
        { icon: <Users size={20} />, label: 'Batches', path: '/batches' },
        { icon: <BarChart3 size={20} />, label: 'Student Engagement', path: '/professor/student-engagement' },
        { icon: <Wifi size={20} />, label: 'Live Monitor', path: '/logs/live' },
        { icon: <ShieldCheck size={20} />, label: 'Rules & Policy', path: '/rules' },
        { icon: <Activity size={20} />, label: 'Logs & Analytics', path: '/logs' },
        { icon: <Shield size={20} />, label: 'Admin Governance', path: '/admin' },
        { icon: <Settings size={20} />, label: 'Settings', path: '/settings' },
      ];

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-slate-800 bg-slate-900 transition-transform">
      <div className="flex h-16 items-center border-b border-slate-800 px-6">
        <div className="flex items-center gap-2 text-indigo-400">
          <Shield size={26} className="text-indigo-400 fill-indigo-400/20" />
          <span className="text-lg font-bold tracking-tight text-white">
            Academia<span className="text-indigo-400">Shield</span>
          </span>
        </div>
      </div>

      <div className="h-[calc(100vh-4rem)] overflow-y-auto px-3 py-4 flex flex-col justify-between">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-all
                   ${isActive 
                     ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30' 
                     : 'text-slate-400 hover:bg-slate-800/60 hover:text-white'
                   }`
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="pt-4 border-t border-slate-800/80">
          <button 
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium text-rose-400 hover:bg-rose-500/10 hover:text-rose-300 transition-colors border border-transparent hover:border-rose-500/20"
          >
            <LogOut size={20} />
            Sign Out
          </button>
        </div>
      </div>
    </aside>
  );
};