import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input, Select } from '../components/ui/Input';
import {
  Plus,
  Globe,
  Laptop,
  Edit2,
  Trash2,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Lock,
  FileCheck,
  Send,
  RotateCcw,
  Usb,
  ShieldAlert,
  Sliders,
  Calendar,
  Layers,
  X,
  Loader2 as Spinner
} from 'lucide-react';
import { RuleSet, Batch, Session, WebsiteRule, ApplicationRule, DevicePolicyRequirement } from '../types';
import {
  getRules,
  createRule,
  updateRule,
  createBatchRuleSet,
  updateRuleSet,
  deleteRule,
  getSessions,
  getBatches,
  publishRuleSet,
  revokeRuleSet,
  addWebsiteRule,
  addApplicationRule,
  updateDeviceRequirements,
  assignRuleSetToSession
} from '../lib/api';

function cleanDomain(raw: string): string {
  let clean = raw.trim().toLowerCase();
  clean = clean.replace(/^https?:\/\//i, '');
  clean = clean.split('/')[0].split('?')[0].split('#')[0].split(':')[0].trim();
  return clean;
}

export function parseRuleList(text: string): { websites: string[]; apps: string[] } {
  if (!text) return { websites: [], apps: [] };

  const rawEntries = text
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && !s.startsWith('#') && !s.startsWith('//'));

  const websites: string[] = [];
  const apps: string[] = [];

  for (const raw of rawEntries) {
    const item = raw.trim();

    // Check for explicit prefix e.g. app: or web:
    if (/^(app|application|proc|process):/i.test(item)) {
      const appName = item.replace(/^(app|application|proc|process):\s*/i, '').trim();
      if (appName) {
        apps.push(appName.endsWith('.exe') ? appName : `${appName}.exe`);
      }
      continue;
    }
    if (/^(web|website|site|url|domain):/i.test(item)) {
      const domain = item.replace(/^(web|website|site|url|domain):\s*/i, '').trim();
      if (domain) {
        const cleaned = cleanDomain(domain);
        if (cleaned) websites.push(cleaned);
      }
      continue;
    }

    const domainCandidate = cleanDomain(item);

    // If it ends with .exe or .app
    if (/\.(exe|app)$/i.test(item)) {
      apps.push(item);
    } else if (domainCandidate && domainCandidate.includes('.')) {
      // Has dot and isn't .exe -> domain/website (e.g. docs.python.org, coursera.org)
      websites.push(domainCandidate);
    } else if (item.length > 0) {
      // No dot -> application (e.g. discord -> discord.exe, spotify -> spotify.exe)
      apps.push(item.endsWith('.exe') ? item : `${item}.exe`);
    }
  }

  return {
    websites: Array.from(new Set(websites)),
    apps: Array.from(new Set(apps)),
  };
}

export const Rules: React.FC = () => {
  const [rules, setRules] = useState<RuleSet[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<string>('all');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [publishingId, setPublishingId] = useState<string | null>(null);

  // 2 Simple Textbox Inputs
  const [allowedText, setAllowedText] = useState('');
  const [blockedText, setBlockedText] = useState('');
  const [showAdvancedDevice, setShowAdvancedDevice] = useState(false);

  // Session Assignment Modal State
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [selectedRuleSetForAssign, setSelectedRuleSetForAssign] = useState<RuleSet | null>(null);
  const [targetSessionId, setTargetSessionId] = useState<string>('');
  const [isAssigning, setIsAssigning] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    description: '',
    batchId: '',
    deviceRequirements: {
      require_agent_enrolled: true,
      require_website_filtering: true,
      require_application_control: true,
      require_managed_browser: false,
      require_usb_storage_restriction: false,
      required_device_compliance_level: 'audit' as 'audit' | 'development' | 'managed' | 'strict',
      blocked_app_action: 'close' as 'close' | 'warn' | 'log',
    },
  });

  async function fetchAll() {
    setLoading(true);
    try {
      const [rulesData, sessionsData, batchesData] = await Promise.all([
        getRules(selectedBatchId !== 'all' ? selectedBatchId : undefined),
        getSessions(),
        getBatches().catch(() => []),
      ]);
      setBatches(batchesData);
      setRules(rulesData);
      setSessions(sessionsData);
      setError('');
    } catch (e: any) {
      setError(e.message || 'Failed to load policy rules.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAll();
  }, [selectedBatchId]);

  const handleBatchFilterChange = (batchId: string) => {
    setSelectedBatchId(batchId);
  };

  const openCreateModal = () => {
    const defaultBatch = batches.length > 0 ? (batches[0]._id || (batches[0] as any).id) : '';
    setIsEditing(false);
    setShowAdvancedDevice(false);
    setFormData({
      id: '',
      name: '',
      description: '',
      batchId: selectedBatchId !== 'all' ? selectedBatchId : defaultBatch,
      deviceRequirements: {
        require_agent_enrolled: true,
        require_website_filtering: true,
        require_application_control: true,
        require_managed_browser: false,
        require_usb_storage_restriction: false,
        required_device_compliance_level: 'audit',
        blocked_app_action: 'close',
      },
    });
    setAllowedText('docs.python.org\nstackoverflow.com\nCode.exe\nchrome.exe');
    setBlockedText('facebook.com\ninstagram.com\ndiscord.exe\nspotify.exe');
    setIsModalOpen(true);
  };

  const openEditModal = (rule: RuleSet) => {
    setIsEditing(true);
    setShowAdvancedDevice(false);

    const allowedWs = (rule.website_rules || [])
      .filter((r) => r.rule_mode === 'allowed')
      .map((r) => r.domain_pattern);
    const blockedWs = (rule.website_rules || [])
      .filter((r) => r.rule_mode === 'blocked')
      .map((r) => r.domain_pattern);

    const allowedApps = (rule.application_rules || [])
      .filter((r) => r.rule_mode === 'allowed')
      .map((r) => r.application_name);
    const blockedApps = (rule.application_rules || [])
      .filter((r) => r.rule_mode === 'blocked')
      .map((r) => r.application_name);

    const allAllowed = [
      ...allowedWs,
      ...(rule.allowed_websites || []),
      ...allowedApps,
      ...(rule.allowed_applications || []),
    ];
    const allBlocked = [
      ...blockedWs,
      ...(rule.blocked_websites || []),
      ...blockedApps,
      ...(rule.blocked_applications || []),
    ];

    setAllowedText(Array.from(new Set(allAllowed.filter(Boolean))).join('\n'));
    setBlockedText(Array.from(new Set(allBlocked.filter(Boolean))).join('\n'));

    const dev = rule.device_requirements || {
      require_agent_enrolled: true,
      require_website_filtering: true,
      require_application_control: true,
      require_managed_browser: false,
      require_usb_storage_restriction: false,
      required_device_compliance_level: 'audit',
      blocked_app_action: 'close',
    };

    setFormData({
      id: rule._id,
      name: rule.name,
      description: rule.description || '',
      batchId: rule.batch_id || rule.batchId || '',
      deviceRequirements: {
        require_agent_enrolled: !!dev.require_agent_enrolled,
        require_website_filtering: !!dev.require_website_filtering,
        require_application_control: !!dev.require_application_control,
        require_managed_browser: !!dev.require_managed_browser,
        require_usb_storage_restriction: !!dev.require_usb_storage_restriction,
        required_device_compliance_level: dev.required_device_compliance_level || 'audit',
        blocked_app_action: dev.blocked_app_action || 'close',
      },
    });
    setIsModalOpen(true);
  };

  const handleSavePolicy = async (andPublish: boolean = false) => {
    if (!formData.name.trim()) {
      alert('Policy name is required.');
      return;
    }
    if (!formData.batchId) {
      alert('Please select a batch for this policy.');
      return;
    }

    const { websites: allowedWebs, apps: allowedAppsList } = parseRuleList(allowedText);
    const { websites: blockedWebs, apps: blockedAppsList } = parseRuleList(blockedText);

    const payload = {
      name: formData.name.trim(),
      description: formData.description.trim(),
      batch_id: formData.batchId && formData.batchId !== 'all' ? formData.batchId : undefined,
      allowed_websites: allowedWebs,
      blocked_websites: blockedWebs,
      allowed_applications: allowedAppsList,
      blocked_applications: blockedAppsList,
      require_agent_enrolled: formData.deviceRequirements.require_agent_enrolled,
      require_dns_or_content_filter: formData.deviceRequirements.require_website_filtering,
      require_application_control: formData.deviceRequirements.require_application_control,
      require_managed_browser_policy: formData.deviceRequirements.require_managed_browser,
      require_usb_storage_restriction: formData.deviceRequirements.require_usb_storage_restriction,
      required_enforcement_level: formData.deviceRequirements.required_device_compliance_level || 'audit',
      blocked_app_action: formData.deviceRequirements.blocked_app_action || 'close',
    };

    try {
      let savedRuleSet: RuleSet;
      if (formData.id) {
        savedRuleSet = await updateRule(formData.id, payload);
      } else {
        savedRuleSet = await createRule(payload);
      }

      const targetId = savedRuleSet._id || savedRuleSet.id;
      if (andPublish && targetId) {
        await publishRuleSet(targetId);
      }

      setIsModalOpen(false);
      await fetchAll();
    } catch (e: any) {
      alert(e.message || 'Failed to save policy rule set.');
    }
  };

  const handlePublish = async (ruleSetId: string) => {
    if (!window.confirm('Are you sure you want to publish this policy version? Once published, this version becomes immutable and signed with Ed25519.')) {
      return;
    }
    setPublishingId(ruleSetId);
    try {
      await publishRuleSet(ruleSetId);
      await fetchAll();
    } catch (e: any) {
      alert(e.message || 'Failed to publish policy rule set.');
    } finally {
      setPublishingId(null);
    }
  };

  const handleRevoke = async (ruleSetId: string) => {
    if (!window.confirm('Are you sure you want to REVOKE this policy? Active devices will transition to fallback protection.')) {
      return;
    }
    try {
      await revokeRuleSet(ruleSetId);
      await fetchAll();
    } catch (e: any) {
      alert(e.message || 'Failed to revoke policy rule set.');
    }
  };

  const handleDelete = async (ruleSetId: string) => {
    if (!window.confirm('Are you sure you want to delete this policy draft?')) {
      return;
    }
    try {
      await deleteRule(ruleSetId);
      await fetchAll();
    } catch (e: any) {
      alert(e.message || 'Failed to delete rule set.');
    }
  };

  const openAssignModal = (rule: RuleSet) => {
    setSelectedRuleSetForAssign(rule);
    // Find eligible sessions belonging to rule's batch
    const eligibleSessions = sessions.filter(
      (s) => s.batchIds?.includes(rule.batch_id || rule.batchId || '') && String(s.status).toLowerCase() !== 'completed'
    );
    setTargetSessionId(eligibleSessions.length > 0 ? eligibleSessions[0]._id : '');
    setAssignModalOpen(true);
  };

  const handleAssignToSession = async () => {
    if (!selectedRuleSetForAssign || !targetSessionId) return;
    setIsAssigning(true);
    try {
      await assignRuleSetToSession(targetSessionId, selectedRuleSetForAssign._id);
      alert('Policy successfully assigned to session!');
      setAssignModalOpen(false);
      await fetchAll();
    } catch (e: any) {
      alert(e.message || 'Failed to assign policy to session.');
    } finally {
      setIsAssigning(false);
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
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Batch & Session Policies</h1>
          <p className="text-slate-500 dark:text-slate-400">
            Define cryptographically signed policies for websites, applications, and managed device requirements.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {batches.length > 0 && (
            <Select
              options={[
                { value: 'all', label: 'All Batches Policies' },
                ...batches.map((b) => ({ value: b._id || (b as any).id, label: `Batch: ${b.name}` })),
              ]}
              value={selectedBatchId}
              onChange={(e) => handleBatchFilterChange(e.target.value)}
              className="w-56"
            />
          )}
          <Button icon={<Plus size={18} />} onClick={openCreateModal}>
            Create Session Policy
          </Button>
        </div>
      </div>

      {/* Security & Managed Compliance Notice */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl p-4 flex items-start gap-3">
          <ShieldCheck className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" size={20} />
          <div>
            <h4 className="text-sm font-semibold text-emerald-900 dark:text-emerald-200">Protected System Processes Active</h4>
            <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-0.5">
              Core system processes (<code className="bg-emerald-100 dark:bg-emerald-900 px-1 py-0.5 rounded">explorer.exe</code>, <code className="bg-emerald-100 dark:bg-emerald-900 px-1 py-0.5 rounded">svchost.exe</code>), Windows accessibility tools, and Academia Shield binaries (<code className="bg-emerald-100 dark:bg-emerald-900 px-1 py-0.5 rounded">acad_agent.exe</code>) are guarded against termination. Arbitrary scripts and shell executions are rejected.
            </p>
          </div>
        </div>

        <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl p-4 flex items-start gap-3">
          <Usb className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" size={20} />
          <div>
            <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200">Honest Managed Device Compliance</h4>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
              USB and removable storage restrictions require managed device posture. On personal or unmanaged machines, the agent audits and truthfully reports compliance as <code className="bg-amber-100 dark:bg-amber-900 px-1 py-0.5 rounded">Requires Managed Device</code> without deploying unstable kernel drivers.
            </p>
          </div>
        </div>
      </div>

      {/* Policy Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {rules.map((rule) => {
          const isDraft = rule.status === 'draft';
          const isPublished = rule.status === 'published';
          const isRevoked = rule.status === 'revoked';
          const batchObj = batches.find((b) => (b._id || (b as any).id) === (rule.batch_id || rule.batchId));
          const assignedSession = sessions.find((s) => s.ruleSetId === rule._id || s._id === rule.session_id);

          return (
            <Card key={rule._id} className="flex flex-col h-full border border-slate-200 dark:border-slate-800 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-2">
                <div className="min-w-0 flex-1 pr-2">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white truncate">{rule.name}</h3>
                  <p className="text-xs text-slate-500 truncate">{rule.description || 'Session security policy'}</p>
                </div>
                <div className="flex gap-1.5 items-center shrink-0">
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded border uppercase ${
                      isPublished
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800'
                        : isDraft
                        ? 'bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800'
                        : 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'
                    }`}
                  >
                    {rule.status}
                  </span>
                  <span className="bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300 text-xs font-bold px-2 py-0.5 rounded border border-brand-200 dark:border-brand-800">
                    v{rule.version}
                  </span>
                </div>
              </div>

              {/* Batch & Session Association */}
              <div className="flex flex-wrap gap-2 text-xs text-slate-600 dark:text-slate-400 mb-3">
                <span className="inline-flex items-center gap-1 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                  <Layers size={12} /> {batchObj ? batchObj.name : 'All Batches'}
                </span>
                {assignedSession && (
                  <span className="inline-flex items-center gap-1 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 px-2 py-0.5 rounded">
                    <Calendar size={12} /> Session: {assignedSession.title}
                  </span>
                )}
              </div>

              {/* SHA-256 Integrity Hash Badge */}
              {rule.policy_hash && (
                <div className="mb-3">
                  <span className="inline-flex items-center gap-1 text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded truncate max-w-full">
                    <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
                    <span className="truncate">SHA256: {rule.policy_hash.slice(0, 16)}...</span>
                  </span>
                </div>
              )}

              {/* Rules Summary */}
              <div className="space-y-3 flex-1 text-xs">
                {/* Allowed Academic Websites */}
                <div>
                  <div className="flex items-center justify-between text-slate-500 mb-1">
                    <span className="font-semibold flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <Globe size={13} /> Allowed Academic Websites ({rule.allowed_websites?.length || 0})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(rule.allowed_websites || []).slice(0, 3).map((w, i) => (
                      <span key={i} className="bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
                        {w}
                      </span>
                    ))}
                    {(rule.allowed_websites?.length || 0) > 3 && (
                      <span className="text-slate-400">+{rule.allowed_websites!.length - 3} more</span>
                    )}
                    {(!rule.allowed_websites || rule.allowed_websites.length === 0) && (
                      <span className="text-slate-400 italic">None configured</span>
                    )}
                  </div>
                </div>

                {/* Blocked Websites */}
                <div>
                  <div className="flex items-center justify-between text-slate-500 mb-1">
                    <span className="font-semibold flex items-center gap-1 text-rose-600 dark:text-rose-400">
                      <Globe size={13} /> Blocked Websites ({rule.blocked_websites?.length || 0})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(rule.blocked_websites || []).slice(0, 3).map((w, i) => (
                      <span key={i} className="bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 px-2 py-0.5 rounded border border-rose-200 dark:border-rose-800">
                        {w}
                      </span>
                    ))}
                    {(rule.blocked_websites?.length || 0) > 3 && (
                      <span className="text-slate-400">+{rule.blocked_websites!.length - 3} more</span>
                    )}
                    {(!rule.blocked_websites || rule.blocked_websites.length === 0) && (
                      <span className="text-slate-400 italic">None configured</span>
                    )}
                  </div>
                </div>

                {/* Allowed Academic Applications */}
                <div>
                  <div className="flex items-center justify-between text-slate-500 mb-1">
                    <span className="font-semibold flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <Laptop size={13} /> Allowed Applications ({rule.allowed_applications?.length || 0})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(rule.allowed_applications || []).slice(0, 3).map((a, i) => (
                      <span key={i} className="bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded border border-emerald-200 dark:border-emerald-800 font-mono">
                        {a}
                      </span>
                    ))}
                    {(rule.allowed_applications?.length || 0) > 3 && (
                      <span className="text-slate-400">+{rule.allowed_applications!.length - 3} more</span>
                    )}
                    {(!rule.allowed_applications || rule.allowed_applications.length === 0) && (
                      <span className="text-slate-400 italic">None configured</span>
                    )}
                  </div>
                </div>

                {/* Blocked Applications */}
                <div>
                  <div className="flex items-center justify-between text-slate-500 mb-1">
                    <span className="font-semibold flex items-center gap-1 text-rose-600 dark:text-rose-400">
                      <Laptop size={13} /> Blocked Applications ({rule.blocked_applications?.length || 0})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(rule.blocked_applications || []).slice(0, 3).map((a, i) => (
                      <span key={i} className="bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 px-2 py-0.5 rounded border border-rose-200 dark:border-rose-800 font-mono">
                        {a}
                      </span>
                    ))}
                    {(rule.blocked_applications?.length || 0) > 3 && (
                      <span className="text-slate-400">+{rule.blocked_applications!.length - 3} more</span>
                    )}
                    {(!rule.blocked_applications || rule.blocked_applications.length === 0) && (
                      <span className="text-slate-400 italic">None configured</span>
                    )}
                  </div>
                </div>

                {/* Device Requirements Badges */}
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex flex-wrap gap-1.5">
                  {rule.device_requirements?.require_usb_storage_restriction && (
                    <span className="bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1">
                      <Usb size={10} /> USB Restricted (Managed)
                    </span>
                  )}
                  {rule.device_requirements?.require_website_filtering && (
                    <span className="bg-blue-100 dark:bg-blue-950/60 text-blue-800 dark:text-blue-300 px-2 py-0.5 rounded text-[10px] font-semibold">
                      DNS Filtering
                    </span>
                  )}
                  {rule.device_requirements?.require_application_control && (
                    <span className="bg-purple-100 dark:bg-purple-950/60 text-purple-800 dark:text-purple-300 px-2 py-0.5 rounded text-[10px] font-semibold">
                      App Control ({rule.device_requirements.blocked_app_action || 'close'})
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex flex-col gap-2">
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="flex-1"
                    icon={<Edit2 size={14} />}
                    onClick={() => openEditModal(rule)}
                  >
                    {isPublished ? 'Branch New Draft' : 'Edit Draft'}
                  </Button>
                  {isDraft && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="text-gray-400 hover:text-red-400 transition-colors"
                      icon={<Trash2 size={14} />}
                      onClick={() => handleDelete(rule._id)}
                    >
                      Delete
                    </Button>
                  )}
                </div>

                {isDraft && (
                  <Button
                    size="sm"
                    variant="primary"
                    className="w-full"
                    icon={<Send size={14} />}
                    disabled={publishingId === rule._id}
                    onClick={() => handlePublish(rule._id)}
                  >
                    {publishingId === rule._id ? 'Signing & Publishing...' : 'Publish & Sign Policy'}
                  </Button>
                )}

                {isPublished && (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      className="flex-1 text-indigo-600 dark:text-indigo-400"
                      icon={<Calendar size={14} />}
                      onClick={() => openAssignModal(rule)}
                    >
                      Assign to Session
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50"
                      icon={<RotateCcw size={14} />}
                      onClick={() => handleRevoke(rule._id)}
                    >
                      Revoke
                    </Button>
                  </div>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {/* ─── Policy Creation & Edit Tabbed Modal ─── */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={isEditing ? `Edit Policy Draft: ${formData.name || 'Untitled'}` : 'Create New Batch Session Policy'}
        footer={
          <div className="flex justify-between w-full">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => handleSavePolicy(false)}>
                Save as Draft
              </Button>
              <Button variant="primary" onClick={() => handleSavePolicy(true)}>
                Publish & Sign Policy
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-4 max-h-[72vh] overflow-y-auto pr-1">
          {/* Top metadata */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Policy Name *"
              placeholder="e.g. Distributed Systems Lab Lockdown"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
            <Select
              label="Assigned Batch *"
              options={batches.map((b) => ({ value: b._id || (b as any).id, label: `${b.name} (${b.code || 'Batch'})` }))}
              value={formData.batchId}
              onChange={(e) => setFormData({ ...formData, batchId: e.target.value })}
              disabled={batches.length === 0}
            />
          </div>

          <Input
            label="Description"
            placeholder="Policy objectives and allowed tools description"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />

          {/* ─── 2 Simple Text Boxes: 1. Allow Websites & Apps, 2. Block Websites & Apps ─── */}
          {(() => {
            const parsedAllowed = parseRuleList(allowedText);
            const parsedBlocked = parseRuleList(blockedText);

            return (
              <>
                {/* ─── 1. ALLOWED WEBSITES & APPS TEXT BOX ─── */}
                <div className="space-y-2 p-3.5 rounded-xl border border-emerald-200 dark:border-emerald-800/60 bg-emerald-50/30 dark:bg-emerald-950/20">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300 text-xs font-extrabold">✓</span>
                      Allowed Websites & Applications
                    </label>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300">
                      {parsedAllowed.websites.length} website{parsedAllowed.websites.length === 1 ? '' : 's'}, {parsedAllowed.apps.length} app{parsedAllowed.apps.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    Enter allowed websites (e.g. <code className="text-emerald-700 dark:text-emerald-300 font-mono">docs.python.org</code>, <code className="text-emerald-700 dark:text-emerald-300 font-mono">coursera.org</code>) and desktop applications (e.g. <code className="text-emerald-700 dark:text-emerald-300 font-mono">Code.exe</code>) — one per line or separated by commas.
                  </p>
                  <textarea
                    rows={4}
                    className="w-full font-mono text-xs p-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 transition-all outline-none"
                    placeholder={"docs.python.org\nstackoverflow.com\nCode.exe\nchrome.exe"}
                    value={allowedText}
                    onChange={(e) => setAllowedText(e.target.value)}
                  />

                  {/* Live detected items badge row */}
                  {(parsedAllowed.websites.length > 0 || parsedAllowed.apps.length > 0) && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {parsedAllowed.websites.map((w) => (
                        <span key={w} className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md bg-emerald-100/70 text-emerald-800 border border-emerald-300 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800">
                          <Globe size={11} className="text-emerald-600 dark:text-emerald-400" />
                          {w}
                        </span>
                      ))}
                      {parsedAllowed.apps.map((a) => (
                        <span key={a} className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md bg-teal-100/70 text-teal-800 border border-teal-300 dark:bg-teal-950 dark:text-teal-300 dark:border-teal-800">
                          <Laptop size={11} className="text-teal-600 dark:text-teal-400" />
                          {a}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* ─── 2. BLOCKED WEBSITES & APPS TEXT BOX ─── */}
                <div className="space-y-2 p-3.5 rounded-xl border border-rose-200 dark:border-rose-800/60 bg-rose-50/30 dark:bg-rose-950/20">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300 text-xs font-extrabold">✕</span>
                      Blocked Websites & Applications
                    </label>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-300">
                      {parsedBlocked.websites.length} website{parsedBlocked.websites.length === 1 ? '' : 's'}, {parsedBlocked.apps.length} app{parsedBlocked.apps.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    Enter blocked websites (e.g. <code className="text-rose-700 dark:text-rose-300 font-mono">reddit.com</code>, <code className="text-rose-700 dark:text-rose-300 font-mono">youtube.com</code>) and desktop applications (e.g. <code className="text-rose-700 dark:text-rose-300 font-mono">discord.exe</code>, <code className="text-rose-700 dark:text-rose-300 font-mono">spotify.exe</code>) — one per line or separated by commas.
                  </p>
                  <textarea
                    rows={4}
                    className="w-full font-mono text-xs p-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-rose-500 focus:border-rose-500 transition-all outline-none"
                    placeholder={"facebook.com\ninstagram.com\ndiscord.exe\nspotify.exe"}
                    value={blockedText}
                    onChange={(e) => setBlockedText(e.target.value)}
                  />

                  {/* Live detected items badge row */}
                  {(parsedBlocked.websites.length > 0 || parsedBlocked.apps.length > 0) && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {parsedBlocked.websites.map((w) => (
                        <span key={w} className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md bg-rose-100/70 text-rose-800 border border-rose-300 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-800">
                          <Globe size={11} className="text-rose-600 dark:text-rose-400" />
                          {w}
                        </span>
                      ))}
                      {parsedBlocked.apps.map((a) => (
                        <span key={a} className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md bg-red-100/70 text-red-800 border border-red-300 dark:bg-red-950 dark:text-red-300 dark:border-red-800">
                          <Laptop size={11} className="text-red-600 dark:text-red-400" />
                          {a}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* ─── OPTIONAL ACCORDION: ADVANCED DEVICE CONTROLS ─── */}
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setShowAdvancedDevice(!showAdvancedDevice)}
                    className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-800/60 text-left flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      <Sliders size={14} className="text-brand-500" />
                      Advanced Device & Security Controls
                    </span>
                    <span className="text-[11px] text-slate-500 font-normal">
                      {showAdvancedDevice ? 'Hide ▲' : 'Show (Optional) ▼'}
                    </span>
                  </button>
                  {showAdvancedDevice && (
                    <div className="p-4 space-y-3 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 text-xs">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <label className="flex items-center gap-2.5 cursor-pointer text-slate-700 dark:text-slate-300">
                          <input
                            type="checkbox"
                            checked={formData.deviceRequirements.require_agent_enrolled}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                deviceRequirements: { ...formData.deviceRequirements, require_agent_enrolled: e.target.checked },
                              })
                            }
                            className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                          />
                          <span>Require Local Agent Enrollment</span>
                        </label>
                        <label className="flex items-center gap-2.5 cursor-pointer text-slate-700 dark:text-slate-300">
                          <input
                            type="checkbox"
                            checked={formData.deviceRequirements.require_website_filtering}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                deviceRequirements: { ...formData.deviceRequirements, require_website_filtering: e.target.checked },
                              })
                            }
                            className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                          />
                          <span>Require Website Filtering / DNS</span>
                        </label>
                        <label className="flex items-center gap-2.5 cursor-pointer text-slate-700 dark:text-slate-300">
                          <input
                            type="checkbox"
                            checked={formData.deviceRequirements.require_application_control}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                deviceRequirements: { ...formData.deviceRequirements, require_application_control: e.target.checked },
                              })
                            }
                            className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                          />
                          <span>Require Application Process Control</span>
                        </label>
                        <label className="flex items-center gap-2.5 cursor-pointer text-slate-700 dark:text-slate-300">
                          <input
                            type="checkbox"
                            checked={formData.deviceRequirements.require_usb_storage_restriction}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                deviceRequirements: { ...formData.deviceRequirements, require_usb_storage_restriction: e.target.checked },
                              })
                            }
                            className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                          />
                          <span>Require USB Storage Restriction (Managed)</span>
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              </>
            );
          })()}
        </div>
      </Modal>

      {/* ─── Assign Policy to Session Modal ─── */}
      <Modal
        isOpen={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        title={`Assign Policy: ${selectedRuleSetForAssign?.name || ''}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={isAssigning || !targetSessionId} onClick={handleAssignToSession}>
              {isAssigning ? 'Assigning...' : 'Assign to Session'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Select an active or scheduled session in this batch to enforce this signed policy version.
          </p>

          {sessions.filter(
            (s) =>
              s.batchIds?.includes(selectedRuleSetForAssign?.batch_id || selectedRuleSetForAssign?.batchId || '') &&
              String(s.status).toLowerCase() !== 'completed'
          ).length === 0 ? (
            <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-lg text-xs text-amber-800 dark:text-amber-300">
              No upcoming or active sessions found for this batch. Please schedule a session first in the Sessions tab.
            </div>
          ) : (
            <Select
              label="Select Session"
              options={sessions
                .filter(
                  (s) =>
                    s.batchIds?.includes(selectedRuleSetForAssign?.batch_id || selectedRuleSetForAssign?.batchId || '') &&
                    String(s.status).toLowerCase() !== 'completed'
                )
                .map((s) => ({
                  value: s._id,
                  label: `${s.title} (${s.type} - ${s.status})`,
                }))}
              value={targetSessionId}
              onChange={(e) => setTargetSessionId(e.target.value)}
            />
          )}
        </div>
      </Modal>
    </div>
  );
};