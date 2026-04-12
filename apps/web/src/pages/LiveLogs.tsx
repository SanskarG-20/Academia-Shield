import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Activity, Wifi, ShieldAlert, CheckCircle } from 'lucide-react';

interface LiveLogEntry {
    id: string;
    studentName: string;
    action: string;
    website: string;
    timestamp: Date;
    status: 'Allowed' | 'Blocked';
    engagement: number;
}

const SAMPLE_NAMES = ['Alice Chen', 'Bob Smith', 'Charlie Day', 'Diana Prince', 'Ethan Hunt', 'Fiona Gallagher'];
const SAMPLE_SITES = ['github.com', 'stackoverflow.com', 'canvas.instructure.com', 'youtube.com', 'chatgpt.com', 'docs.python.org'];

export const LiveLogs: React.FC = () => {
  const [logs, setLogs] = useState<LiveLogEntry[]>([]);

  // Simulate real-time data stream
  useEffect(() => {
    const interval = setInterval(() => {
        const randomName = SAMPLE_NAMES[Math.floor(Math.random() * SAMPLE_NAMES.length)];
        const randomSite = SAMPLE_SITES[Math.floor(Math.random() * SAMPLE_SITES.length)];
        const isBlocked = ['youtube.com', 'chatgpt.com'].includes(randomSite);
        
        const newLog: LiveLogEntry = {
            id: Math.random().toString(36).substr(2, 9),
            studentName: randomName,
            action: isBlocked ? 'Attempted Access' : 'Accessed Resource',
            website: randomSite,
            timestamp: new Date(),
            status: isBlocked ? 'Blocked' : 'Allowed',
            engagement: Math.floor(Math.random() * 30) + 70 // 70-100
        };

        setLogs(prev => [newLog, ...prev].slice(0, 20)); // Keep last 20 logs
    }, 2000); // New log every 2 seconds

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
                    <Wifi className="text-red-500 animate-pulse" /> Live Session Monitor
                </h1>
                <p className="text-slate-500 dark:text-slate-400">Real-time telemetry from active student sessions.</p>
            </div>
            <div className="flex gap-2 text-sm">
                <span className="px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full border border-emerald-100 flex items-center gap-1">
                    <Activity size={14} /> Monitoring Active
                </span>
            </div>
        </div>

        <Card noPadding>
            <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
                        <tr>
                            <th className="px-6 py-3 font-medium text-slate-500">Timestamp</th>
                            <th className="px-6 py-3 font-medium text-slate-500">Student</th>
                            <th className="px-6 py-3 font-medium text-slate-500">Activity</th>
                            <th className="px-6 py-3 font-medium text-slate-500">Status</th>
                            <th className="px-6 py-3 font-medium text-slate-500">Engagement</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {logs.map(log => (
                            <tr key={log.id} className="animate-fade-in">
                                <td className="px-6 py-3 font-mono text-slate-500 text-xs">
                                    {log.timestamp.toLocaleTimeString()}
                                </td>
                                <td className="px-6 py-3 font-medium text-slate-900 dark:text-white">
                                    {log.studentName}
                                </td>
                                <td className="px-6 py-3 text-slate-600 dark:text-slate-400">
                                    {log.action}: <span className="font-mono text-xs bg-slate-100 dark:bg-slate-700 px-1 rounded">{log.website}</span>
                                </td>
                                <td className="px-6 py-3">
                                    {log.status === 'Allowed' ? (
                                        <span className="flex items-center gap-1 text-emerald-600 text-xs font-medium">
                                            <CheckCircle size={14} /> Allowed
                                        </span>
                                    ) : (
                                        <span className="flex items-center gap-1 text-red-600 text-xs font-medium">
                                            <ShieldAlert size={14} /> Blocked
                                        </span>
                                    )}
                                </td>
                                <td className="px-6 py-3">
                                    <div className="w-24 bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                        <div 
                                            className={`h-full ${log.engagement > 85 ? 'bg-emerald-500' : 'bg-amber-500'}`} 
                                            style={{ width: `${log.engagement}%` }}
                                        />
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {logs.length === 0 && (
                            <tr>
                                <td colSpan={5} className="px-6 py-8 text-center text-slate-400 italic">
                                    Waiting for live data...
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    </div>
  );
};