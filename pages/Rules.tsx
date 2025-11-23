import React, { useState } from 'react';
import { MOCK_RULE_SETS } from '../constants';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input, Select } from '../components/ui/Input';
import { Plus, Globe, Laptop, Check, XCircle } from 'lucide-react';
import { RuleSet } from '../types';

export const Rules: React.FC = () => {
  const [rules, setRules] = useState<RuleSet[]>(MOCK_RULE_SETS);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newRuleName, setNewRuleName] = useState('');

  const handleCreateRule = () => {
    const newRule: RuleSet = {
      id: Math.random().toString(36).substr(2, 9),
      name: newRuleName,
      mode: 'Blocklist',
      websites: [],
      applications: []
    };
    setRules([...rules, newRule]);
    setIsModalOpen(false);
    setNewRuleName('');
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Access Rules & Policies</h1>
          <p className="text-slate-500 dark:text-slate-400">Define whitelist and blocklist profiles for sessions.</p>
        </div>
        <Button icon={<Plus size={18} />} onClick={() => setIsModalOpen(true)}>Create Rule Set</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {rules.map((rule) => (
          <Card key={rule.id} className="flex flex-col h-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{rule.name}</h3>
              <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${
                rule.mode === 'Whitelist' 
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800' 
                  : 'bg-red-50 text-red-700 border-red-100 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800'
              }`}>
                {rule.mode}
              </span>
            </div>

            <div className="space-y-4 flex-1">
              <div>
                <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
                  <Globe size={16} />
                  <span className="font-medium">Websites</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {rule.websites.slice(0, 4).map((site, i) => (
                    <span key={i} className="bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-600">
                      {site}
                    </span>
                  ))}
                  {rule.websites.length > 4 && (
                    <span className="text-xs text-slate-400 flex items-center">+{rule.websites.length - 4} more</span>
                  )}
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
                  <Laptop size={16} />
                  <span className="font-medium">Applications</span>
                </div>
                <div className="flex flex-wrap gap-2">
                   {rule.applications.length > 0 ? rule.applications.map((app, i) => (
                    <span key={i} className="bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-600">
                      {app}
                    </span>
                  )) : <span className="text-xs text-slate-400 italic">No restrictions</span>}
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-700 flex gap-2">
              <Button size="sm" variant="secondary" className="flex-1">Edit</Button>
              <Button size="sm" variant="secondary" className="text-red-600 hover:text-red-700">Delete</Button>
            </div>
          </Card>
        ))}
      </div>

      <Modal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        title="Create New Rule Set"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateRule}>Create Rule</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input 
            label="Rule Set Name" 
            placeholder="e.g., Strict Coding Exam" 
            value={newRuleName}
            onChange={(e) => setNewRuleName(e.target.value)}
          />
          <Select 
            label="Restriction Mode"
            options={[
              { value: 'Blocklist', label: 'Blocklist (Allow all except...)' },
              { value: 'Whitelist', label: 'Whitelist (Block all except...)' },
            ]}
          />
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Websites</label>
            <div className="p-3 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-900 min-h-[80px]">
               <span className="text-xs text-slate-400">Type domain and press Enter (e.g. google.com)</span>
            </div>
          </div>
          <div>
             <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Applications</label>
             <div className="p-3 border border-slate-300 dark:border-slate-700 rounded-lg bg-slate-50 dark:bg-slate-900 min-h-[80px]">
                <span className="text-xs text-slate-400">Type process name and press Enter (e.g. Discord)</span>
             </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};
