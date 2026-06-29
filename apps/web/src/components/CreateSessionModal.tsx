import React, { useState } from 'react';
import { Modal } from './ui/Modal';
import { Input, Select } from './ui/Input';
import { Button } from './ui/Button';
import { Batch, SessionType, RuleSet } from '../types';

interface CreateSessionModalProps {
  isOpen: boolean;
  onClose: () => void;
  rules: RuleSet[];
  batches: Batch[];
  onCreate: (formData: any) => Promise<void>;
}

export const CreateSessionModal: React.FC<CreateSessionModalProps> = ({
  isOpen,
  onClose,
  rules,
  batches,
  onCreate,
}) => {
  console.log('rendering form');

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
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const formData = {
        title: newSession.title,
        course: newSession.course,
        type: newSession.type,
        startTime: `${newSession.date}T${newSession.startTime}`,
        endTime: `${newSession.date}T${newSession.endTime}`,
        ruleSetId: newSession.ruleSetId,
        batchIds: newSession.selectedBatchIds
      };
      await onCreate(formData);
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
      onClose();
    } catch (error) {
      console.error(error);
      alert('Failed to create session');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Session"
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose} disabled={isLoading}>Cancel</Button>
          <Button type="submit" form="create-session-form" disabled={isLoading}>
            {isLoading ? 'Creating...' : 'Create Session'}
          </Button>
        </>
      }
    >
      <form id="create-session-form" onSubmit={handleSubmit} className="space-y-4 max-h-[60vh] overflow-y-auto px-1">
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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Input
            label="Date"
            type="date"
            value={newSession.date}
            onChange={e => setNewSession({...newSession, date: e.target.value})}
          />
          <Input
            label="Start Time"
            type="time"
            value={newSession.startTime}
            onChange={e => setNewSession({...newSession, startTime: e.target.value})}
          />
          <Input
            label="End Time"
            type="time"
            value={newSession.endTime}
            onChange={e => setNewSession({...newSession, endTime: e.target.value})}
          />
        </div>

        <Select
          label="Rule Set (Policy)"
          options={[
            { value: '', label: 'Select a Rule Set...' },
            ...rules.map(r => ({ value: r._id, label: r.name }))
          ]}
          value={newSession.ruleSetId}
          onChange={e => setNewSession({...newSession, ruleSetId: e.target.value})}
        />

        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">Assign to Classes (Batches)</label>
          <div className="grid grid-cols-2 gap-2">
            {batches.map(batch => (
              <label key={batch._id} className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                newSession.selectedBatchIds.includes(batch._id)
                  ? 'bg-brand-50 border-brand-200 dark:bg-brand-900/20 dark:border-brand-700'
                  : 'bg-slate-50 border-slate-200 dark:bg-slate-900 dark:border-slate-700'
              }`}>
                <input
                  type="checkbox"
                  className="rounded border-slate-300 text-brand-600 focus:ring-brand-500 mr-3"
                  checked={newSession.selectedBatchIds.includes(batch._id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setNewSession(prev => ({...prev, selectedBatchIds: [...prev.selectedBatchIds, batch._id]}));
                    } else {
                      setNewSession(prev => ({...prev, selectedBatchIds: prev.selectedBatchIds.filter(id => id !== batch._id)}));
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
      </form>
    </Modal>
  );
};