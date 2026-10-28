import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input, Select } from '../components/ui/Input';
import { Plus, Globe, Laptop, Edit2, Trash2, Loader2 as Spinner } from 'lucide-react';
import { RuleSet } from '../types';
import { getRules, createRule, updateRule, deleteRule, getSessions } from '../lib/api';

export const Rules: React.FC = () => {
  const [rules, setRules] = useState<RuleSet[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeRuleIds, setActiveRuleIds] = useState<string[]>([]);

  // Form State
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    mode: 'Blocklist',
    websites: '',
    applications: ''
  });

  async function fetchAll() {
    setLoading(true);
    try {
      const [rulesData, sessionsData] = await Promise.all([getRules(), getSessions()]);
      setRules(rulesData);
      setActiveRuleIds(
        sessionsData
          .filter((s: any) => String(s.status).toLowerCase() === 'active')
          .map((s: any) => String(s.ruleSetId || ''))
          .filter(Boolean)
      );
      setError("");
    } catch (e: any) {
      setError("Failed to load. Is the server running at the configured IP?");
    } finally {
      setLoading(false);
    }
  }

  // Load rules on mount
  useEffect(() => {
    fetchAll();
  }, []);

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
      id: rule._id,
      name: rule.name,
      mode: rule.mode,
      websites: rule.websites.join(', '),
      applications: rule.applications.join(', ')
    });
    setIsModalOpen(true);
  };

  const handleSaveRule = async () => {
    const websiteList = formData.websites.split(',').map(s => s.trim()).filter(Boolean);
    const appList = formData.applications.split(',').map(s => s.trim()).filter(Boolean);

    try {
      if (isEditing) {
        await updateRule(formData.id, {
          name: formData.name,
          mode: formData.mode,
          websites: websiteList,
          applications: appList,
        });
      } else {
        await createRule(formData.name, formData.mode, websiteList, appList);
      }
      await fetchAll();
      setFormData({
        id: '',
        name: '',
        mode: 'Blocklist',
        websites: '',
        applications: ''
      });
      setIsModalOpen(false);
    } catch (e: any) {
      alert(e.message || "Failed to save rule");
    }
  };

  const handleDeleteRule = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this rule set?')) {
      try {
        await deleteRule(id);
        await fetchAll();
      } catch (e: any) {
        alert(e.message || "Failed to delete rule");
      }
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spinner className="animate-spin text-brand-600" size={32} />
      </div>
    );
  }

  if (error) return <p className="text-red-400 p-6">{error}</p>;

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
        {rules.map((rule: any) => (
          <Card key={rule._id} className="flex flex-col h-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white truncate pr-2">{rule.name}</h3>
              <div className="flex gap-2 items-center">
                {activeRuleIds.includes(rule._id) && (
                  <span className="inline-flex items-center gap-1.5 bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 text-xs font-semibold px-2.5 py-1 rounded-full border border-rose-300 dark:border-rose-800 shadow-xs">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                    </span>
                    BLOCKING ACTIVE
                  </span>
                )}
                <span className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium border ${
                  rule.mode === 'Whitelist' 
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800' 
                    : 'bg-red-50 text-red-700 border-red-100 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800'
                }`}>
                  {rule.mode}
                </span>
              </div>
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
                className="flex-1 text-gray-400 hover:text-red-400 transition-colors"
                icon={<Trash2 size={14}/>}
                onClick={() => handleDeleteRule(rule._id)}
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
              placeholder="e.g. chrome.exe, spotify.exe (Comma separated)"
              value={formData.applications}
              onChange={(e) => setFormData({...formData, applications: e.target.value})}
            />
            <p className="mt-1 text-xs text-slate-500">Use exact executable names (such as chrome.exe), separated by commas. The Windows agent requests a normal close and allows unsaved-work prompts; it never force-kills apps.</p>
          </div>
        </div>
      </Modal>
    </div>
  );
};
