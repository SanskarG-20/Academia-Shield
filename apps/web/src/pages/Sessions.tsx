import React, { useState, useEffect } from 'react';
import { GoogleGenAI } from "@google/genai";
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { Plus, Filter, Search, X, School, Sparkles, Loader2 as Spinner } from 'lucide-react';
import { SessionStatus, SessionType, Session, RuleSet } from '../types';
import { MOCK_BATCHES } from '../constants';
import { getSessions, createSession, updateSessionStatus, getAgentConfig, getRules } from '../lib/api';
import { SessionCard } from '../components/SessionCard';
import { CreateSessionModal } from '../components/CreateSessionModal';

export const Sessions: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [rules, setRules] = useState<RuleSet[]>([]);
  const [agentConfig, setAgentConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  async function fetchAll() {
    try {
      const [s, r, a] = await Promise.all([getSessions(), getRules(), getAgentConfig()]);
      setSessions(s);
      setRules(r);
      setAgentConfig(a);
      setError("");
    } catch (e: any) {
      setError("Cannot reach server. Check IP in api.ts.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 15000); // auto-refresh every 15s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const timeInterval = setInterval(() => setCurrentTime(new Date()), 5000);
    return () => clearInterval(timeInterval);
  }, []);

  const handleCreateSession = async (formData: any) => {
    await createSession(formData);
    await fetchAll();
  };

  const handleStatusChange = async (id: string, newStatus: string) => {
    try {
      await updateSessionStatus(id, newStatus);
      await fetchAll();
    } catch (err: any) {
      alert("Failed to update status: " + err.message);
    }
  };

  const handleDeleteSession = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this session?')) {
      alert("Delete session functionality not wired in this step, but ID is " + id);
    }
  };

  const handleJoinBatch = () => {
    const batch = MOCK_BATCHES.find(b => b.code === joinCode.toUpperCase());
    if (batch) {
      const currentJoined = JSON.parse(localStorage.getItem('joinedBatches') || '[]');
      if (!currentJoined.includes(batch.id)) {
        localStorage.setItem('joinedBatches', JSON.stringify([...currentJoined, batch.id]));
        alert(`Successfully joined ${batch.name}!`);
      } else {
        alert('You are already a member of this class.');
      }
      setIsJoinModalOpen(false);
      setJoinCode('');
    } else {
      alert('Invalid Batch Code. Please check and try again.');
    }
  };

  const handleGenerateSummary = async (session: any) => {
    setAiSummary('');
    setIsGeneratingSummary(true);
    setSummaryModalOpen(true);

    try {
      const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
      const batchNames = session.batchIds?.map((bid: string) => MOCK_BATCHES.find(b => b.id === bid)?.name).filter(Boolean).join(', ') || 'Public (No batches)';
      
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

  const resetFilters = () => {
    setSearchTerm('');
    setStatusFilter('All');
    setTypeFilter('All');
    setDateRange({ start: '', end: '' });
  };

  const filteredSessions = sessions.filter((s: any) => {
    if (isStudent) {
      const joinedBatches = JSON.parse(localStorage.getItem('joinedBatches') || '[]');
      // Show all for demo
    }

    const searchLower = searchTerm.toLowerCase();
    const matchesSearch = s.title.toLowerCase().includes(searchLower) || s.course.toLowerCase().includes(searchLower);
    const matchesStatus = statusFilter === 'All' || s.status.toLowerCase() === statusFilter.toLowerCase();
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

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {agentConfig && (
        agentConfig.blocking_active ? (
          <div className="w-full mb-6 px-5 py-4 rounded-xl border border-red-600 bg-red-950/40 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-red-400 text-xl animate-pulse">🔴</span>
              <div>
                <p className="text-red-300 font-semibold text-sm">
                  BLOCKING IN PROGRESS — {agentConfig.active_sessions[0]?.title}
                </p>
                <p className="text-red-400/70 text-xs mt-0.5">
                  {agentConfig.domains.length} domains blocked · 
                  Ends at {new Date(agentConfig.active_sessions[0]?.ends_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
                </p>
              </div>
            </div>
            <span className="text-xs text-red-500 font-mono">
              {new Date(agentConfig.server_time).toLocaleTimeString()}
            </span>
          </div>
        ) : (
          <div className="w-full mb-6 px-5 py-3 rounded-xl border border-green-800 bg-green-950/30 flex items-center gap-3">
            <span className="text-green-400">🟢</span>
            <p className="text-green-300 text-sm font-medium">
              No Active Block Session — Students have unrestricted access
            </p>
          </div>
        )
      )}

      {error && (
        <p className="text-red-400 p-4 border border-red-900 bg-red-950/20 rounded-lg">{error}</p>
      )}

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
                filteredSessions.map((session: any) => (
                  <SessionCard
                    key={session._id || session.id}
                    session={session}
                    isStudent={isStudent}
                    onStatusChange={handleStatusChange}
                    onGenerateSummary={handleGenerateSummary}
                    onDeleteSession={handleDeleteSession}
                    currentTime={currentTime}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={isStudent ? 5 : 6} className="px-6 py-12 text-center text-slate-500">
                    <div className="flex flex-col items-center justify-center">
                      <Filter className="h-10 w-10 text-slate-300 mb-3" />
                      <p className="text-lg font-medium text-slate-900 dark:text-white">No sessions found</p>
                      <p className="text-sm text-slate-500">Try adjusting your search or filters.</p>
                      <Button variant="ghost" size="sm" className="mt-4 text-brand-600" onClick={resetFilters}>
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

      <CreateSessionModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        rules={rules} 
        onCreate={handleCreateSession} 
      />

      {/* AI Summary Modal */}
      <Modal
        isOpen={summaryModalOpen}
        onClose={() => setSummaryModalOpen(false)}
        title="AI Session Summary"
        footer={<Button onClick={() => setSummaryModalOpen(false)}>Close</Button>}
      >
        <div className="space-y-4">
          {isGeneratingSummary ? (
            <div className="flex flex-col items-center justify-center py-8">
              <Spinner className="animate-spin text-brand-600 mb-4" size={32} />
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

      {/* Join Batch Modal (Student) */}
      <Modal
        isOpen={isJoinModalOpen}
        onClose={() => setIsJoinModalOpen(false)}
        title="Join a Class"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsJoinModalOpen(false)}>Cancel</Button>
            <Button onClick={handleJoinBatch}>Join Class</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input 
            label="Class Join Code"
            placeholder="e.g. CS101A"
            value={joinCode}
            onChange={e => setJoinCode(e.target.value)}
          />
          <p className="text-sm text-slate-500">Ask your professor for the 6-character class code to join their sessions.</p>
        </div>
      </Modal>
    </div>
  );
};
