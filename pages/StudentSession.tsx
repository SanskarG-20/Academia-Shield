import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { SpotlightCard } from '../components/ui/SpotlightCard';
import { Calendar, Clock, ArrowRight, CheckCircle, BookOpen, EyeOff, RefreshCw, Globe, Play, XCircle, MousePointer2 } from 'lucide-react';
import { MOCK_SESSIONS, MOCK_BATCHES, MOCK_RULE_SETS } from '../constants';
import { Session, SessionStatus } from '../types';

export const StudentSession: React.FC = () => {
  const [userName, setUserName] = useState('Student');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [hiddenSessionIds, setHiddenSessionIds] = useState<string[]>([]);
  const [isWorking, setIsWorking] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  
  useEffect(() => {
    setUserName(localStorage.getItem('userName') || 'Student');
    // Load student sessions (Mock logic: all sessions + joined batches)
    const joinedBatches = JSON.parse(localStorage.getItem('joinedBatches') || '[]');
    // Filter sessions belonging to joined batches OR public
    const studentSessions = MOCK_SESSIONS.filter(s => 
        !s.batchIds || s.batchIds.length === 0 || s.batchIds.some(bid => joinedBatches.includes(bid))
    );
    setSessions(studentSessions);
  }, []);

  const getStatusColor = (status: SessionStatus) => {
    switch (status) {
      case SessionStatus.ACTIVE: return 'text-emerald-600 bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800';
      case SessionStatus.UPCOMING: return 'text-blue-600 bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800';
      default: return 'text-slate-600 bg-slate-100 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700';
    }
  };

  const activeSession = sessions.find(s => s.status === SessionStatus.ACTIVE);
  
  // Filter out hidden sessions for the upcoming list
  const upcomingSessions = sessions.filter(s => 
    s.status === SessionStatus.UPCOMING && !hiddenSessionIds.includes(s.id)
  );

  const hideSession = (id: string) => {
    setHiddenSessionIds(prev => [...prev, id]);
  };

  const showAllSessions = () => {
    setHiddenSessionIds([]);
  };

  const handleStartWorking = (sessionId: string) => {
      setCurrentSessionId(sessionId);
      setIsWorking(true);
  };

  const simulateActivity = (activity: string) => {
      // In a real app, this sends a log to backend
      console.log(`[Student Activity] ${activity} in session ${currentSessionId}`);
      alert(`Simulated: Opened ${activity}`);
  };

  if (isWorking && activeSession) {
      const ruleSet = MOCK_RULE_SETS.find(r => r.id === activeSession.ruleSetId);
      return (
          <div className="max-w-5xl mx-auto space-y-6 animate-fade-in">
              <div className="flex items-center justify-between mb-4">
                  <div>
                      <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
                          <span className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"/>
                          Working Mode: {activeSession.title}
                      </h2>
                      <p className="text-slate-500 mt-1">Your activity is being logged.</p>
                  </div>
                  <Button variant="danger" onClick={() => setIsWorking(false)}>Stop Session</Button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <Card title="Allowed Resources" className="md:col-span-2">
                      <div className="space-y-4">
                          <p className="text-sm text-slate-500">
                              Access strictly limited to the following resources. Click to simulate access.
                          </p>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              {ruleSet?.websites.map((site, i) => (
                                  <button 
                                    key={i}
                                    onClick={() => simulateActivity(site)}
                                    className="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-brand-500 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-all text-left group"
                                  >
                                      <div className="p-2 bg-white dark:bg-slate-800 rounded-lg shadow-sm group-hover:scale-110 transition-transform">
                                          <Globe size={20} className="text-brand-600"/>
                                      </div>
                                      <div>
                                          <p className="font-medium text-slate-900 dark:text-white">Open {site}</p>
                                          <p className="text-xs text-slate-500">External Link</p>
                                      </div>
                                  </button>
                              ))}
                              {ruleSet?.applications.map((app, i) => (
                                  <button 
                                    key={i}
                                    onClick={() => simulateActivity(app)}
                                    className="flex items-center gap-3 p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-brand-500 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-all text-left group"
                                  >
                                      <div className="p-2 bg-white dark:bg-slate-800 rounded-lg shadow-sm group-hover:scale-110 transition-transform">
                                          <MousePointer2 size={20} className="text-indigo-600"/>
                                      </div>
                                      <div>
                                          <p className="font-medium text-slate-900 dark:text-white">Launch {app}</p>
                                          <p className="text-xs text-slate-500">Application</p>
                                      </div>
                                  </button>
                              ))}
                          </div>
                      </div>
                  </Card>
                  
                  <div className="space-y-6">
                      <Card title="Session Stats">
                          <div className="space-y-4">
                              <div className="flex justify-between items-center">
                                  <span className="text-sm text-slate-500">Time Elapsed</span>
                                  <span className="font-mono font-bold text-xl">00:12:45</span>
                              </div>
                              <div className="flex justify-between items-center">
                                  <span className="text-sm text-slate-500">Engagement</span>
                                  <span className="font-bold text-emerald-500">98%</span>
                              </div>
                              <div className="pt-4 border-t border-slate-100 dark:border-slate-700">
                                  <p className="text-xs text-slate-400 mb-2">Policy Status</p>
                                  <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 p-2 rounded">
                                      <CheckCircle size={16} /> Compliant
                                  </div>
                              </div>
                          </div>
                      </Card>
                  </div>
              </div>
          </div>
      );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-brand-600 to-blue-700 rounded-2xl p-8 text-white shadow-xl">
        <div>
          <h1 className="text-3xl font-bold mb-2">Welcome back, {userName}</h1>
          <p className="text-brand-100 max-w-xl">
            You have {activeSession ? '1 active session' : 'no active sessions'} and {upcomingSessions.length} upcoming classes visible.
          </p>
        </div>
        <div className="hidden md:block bg-white/10 backdrop-blur-sm p-4 rounded-xl border border-white/20">
           <p className="text-sm font-medium text-brand-100 uppercase tracking-wider mb-1">Compliance Status</p>
           <div className="flex items-center gap-2 text-emerald-300 font-bold text-lg">
             <CheckCircle size={20} /> System Ready
           </div>
        </div>
      </div>

      {/* Active Session Hero */}
      {activeSession && (
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
            Live Now
          </h2>
          <SpotlightCard className="border-l-4 border-l-emerald-500" spotlightColor="rgba(16, 185, 129, 0.1)">
            <div className="p-6 md:p-8 flex flex-col md:flex-row gap-6 items-start md:items-center justify-between">
              <div className="flex-1">
                 <div className="flex items-center gap-3 mb-2">
                   <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-500 text-white animate-pulse">LIVE EXAM</span>
                   <span className="text-sm text-slate-500 dark:text-slate-400 font-mono">Code: {activeSession.batchIds?.[0] ? MOCK_BATCHES.find(b => b.id === activeSession.batchIds![0])?.code : 'PUBLIC'}</span>
                 </div>
                 <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">{activeSession.title}</h3>
                 <p className="text-slate-500 dark:text-slate-400 flex items-center gap-2">
                   <BookOpen size={16} /> {activeSession.course}
                 </p>
              </div>
              
              <div className="flex flex-col sm:flex-row gap-4 w-full md:w-auto">
                 <div className="text-center px-6 py-3 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-100 dark:border-slate-700">
                    <p className="text-xs text-slate-400 uppercase">Time Remaining</p>
                    <p className="text-xl font-mono font-bold text-slate-900 dark:text-white">00:45:20</p>
                 </div>
                 <Button 
                    size="lg" 
                    className="w-full md:w-auto shadow-lg shadow-brand-500/20" 
                    icon={<Play size={20} />}
                    onClick={() => handleStartWorking(activeSession.id)}
                 >
                   Start Working
                 </Button>
              </div>
            </div>
          </SpotlightCard>
        </div>
      )}

      {/* Upcoming List */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Upcoming Sessions</h2>
          {hiddenSessionIds.length > 0 && (
            <Button 
              variant="ghost" 
              size="sm" 
              icon={<RefreshCw size={14} />}
              onClick={showAllSessions}
            >
              Show Hidden ({hiddenSessionIds.length})
            </Button>
          )}
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {upcomingSessions.map(session => (
            <Card key={session.id} className="flex flex-col h-full hover:border-brand-300 dark:hover:border-brand-700 transition-colors group relative">
              <button 
                onClick={() => hideSession(session.id)}
                className="absolute top-3 right-3 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-full transition-colors opacity-0 group-hover:opacity-100 z-10"
                title="Hide from view"
              >
                <EyeOff size={16} />
              </button>

              <div className="flex justify-between items-start mb-4">
                <div className={`p-2 rounded-lg ${getStatusColor(session.status)}`}>
                   <Calendar size={20} />
                </div>
                <span className={`px-2.5 py-1 rounded text-xs font-medium border ${getStatusColor(session.status)}`}>
                   {new Date(session.startTime).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}
                </span>
              </div>
              
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1 group-hover:text-brand-600 transition-colors">
                {session.title}
              </h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">{session.course}</p>
              
              <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between text-sm">
                 <span className="text-slate-500 flex items-center gap-1">
                   <Clock size={14} /> 60 mins
                 </span>
                 <Button variant="ghost" size="sm" className="text-brand-600 p-0 hover:bg-transparent hover:underline">
                   View Details
                 </Button>
              </div>
            </Card>
          ))}
          
          {/* Add Class Card */}
          <button onClick={() => window.location.hash = '/student/join-batch'} className="flex flex-col items-center justify-center p-6 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700 text-slate-400 hover:text-brand-600 hover:border-brand-300 hover:bg-brand-50/50 dark:hover:bg-brand-900/10 transition-all h-full min-h-[200px]">
             <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
               <ArrowRight size={24} />
             </div>
             <p className="font-medium">Join New Class</p>
             <p className="text-xs mt-1">Use batch code</p>
          </button>
        </div>
      </div>
    </div>
  );
};