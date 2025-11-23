import React from 'react';
import { MOCK_LOGS } from '../constants';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { Search, AlertTriangle, CheckCircle } from 'lucide-react';

export const Logs: React.FC = () => {
  const engagementData = [
    { name: 'High Engagement', value: 65, color: '#10b981' }, // emerald-500
    { name: 'Moderate', value: 25, color: '#f59e0b' }, // amber-500
    { name: 'Low/Distracted', value: 10, color: '#ef4444' }, // red-500
  ];

  const usageData = [
    { site: 'canvas', time: 120 },
    { site: 'wiki', time: 45 },
    { site: 'github', time: 90 },
    { site: 'youtube', time: 15 }, // potentially non-whitelisted depending on context
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Activity Logs & Analytics</h1>
        <p className="text-slate-500 dark:text-slate-400">Deep dive into student behavior and session security.</p>
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

        <Card title="Avg Time Spent on Resources (mins)">
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

      {/* Logs Table */}
      <Card noPadding title="Detailed Activity Log" action={<div className="w-64"><Input placeholder="Search logs..." icon={<Search size={14}/>} className="mb-0 h-8 text-xs"/></div>}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-xs uppercase text-slate-500 font-medium">
              <tr>
                <th className="px-6 py-3">Timestamp</th>
                <th className="px-6 py-3">Student</th>
                <th className="px-6 py-3">Resource</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Engagement</th>
                <th className="px-6 py-3">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700 bg-white dark:bg-slate-900">
              {MOCK_LOGS.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors duration-150">
                  <td className="px-6 py-3 text-slate-500 whitespace-nowrap">
                    {new Date(log.timestamp).toLocaleTimeString()} <span className="text-xs text-slate-400 block">{new Date(log.timestamp).toLocaleDateString()}</span>
                  </td>
                  <td className="px-6 py-3 font-medium text-slate-900 dark:text-white">
                    {log.studentName} <span className="text-xs text-slate-400 font-normal block">ID: {log.studentId}</span>
                  </td>
                  <td className="px-6 py-3 text-slate-600 dark:text-slate-300">
                    <span className="font-mono bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-xs">{log.resourceAccessed}</span>
                  </td>
                  <td className="px-6 py-3">
                    {log.isWhitelisted ? (
                      <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                        <CheckCircle size={14} /> Allowed
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400 text-xs font-medium">
                        <AlertTriangle size={14} /> Violation
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3">
                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 max-w-[100px] mb-1">
                      <div 
                        className={`h-1.5 rounded-full ${log.engagementScore > 80 ? 'bg-emerald-500' : log.engagementScore > 50 ? 'bg-yellow-500' : 'bg-red-500'}`} 
                        style={{ width: `${log.engagementScore}%`, transition: 'width 1s ease-out' }}
                      ></div>
                    </div>
                    <span className="text-xs text-slate-500">{log.engagementScore}%</span>
                  </td>
                  <td className="px-6 py-3 text-slate-500 text-xs">
                    {Math.floor(log.timeSpentSeconds / 60)}m {log.timeSpentSeconds % 60}s
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};