import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from 'recharts';
import { Card } from '../components/ui/Card';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { Button } from '../components/ui/Button';
import { Users, ShieldAlert, Activity, Calendar, Plus, Wifi, ChevronRight, CheckCircle, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

// Mock chart data
const activityData = [
  { time: '08:00', students: 120 },
  { time: '10:00', students: 450 },
  { time: '12:00', students: 300 },
  { time: '14:00', students: 800 },
  { time: '16:00', students: 600 },
  { time: '18:00', students: 200 },
];

const sessionData = [
  { name: 'Mon', Active: 4, Completed: 10 },
  { name: 'Tue', Active: 7, Completed: 8 },
  { name: 'Wed', Active: 5, Completed: 12 },
  { name: 'Thu', Active: 8, Completed: 9 },
  { name: 'Fri', Active: 6, Completed: 11 },
];

const StatCard = ({ title, value, trend, icon, color }: any) => (
  <SpotlightCard className="hover:-translate-y-1">
    <div className="p-6 flex items-start justify-between h-full">
      <div>
        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
        <h3 className="text-3xl font-bold text-slate-900 dark:text-white mt-2">{value}</h3>
        <p className={`text-xs font-medium mt-2 ${trend.includes('+') || trend.includes('Good') || trend === 'Live' ? 'text-emerald-600' : 'text-red-600'}`}>
          {trend} <span className="text-slate-400 font-normal">vs last week</span>
        </p>
      </div>
      <div className={`p-3 rounded-lg ${color} text-white shadow-lg shadow-${color.split('-')[1]}-500/30`}>
        {icon}
      </div>
    </div>
  </SpotlightCard>
);

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const userRole = localStorage.getItem('userRole');
  const userName = localStorage.getItem('userName') || (userRole === 'student' ? 'Student' : 'Professor');
  const isStudent = userRole === 'student';

  // Mock Live Sessions Data
  const [liveSessions, setLiveSessions] = useState([
    { id: 's1', title: 'Midterm Examination', course: 'CS 302', totalStudents: 120, currentEngagement: 96 },
    { id: 's2', title: 'Intro to ML Lecture', course: 'CS 405', totalStudents: 85, currentEngagement: 82 },
    { id: 's3', title: 'Data Structures Lab', course: 'CS 201', totalStudents: 42, currentEngagement: 65 },
  ]);

  // Simulate real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      setLiveSessions(prev => prev.map(session => ({
        ...session,
        currentEngagement: Math.min(100, Math.max(0, session.currentEngagement + (Math.random() * 4 - 2)))
      })));
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Dashboard Overview</h1>
          <p className="text-slate-500 dark:text-slate-400">
            {isStudent 
              ? 'Welcome back. Check your upcoming schedule and compliance status.' 
              : `Welcome back, ${userName}. Here's what's happening today.`}
          </p>
        </div>
        {!isStudent && (
          <Button icon={<Plus size={18} />} onClick={() => navigate('/sessions')}>Create Session</Button>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          title={isStudent ? "Enrolled Sessions" : "Active Sessions"} 
          value={isStudent ? "4" : "12"} 
          trend={isStudent ? "Live" : "+2"} 
          icon={<Activity size={24} />} 
          color="bg-blue-500" 
        />
        
        {isStudent ? (
          <>
            <StatCard 
              title="My Attendance" 
              value="98%" 
              trend="+2%" 
              icon={<Users size={24} />} 
              color="bg-emerald-500" 
            />
            <StatCard 
              title="Upcoming Exams" 
              value="2" 
              trend="Next: Mon" 
              icon={<Calendar size={24} />} 
              color="bg-indigo-500" 
            />
            <StatCard 
              title="System Status" 
              value="Ready" 
              trend="Good" 
              icon={<ShieldAlert size={24} />} 
              color="bg-teal-500" 
            />
          </>
        ) : (
          <>
            <StatCard 
              title="Total Students" 
              value="1,284" 
              trend="+5%" 
              icon={<Users size={24} />} 
              color="bg-indigo-500" 
            />
            <StatCard 
              title="Anomalies Detected" 
              value="3" 
              trend="-1" 
              icon={<ShieldAlert size={24} />} 
              color="bg-red-500" 
            />
            <StatCard 
              title="Upcoming Exams" 
              value="8" 
              trend="+4" 
              icon={<Calendar size={24} />} 
              color="bg-teal-500" 
            />
          </>
        )}
      </div>

      {/* PROFESSOR VIEW ONLY: Charts and Live Monitoring */}
      {!isStudent && (
        <>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <Wifi className="text-red-500 animate-pulse" size={20} />
                Live Session Monitoring
              </h2>
              <Button variant="ghost" size="sm" className="text-sm" onClick={() => navigate('/sessions')}>View All <ChevronRight size={16} /></Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {liveSessions.map(session => (
                <Card key={session.id} noPadding className="relative overflow-hidden border-l-4 border-l-brand-500">
                  <div className="p-5">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h3 className="font-semibold text-slate-900 dark:text-white truncate pr-2">{session.title}</h3>
                        <p className="text-xs text-slate-500 dark:text-slate-400">{session.course}</p>
                      </div>
                      <span className="px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-xs font-bold rounded animate-pulse">LIVE</span>
                    </div>
                    
                    <div className="mt-4 space-y-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-500">Active Students</span>
                        <span className="font-medium text-slate-900 dark:text-white">{session.totalStudents}</span>
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-slate-500">Engagement Score</span>
                          <span className={`font-bold ${session.currentEngagement > 85 ? 'text-emerald-500' : session.currentEngagement > 60 ? 'text-yellow-500' : 'text-red-500'}`}>
                            {session.currentEngagement.toFixed(1)}%
                          </span>
                        </div>
                        <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
                          <div 
                            className={`h-full rounded-full transition-all duration-1000 ease-out ${session.currentEngagement > 85 ? 'bg-emerald-500' : session.currentEngagement > 60 ? 'bg-yellow-500' : 'bg-red-500'}`}
                            style={{ width: `${session.currentEngagement}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card title="Engagement Trends (24h)" className="lg:col-span-2 h-96">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activityData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorStudents" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: '#64748b' }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="students" 
                    stroke="#0ea5e9" 
                    strokeWidth={3} 
                    fillOpacity={1} 
                    fill="url(#colorStudents)" 
                    animationDuration={2000}
                    animationEasing="ease-in-out"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Weekly Session Distribution" className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sessionData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b' }} />
                  <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ borderRadius: '8px' }} />
                  <Legend />
                  <Bar 
                    dataKey="Active" 
                    fill="#0ea5e9" 
                    radius={[4, 4, 0, 0]} 
                    barSize={20} 
                    animationDuration={1500}
                    animationBegin={0}
                    animationEasing="ease-out"
                  />
                  <Bar 
                    dataKey="Completed" 
                    fill="#94a3b8" 
                    radius={[4, 4, 0, 0]} 
                    barSize={20} 
                    animationDuration={1500}
                    animationBegin={300}
                    animationEasing="ease-out"
                  />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </>
      )}

      {/* STUDENT VIEW: Simple List instead of Graphs */}
      {isStudent && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Upcoming Schedule">
            <div className="space-y-4">
               {[1,2].map(i => (
                 <div key={i} className="flex items-center p-3 rounded-lg bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700">
                    <div className="h-10 w-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center mr-4">
                      <Calendar size={20} />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-medium text-slate-900 dark:text-white">Computer Networks Exam</h4>
                      <p className="text-xs text-slate-500">Tomorrow, 10:00 AM</p>
                    </div>
                    <Button size="sm" variant="secondary">Details</Button>
                 </div>
               ))}
            </div>
          </Card>
          
          <Card title="Compliance Status">
            <div className="flex flex-col items-center justify-center h-full py-6">
               <div className="h-16 w-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-4">
                 <CheckCircle size={32} />
               </div>
               <h3 className="text-lg font-semibold text-slate-900 dark:text-white">You are Compliant</h3>
               <p className="text-center text-slate-500 text-sm mt-2 max-w-xs">
                 Your device environment meets all security requirements for upcoming exams.
               </p>
               <Button className="mt-6" variant="outline">Run System Check</Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};