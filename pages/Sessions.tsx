import React, { useState, useEffect } from 'react';
import { GoogleGenAI } from "@google/genai";
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { Plus, Filter, Trash2, Calendar, Clock, AlertCircle, Search, X, Globe, Lock, ShieldAlert, Users, School, Sparkles } from 'lucide-react';
import { SessionStatus, SessionType, Session, RuleSet } from '../types';
import { MOCK_BATCHES, MOCK_RULE_SETS } from '../constants';

export const Sessions: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [availableRuleSets, setAvailableRuleSets] = useState<RuleSet[]>(MOCK_RULE_SETS);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isJoinModalOpen, setIsJoinModalOpen] = useState(false); // For students
  const [joinCode, setJoinCode] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentTime, setCurrentTime] = useState(new Date());
  
  // Filter States
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [typeFilter, setTypeFilter] = useState<string>('All');
  const [dateRange, setDateRange] = useState({ start: '', end: '' });

  // AI Summary State
  const [summaryModalOpen, setSummaryModalOpen] = useState(false);
  const [aiSummary, setAiSummary] = useState('');
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);

  const userRole = localStorage.getItem('userRole');
  const isStudent = userRole === 'student';

  // Load custom rules for sync
  useEffect(() => {
    const storedRules = localStorage.getItem('customRuleSets');
    if (storedRules) {
      setAvailableRuleSets(JSON.parse(storedRules));
    }
  }, [isModalOpen]);

  // Initialize with demo data relative to current time to demonstrate features
  useEffect(() => {
    const now = new Date();
    const demoSessions: Session[] = [
      {
        id: '101',
        title: 'Midterm Examination (Live Demo)',
        course: 'CS 302: Algorithms',
        type: SessionType.EXAM,
        // Active now: Started 30 mins ago, ends in 1 hour
        startTime: new Date(now.getTime() - 30 * 60000).toISOString(),
        endTime: new Date(now.getTime() + 60 * 60000).toISOString(),
        status: SessionStatus.ACTIVE,
        ruleSetId: '1',
        batchIds: ['b1']
      },
      {
        id: '102',
        title: 'Intro to ML Lecture',
        course: 'CS 405: Machine Learning',
        type: SessionType.LECTURE,
        // Starting soon: Starts in 5 mins
        startTime: new Date(now.getTime() + 5 * 60000).toISOString(),
        endTime: new Date(now.getTime() + 95 * 60000).toISOString(),
        status: SessionStatus.UPCOMING,
        ruleSetId: '2',
        batchIds: ['b2']
      },
      {
        id: '103',
        title: 'Database Systems Lab',
        course: 'CS 350: Databases',
        type: SessionType.LAB,
        // Completed
        startTime: new Date(now.getTime() - 180 * 60000).toISOString(),
        endTime: new Date(now.getTime() - 60 * 60000).toISOString(),
        status: SessionStatus.COMPLETED,
        ruleSetId: '3',
        batchIds: ['b1']
      },
      {
        id: '104',
        title: 'Future Physics Seminar',
        course: 'PHY 201: Quantum Mechanics',
        type: SessionType.LECTURE,
        // Future: Starts in 3 hours
        startTime: new Date(now.getTime() + 180 * 60000).toISOString(),
        endTime: new Date(now.getTime() + 240 * 60000).toISOString(),
        status: SessionStatus.UPCOMING,
        ruleSetId: '2',
        batchIds: [] // Public session
      },
    ];
    setSessions(demoSessions);
  }, []);

  // Real-time status update simulation
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      setCurrentTime(now);
      
      setSessions(prevSessions => prevSessions.map(session => {
        const start = new Date(session.startTime);
        const end = new Date(session.endTime);
        let newStatus = session.status;

        // Auto-update status based on time
        if (now >= start && now <= end) {
          newStatus = SessionStatus.ACTIVE;
        } else if (now > end) {
          newStatus = SessionStatus.COMPLETED;
        } else if (now < start) {
          newStatus = SessionStatus.UPCOMING;
        }
        
        return { ...session, status: newStatus };
      }));
    }, 5000); // Check every 5 seconds

    return () => clearInterval(interval);
  }, []);

  // New Session Form State
  const [newSession, setNewSession] = useState({
    title: '',
    course: '',
    type: SessionType.LECTURE,
    date: '',
    startTime: '',
    endTime: '',
    selectedBatchIds: [] as string[],
    ruleSetId: ''
  });

  const handleCreateSession = () => {
    const s: Session = {
      id: Math.random().toString(36).substr(2, 9),
      title: newSession.title,
      course: newSession.course,
      type: newSession.type,
      startTime: `${newSession.date}T${newSession.startTime}`,
      endTime: `${newSession.date}T${newSession.endTime}`,
      status: SessionStatus.UPCOMING,
      ruleSetId: newSession.ruleSetId || '1',
      batchIds: newSession.selectedBatchIds
    };
    setSessions([s, ...sessions]);
    setIsModalOpen(false);
    // Reset form
    setNewSession({ 
      title: '', 
      course: '', 
      type: SessionType.LECTURE, 
      date: '', 
      startTime: '', 
      endTime: '',
      selectedBatchIds: [],
      ruleSetId: ''
    });
  };

  // Student Join Batch Logic
  const handleJoinBatch = () => {
    // Simulate joining by verifying code against mock batches
    const batch = MOCK_BATCHES.find(b => b.code === joinCode.toUpperCase());
    if (batch) {
      // In a real app, this would save to backend. Here we save to localStorage for persistence in this session.
      const currentJoined = JSON.parse(localStorage.getItem('joinedBatches') || '[]');
      if (!currentJoined.includes(batch.id)) {
        localStorage.setItem('joinedBatches', JSON.stringify([...currentJoined, batch.id]));
        alert(`Successfully joined ${batch.name}!`);
      } else {
        alert('You are already a member of this class.');
      }
      setIsJoinModalOpen(false);
      setJoinCode('');
      // Trigger a re-render or update logic if needed
    } else {
      alert('Invalid Batch Code. Please check and try again.');
    }
  };

  const handleDeleteSession = (id: string) => {
    if(window.confirm('Are you sure you want to delete this session?')) {
      setSessions(prev => prev.filter(s => s.id !== id));
    }
  };

  const handleGenerateSummary = async (session: Session) => {
    setAiSummary('');
    setIsGeneratingSummary(true);
    setSummaryModalOpen(true);

    try {
      const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
      
      // Enhance context with batch names
      const batchNames = session.batchIds?.map(bid => MOCK_BATCHES.find(b => b.id === bid)?.name).filter(Boolean).join(', ') || 'Public (No batches)';
      
      const prompt = `
        Please generate a concise, professional summary for this academic session.
        Structure the summary to be readable at a glance.
        
        Details:
        Title: ${session.title}
        Course: ${session.course}
        Type: ${session.type}
        Start Time: ${new Date(session.startTime).toLocaleString()}
        End Time: ${new Date(session.endTime).toLocaleString()}
        Status: ${session.status}
        Assigned Classes: ${batchNames}
      `;

      const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash',
        contents: prompt,
      });

      setAiSummary(response.text);
    } catch (error) {
      setAiSummary("Failed to generate summary. Please try again.");
      console.error(error);
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const filteredSessions = sessions.filter(s => {
    // Role filtering
    if (isStudent) {
      // If student, only show sessions that are public (no batch) OR belong to joined batches
      const joinedBatches = JSON.parse(localStorage.getItem('joinedBatches') || '[]');
      // For demo purposes, we also show sessions with NO batch (public)
      const isPublic = !s.batchIds || s.batchIds.length === 0;
      const isJoined = s.batchIds?.some(id => joinedBatches.includes(id));
      
      // For this prototype, lets just show all for students to see the UI, 
      // but in production uncomment: if (!isPublic && !isJoined) return false;
    }

    const searchLower = searchTerm.toLowerCase();
    const matchesSearch = s.title.toLowerCase().includes(searchLower) || 
                          s.course.toLowerCase().includes(searchLower);
    
    const matchesStatus = statusFilter === 'All' || s.status === statusFilter;
    const matchesType = typeFilter === 'All' || s.type === typeFilter;

    let matchesDate = true;
    if (dateRange.start) {
        const sessionDate = new Date(s.startTime);
        const filterStart = new Date(dateRange.start);
        filterStart.setHours(0,0,0,0);
        matchesDate = matchesDate && sessionDate >= filterStart;
    }
    if (dateRange.end) {
        const sessionDate = new Date(s.startTime);
        const filterEnd = new Date(dateRange.end);
        filterEnd.setHours(23, 59, 59, 999);
        matchesDate = matchesDate && sessionDate <= filterEnd;
    }

    return matchesSearch && matchesStatus && matchesType && matchesDate;
  });

  const isStartingSoon = (session: Session) => {
    const start = new Date(session.startTime);
    const diff = start.getTime() - currentTime.getTime();
    return session.status === SessionStatus.UPCOMING && diff > 0 && diff <= 15 * 60 * 1000;
  };

  const getStatusBadge = (session: Session) => {
    if (isStartingSoon(session)) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 border border-amber-200 animate-pulse">
          <AlertCircle size={12} className="mr-1" />
          Starting Soon
        </span>
      );
    }

    switch (session.status) {
      case SessionStatus.ACTIVE: 
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 border border-emerald-200 shadow-sm">
            <span className="relative flex h-2 w-2 mr-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Active Now
          </span>
        );
      case SessionStatus.UPCOMING: 
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800">Upcoming</span>;
      case SessionStatus.COMPLETED: 
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700">Completed</span>;
      default: 
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">Unknown</span>;
    }
  };

  const resetFilters = () => {
    setSearchTerm('');
    setStatusFilter('All');
    setTypeFilter('All');
    setDateRange({ start: '', end: '' });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Sessions</h1>
          <p className="text-slate-500 dark:text-slate-400">
            {isStudent ? 'My Enrolled Sessions & Classes' : 'Schedule and monitor academic sessions.'}
          </p>
        </div>
        <div className="flex gap-3">
          {isStudent && (
            <Button variant="outline" icon={<School size={18} />} onClick={() => setIsJoinModalOpen(true)}>
              Join Class
            </Button>
          )}
          {!isStudent && (
            <Button icon={<Plus size={18} />} onClick={() => setIsModalOpen(true)}>Add New Session</Button>
          )}
        </div>
      </div>

      <Card noPadding className="overflow-hidden">
        {/* Toolbar */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50">
          <div className="flex flex-col sm:flex-row gap-4 justify-between">
            <div className="relative w-full sm:w-72">
              <Input 
                placeholder="Search sessions..." 
                value={searchTerm} 
                onChange={e => setSearchTerm(e.target.value)} 
                className="mb-0"
                icon={<Search size={16} />}
              />
            </div>
            <Button 
              variant={isFiltersOpen ? 'primary' : 'secondary'} 
              icon={<Filter size={16} />} 
              onClick={() => setIsFiltersOpen(!isFiltersOpen)}
            >
              {isFiltersOpen ? 'Hide Filters' : 'Filters'}
            </Button>
          </div>

          {/* Advanced Filters */}
          {isFiltersOpen && (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 animate-fade-in">
              <Select
                label="Status"
                options={[
                  { value: 'All', label: 'All Statuses' },
                  { value: SessionStatus.ACTIVE, label: 'Active' },
                  { value: SessionStatus.UPCOMING, label: 'Upcoming' },
                  { value: SessionStatus.COMPLETED, label: 'Completed' },
                ]}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="mb-0"
              />
              <Select
                label="Type"
                options={[
                  { value: 'All', label: 'All Types' },
                  { value: SessionType.LECTURE, label: 'Lecture' },
                  { value: SessionType.EXAM, label: 'Exam' },
                  { value: SessionType.LAB, label: 'Lab' },
                  { value: SessionType.QUIZ, label: 'Quiz' },
                ]}
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="mb-0"
              />
              <Input
                label="From Date"
                type="date"
                value={dateRange.start}
                onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
                className="mb-0"
              />
              <Input
                label="To Date"
                type="date"
                value={dateRange.end}
                onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
                className="mb-0"
              />
              <div className="flex items-end">
                 <Button 
                   variant="ghost" 
                   className="w-full text-slate-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 border border-slate-200 dark:border-slate-700"
                   onClick={resetFilters}
                   icon={<X size={16} />}
                 >
                   Reset Filters
                 </Button>
              </div>
            </div>
          )}
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="px-6 py-4 font-semibold text-slate-900 dark:text-white">Session Title</th>
                <th className="px-6 py-4 font-semibold text-slate-900 dark:text-white">Course / Class</th>
                <th className="px-6 py-4 font-semibold text-slate-900 dark:text-white">Type</th>
                <th className="px-6 py-4 font-semibold text-slate-900 dark:text-white">Time</th>
                <th className="px-6 py-4 font-semibold text-slate-900 dark:text-white">Status</th>
                {!isStudent && <th className="px-6 py-4 font-semibold text-slate-900 dark:text-white text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700 bg-white dark:bg-slate-900">
              {filteredSessions.length > 0 ? (
                filteredSessions.map((session) => (
                  <tr key={session.id} className={`hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors ${session.status === SessionStatus.ACTIVE ? 'bg-emerald-50/30 dark:bg-emerald-900/5' : ''}`}>
                    <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
                      {session.title}
                      {session.status === SessionStatus.ACTIVE && (
                        <span className="ml-2 inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" title="Live Monitoring Active"></span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-slate-500 dark:text-slate-400">
                      {session.course}
                      {session.batchIds && session.batchIds.length > 0 && (
                         <div className="flex gap-1 mt-1">
                           {session.batchIds.map(bid => {
                              const b = MOCK_BATCHES.find(mb => mb.id === bid);
                              return b ? (
                                <span key={bid} className="text-[10px] px-1.5 py-0.5 bg-slate-100 dark:bg-slate-700 rounded text-slate-500">
                                  {b.name}
                                </span>
                              ) : null;
                           })}
                         </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300">
                        {session.type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-slate-500 dark:text-slate-400">
                      <div className="flex flex-col text-xs">
                        <span className="flex items-center gap-1"><Calendar size={12}/> {new Date(session.startTime).toLocaleDateString()}</span>
                        <span className="flex items-center gap-1"><Clock size={12}/> {new Date(session.startTime).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {getStatusBadge(session)}
                    </td>
                    {!isStudent && (
                      <td className="px-6 py-4 text-right">
                        <div className="flex justify-end gap-2">
                          <button
                            className="text-brand-600 hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-300 p-2 rounded-full hover:bg-brand-50 dark:hover:bg-brand-900/10 transition-colors"
                            onClick={() => handleGenerateSummary(session)}
                            title="AI Summary"
                          >
                            <Sparkles size={18} />
                          </button>
                          <button 
                            className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors p-2 rounded-full hover:bg-red-50 dark:hover:bg-red-900/10"
                            onClick={() => handleDeleteSession(session.id)}
                            title="Delete Session"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={isStudent ? 5 : 6} className="px-6 py-12 text-center text-slate-500">
                    <div className="flex flex-col items-center justify-center">
                      <Filter className="h-10 w-10 text-slate-300 mb-3" />
                      <p className="text-lg font-medium text-slate-900 dark:text-white">No sessions found</p>
                      <p className="text-sm text-slate-500">Try adjusting your search or filters.</p>
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        className="mt-4 text-brand-600" 
                        onClick={resetFilters}
                      >
                        Clear all filters
                      </Button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* AI Summary Modal */}
      <Modal
        isOpen={summaryModalOpen}
        onClose={() => setSummaryModalOpen(false)}
        title="AI Session Summary"
        footer={
          <Button onClick={() => setSummaryModalOpen(false)}>Close</Button>
        }
      >
        <div className="space-y-4">
          {isGeneratingSummary ? (
            <div className="flex flex-col items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600 mb-4"></div>
              <p className="text-slate-500 animate-pulse">Generating summary using Gemini...</p>
            </div>
          ) : (
            <div className="bg-slate-50 dark:bg-slate-900 p-4 rounded-lg border border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2 mb-3 text-brand-600 dark:text-brand-400 font-medium">
                <Sparkles size={16} />
                <span>Generated Summary</span>
              </div>
              <p className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed whitespace-pre-line">
                {aiSummary}
              </p>
            </div>
          )}
        </div>
      </Modal>

      {/* Create Modal (Professor) */}
      <Modal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        title="Create New Session"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateSession}>Create Session</Button>
          </>
        }
      >
        <div className="space-y-4 max-h-[60vh] overflow-y-auto px-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input 
              label="Session Title" 
              placeholder="e.g., Midterm Exam" 
              value={newSession.title}
              onChange={e => setNewSession({...newSession, title: e.target.value})}
            />
            <Input 
              label="Course Name" 
              placeholder="e.g., CS 101" 
              value={newSession.course}
              onChange={e => setNewSession({...newSession, course: e.target.value})}
            />
          </div>
          <Select 
            label="Session Type"
            options={[
              { value: SessionType.LECTURE, label: 'Lecture' },
              { value: SessionType.EXAM, label: 'Exam' },
              { value: SessionType.QUIZ, label: 'Quiz' },
              { value: SessionType.LAB, label: 'Lab' },
            ]}
            value={newSession.type}
            onChange={e => setNewSession({...newSession, type: e.target.value as SessionType})}
          />
          
          {/* Batch Selection */}
          <div className="space-y-2">
             <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">Assign to Classes (Batches)</label>
             <div className="grid grid-cols-2 gap-2">
               {MOCK_BATCHES.map(batch => (
                 <label key={batch.id} className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                   newSession.selectedBatchIds.includes(batch.id) 
                     ? 'bg-brand-50 border-brand-200 dark:bg-brand-900/20 dark:border-brand-700' 
                     : 'bg-slate-50 border-slate-200 dark:bg-slate-900 dark:border-slate-700'
                 }`}>
                   <input 
                     type="checkbox" 
                     className="rounded border-slate-300 text-brand-600 focus:ring-brand-500 mr-3"
                     checked={newSession.selectedBatchIds.includes(batch.id)}
                     onChange={(e) => {
                       if (e.target.checked) {
                         setNewSession(prev => ({...prev, selectedBatchIds: [...prev.selectedBatchIds, batch.id]}));
                       } else {
                         setNewSession(prev => ({...prev, selectedBatchIds: prev.selectedBatchIds.filter(id => id !== batch.id)}));
                       }
                     }}
                   />
                   <div>
                     <div className="text-sm font-medium text-slate-900 dark:text-white">{batch.name}</div>
                     <div className="text-xs text-slate-500">{batch.department} • Yr {batch.year}</div>
                   </div>
                 </label>
               ))}
             </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input 
              label="Date" 
              type="date" 
              value={newSession.date}
              onChange={e => setNewSession({...newSession, date: e.target.value})}
            />
            <div className="grid grid-cols-2 gap-2">
              <Input 
                label="Start" 
                type="time" 
                value={newSession.startTime}
                onChange={e => setNewSession({...newSession, startTime: e.target.value})}
              />
              <Input 
                label="End" 
                type="time" 
                value={newSession.endTime}
                onChange={e => setNewSession({...newSession, endTime: e.target.value})}
              />
            </div>
          </div>

          <hr className="border-slate-200 dark:border-slate-700 my-4"/>
          
          {/* Internet Access Control Section */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-2">
               <ShieldAlert size={16} className="text-brand-500"/> Internet Access Control
            </label>
            <div className="bg-slate-50 dark:bg-slate-900 p-4 rounded-lg border border-slate-200 dark:border-slate-700">
              <Select 
                 label="Select Security Rule Set"
                 options={[
                     { value: '', label: 'Select a Rule Set...' },
                     ...availableRuleSets.map(r => ({ value: r.id, label: `${r.name} (${r.mode})` }))
                 ]}
                 value={newSession.ruleSetId}
                 onChange={(e) => setNewSession({...newSession, ruleSetId: e.target.value})}
                 className="mb-2"
              />
              <p className="text-xs text-slate-500 mt-1">
                This rule set defines which websites and applications are allowed or blocked during the session.
              </p>
            </div>
          </div>
        </div>
      </Modal>

      {/* Join Batch Modal (Student) */}
      <Modal
        isOpen={isJoinModalOpen}
        onClose={() => setIsJoinModalOpen(false)}
        title="Join a Class"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsJoinModalOpen(false)}>Cancel</Button>
            <Button onClick={handleJoinBatch} disabled={joinCode.length < 6}>Join Class</Button>
          </>
        }
      >
        <div className="text-center space-y-6 py-4">
           <div className="bg-blue-50 dark:bg-blue-900/20 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-2">
             <Users size={32} className="text-blue-600 dark:text-blue-400" />
           </div>
           <div>
             <h3 className="text-lg font-medium text-slate-900 dark:text-white">Enter Class Code</h3>
             <p className="text-sm text-slate-500">Ask your professor for the 6-character batch code.</p>
           </div>
           <div className="max-w-xs mx-auto">
             <Input 
               className="text-center text-2xl tracking-widest font-mono uppercase"
               placeholder="e.g. CSE4X9"
               maxLength={6}
               value={joinCode}
               onChange={e => setJoinCode(e.target.value.toUpperCase())}
               autoFocus
             />
           </div>
        </div>
      </Modal>
    </div>
  );
};