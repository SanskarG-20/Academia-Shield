import React, { useState, useEffect } from 'react';
import { MOCK_RULE_SETS } from '../constants';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input, Select } from '../components/ui/Input';
import { Plus, Globe, Laptop, Edit2, Trash2 } from 'lucide-react';
import { RuleSet } from '../types';

export const Rules: React.FC = () => {
  const [rules, setRules] = useState<RuleSet[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    mode: 'Blocklist',
    websites: '',
    applications: ''
  });

  // Load rules from localStorage on mount
  useEffect(() => {
    const storedRules = localStorage.getItem('customRuleSets');
    if (storedRules) {
      setRules(JSON.parse(storedRules));
    } else {
      // Initialize with mock data if empty
      setRules(MOCK_RULE_SETS);
      localStorage.setItem('customRuleSets', JSON.stringify(MOCK_RULE_SETS));
    }
  }, []);

  const saveToStorage = (updatedRules: RuleSet[]) => {
    setRules(updatedRules);
    localStorage.setItem('customRuleSets', JSON.stringify(updatedRules));
  };

  const openCreateModal = () => {
    setIsEditing(false);
    setFormData({
      id: '',
      name: '',
      mode: 'Blocklist',
      websites: '',
      applications: ''
    });
    setIsModalOpen(true);
  };

  const openEditModal = (rule: RuleSet) => {
    setIsEditing(true);
    setFormData({
      id: rule.id,
      name: rule.name,
      mode: rule.mode,
      websites: rule.websites.join(', '),
      applications: rule.applications.join(', ')
    });
    setIsModalOpen(true);
  };

  const handleSaveRule = () => {
    const websiteList = formData.websites.split(',').map(s => s.trim()).filter(s => s.length > 0);
    const appList = formData.applications.split(',').map(s => s.trim()).filter(s => s.length > 0);

    let updatedRules: RuleSet[];

    if (isEditing) {
      updatedRules = rules.map(r => r.id === formData.id ? {
        ...r,
        name: formData.name,
        mode: formData.mode as 'Blocklist' | 'Whitelist',
        websites: websiteList,
        applications: appList
      } : r);
    } else {
      const newRule: RuleSet = {
        id: Math.random().toString(36).substr(2, 9),
        name: formData.name,
        mode: formData.mode as 'Blocklist' | 'Whitelist',
        websites: websiteList,
        applications: appList
      };
      updatedRules = [...rules, newRule];
    }

    saveToStorage(updatedRules);
    setIsModalOpen(false);
  };

  const handleDeleteRule = (id: string) => {
    if (window.confirm('Are you sure you want to delete this rule set?')) {
      const updatedRules = rules.filter(r => r.id !== id);
      saveToStorage(updatedRules);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Access Rules & Policies</h1>
          <p className="text-slate-500 dark:text-slate-400">Define whitelist and blocklist profiles for sessions.</p>
        </div>
        <Button icon={<Plus size={18} />} onClick={openCreateModal}>Create Rule Set</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {rules.map((rule) => (
          <Card key={rule.id} className="flex flex-col h-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white truncate pr-2">{rule.name}</h3>
              <span className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium border ${
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
                  {rule.websites.length === 0 && <span className="text-xs text-slate-400 italic">No websites listed</span>}
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
                  <Laptop size={16} />
                  <span className="font-medium">Applications</span>
                </div>
                <div className="flex flex-wrap gap-2">
                   {rule.applications.length > 0 ? rule.applications.slice(0, 4).map((app, i) => (
                    <span key={i} className="bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-600">
                      {app}
                    </span>
                  )) : <span className="text-xs text-slate-400 italic">No restrictions</span>}
                  {rule.applications.length > 4 && (
                    <span className="text-xs text-slate-400 flex items-center">+{rule.applications.length - 4} more</span>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-700 flex gap-2">
              <Button 
                size="sm" 
                variant="secondary" 
                className="flex-1"
                icon={<Edit2 size={14}/>}
                onClick={() => openEditModal(rule)}
              >
                Edit
              </Button>
              <Button 
                size="sm" 
                variant="secondary"
                className="flex-1 text-red-600 hover:bg-red-50 hover:border-red-200 dark:hover:bg-red-900/20 dark:text-red-400 dark:hover:border-red-900/50"
                icon={<Trash2 size={14}/>}
                onClick={() => handleDeleteRule(rule.id)}
              >
                Delete
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={isEditing ? "Edit Rule Set" : "Create New Rule Set"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveRule}>{isEditing ? "Save Changes" : "Create Rule Set"}</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input 
            label="Rule Set Name"
            placeholder="e.g. Computer Science Lab"
            value={formData.name}
            onChange={(e) => setFormData({...formData, name: e.target.value})}
          />
          
          <Select 
            label="Enforcement Mode"
            options={[
              { value: 'Blocklist', label: 'Blocklist (Allow all except listed)' },
              { value: 'Whitelist', label: 'Whitelist (Block all except listed)' },
            ]}
            value={formData.mode}
            onChange={(e) => setFormData({...formData, mode: e.target.value})}
          />
          
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Restricted/Allowed Websites
            </label>
            <textarea
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg py-2.5 px-4 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-colors duration-200"
              rows={3}
              placeholder="e.g. facebook.com, twitter.com (Comma separated)"
              value={formData.websites}
              onChange={(e) => setFormData({...formData, websites: e.target.value})}
            />
            <p className="mt-1 text-xs text-slate-500">Separate domains with commas.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Restricted/Allowed Applications
            </label>
            <textarea
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg py-2.5 px-4 text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-colors duration-200"
              rows={3}
              placeholder="e.g. Calculator, Spotify, Steam (Comma separated)"
              value={formData.applications}
              onChange={(e) => setFormData({...formData, applications: e.target.value})}
            />
            <p className="mt-1 text-xs text-slate-500">Separate application names with commas.</p>
          </div>
        </div>
      </Modal>
    </div>
  );
};