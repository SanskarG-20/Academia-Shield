
import React, { useState } from 'react';
import { MOCK_LOGS } from '../constants';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { Search, AlertTriangle, CheckCircle, Clock, Maximize2, Minimize2, Eye, Layout } from 'lucide-react';

export const Logs: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');

  const engagementData = [
    { name: 'High Engagement', value: 65, color: '#10b981' }, // emerald-500
    { name: 'Moderate', value: 25, color: '#f59e0b' }, // amber-500
    { name: 'Low/Distracted', value: 10, color: '#ef4444' }, // red-500
  ];

  const usageData = [
    { site: 'canvas', time: 120 },
    { site: 'wiki', time: 45 },
    { site: 'github', time: 90 },
    { site: 'youtube', time: 15 },
  ];

  const filteredLogs = MOCK_LOGS.filter(log => 
    log.studentName.toLowerCase().includes(searchTerm.toLowerCase()) || 
    log.resourceAccessed.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Activity Logs & Analytics</h1>
        <p className="text-slate-500 dark:text-slate-400">Deep dive into student behavior, focus metrics, and session security.</p>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Engagement Distribution">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie 
                  data={engagementData} 
                  innerRadius={60} 
                  outerRadius={80} 
                  paddingAngle={5} 
                  dataKey="value"
                  cx="50%"
                  cy="50%"
                  animationDuration={1500}
                  animationEasing="ease-out"
                >
                  {engagementData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend verticalAlign="bottom" height={36}/>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Avg Active Time on Resources (mins)">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={usageData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#e2e8f0" />
                <XAxis type="number" hide />
                <YAxis dataKey="site" type="category" width={80} tick={{fill: '#64748b', fontSize: 12}} />
                <Tooltip cursor={{fill: 'transparent'}} />
                <Bar 
                  dataKey="time" 
                  fill="#6366f1" 
                  radius={[0, 4, 4, 0]} 
                  barSize={20} 
                  animationDuration={1500}
                  animationEasing="ease-out"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Detailed Logs Table */}
      <Card 
        noPadding 
        title="Detailed Activity Log" 
        action={
          <div className="w-64">
            <Input 
              placeholder="Search student or resource..." 
              icon={<Search size={14}/>} 
              className="mb-0 h-9 text-sm"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-xs uppercase text-slate-500 font-medium">
              <tr>
                <th className="px-6 py-3">Timestamp / Student</th>
                <th className="px-6 py-3">Resource / Status</th>
                <th className="px-6 py-3 w-1/4">Time Analysis (Active vs Bg)</th>
                <th className="px-6 py-3">Focus Quality</th>
                <th className="px-6 py-3">Engagement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700 bg-white dark:bg-slate-900">
              {filteredLogs.map((log) => {
                const totalTime = log.activeSeconds + log.backgroundSeconds;
                const activePercent = totalTime > 0 ? (log.activeSeconds / totalTime) * 100 : 0;
                
                return (
                  <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors duration-150 group">
                    <td className="px-6 py-4">
                      <div className="flex flex-col">
                        <span className="font-medium text-slate-900 dark:text-white text-sm">{log.studentName}</span>
                        <span className="text-xs text-slate-400">{new Date(log.timestamp).toLocaleTimeString()} • ID: {log.studentId}</span>
                      </div>
                    </td>
                    
                    <td className="px-6 py-4">
                      <div className="space-y-1">
                        <span className="font-mono bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-xs text-slate-700 dark:text-slate-300">
                          {log.resourceAccessed}
                        </span>
                        <div>
                          {log.isWhitelisted ? (
                            <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                              <CheckCircle size={12} /> Allowed
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400 text-xs font-medium">
                              <AlertTriangle size={12} /> Violation
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Time Analysis Column */}
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1.5">
                         <div className="flex justify-between text-xs mb-1">
                            <span className="text-slate-500 font-medium" title="Total time tab was open">Total: {formatDuration(totalTime)}</span>
                            <span className="text-emerald-600 font-bold" title="Time actually interacting">{Math.round(activePercent)}% Active</span>
                         </div>
                         <div className="flex h-2.5 w-full rounded-full overflow-hidden bg-slate-200 dark:bg-slate-700">
                           <div 
                             className="bg-emerald-500 h-full hover:bg-emerald-400 transition-colors" 
                             style={{ width: `${activePercent}%` }}
                             title={`Active Working: ${formatDuration(log.activeSeconds)}`}
                           />
                           <div 
                             className="bg-slate-300 dark:bg-slate-600 h-full hover:bg-slate-400 transition-colors" 
                             style={{ width: `${100 - activePercent}%` }}
                             title={`Background/Idle: ${formatDuration(log.backgroundSeconds)}`}
                           />
                         </div>
                         <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
                            <span>Active: {formatDuration(log.activeSeconds)}</span>
                            <span>Bg: {formatDuration(log.backgroundSeconds)}</span>
                         </div>
                      </div>
                    </td>

                    {/* Focus Quality Column */}
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                          <Layout size={14} className="text-slate-400"/>
                          <span className="font-medium">{log.windowSwitches} Context Switches</span>
                        </div>
                        {log.windowSwitches > 5 ? (
                           <span className="inline-flex w-fit px-1.5 py-0.5 rounded text-[10px] bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 font-medium">
                             Distracted
                           </span>
                        ) : (
                           <span className="inline-flex w-fit px-1.5 py-0.5 rounded text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 font-medium">
                             Focused
                           </span>
                        )}
                      </div>
                    </td>

                    {/* Engagement Column */}
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="relative w-10 h-10">
                           <svg className="w-full h-full transform -rotate-90">
                             <circle cx="20" cy="20" r="16" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-slate-200 dark:text-slate-700" />
                             <circle 
                               cx="20" 
                               cy="20" 
                               r="16" 
                               stroke="currentColor" 
                               strokeWidth="4" 
                               fill="transparent" 
                               strokeDasharray={100}
                               strokeDashoffset={100 - log.engagementScore}
                               className={`${log.engagementScore > 80 ? 'text-emerald-500' : log.engagementScore > 50 ? 'text-yellow-500' : 'text-red-500'} transition-all duration-1000`} 
                             />
                           </svg>
                           <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-slate-700 dark:text-slate-200">
                             {log.engagementScore}
                           </span>
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
