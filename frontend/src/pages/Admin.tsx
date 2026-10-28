import React, { useState, useEffect } from 'react';
import { 
  Shield, 
  Building2, 
  Laptop, 
  FileText, 
  Download, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  Sliders, 
  Usb, 
  Timer, 
  UserCheck,
  Ban,
  Brain,
  Sparkles,
  Cpu,
  Play
} from 'lucide-react';
import { api, getMLModels, approveMLModel, trainMLModel } from '../lib/api';

export const Admin: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'institution' | 'devices' | 'audit' | 'ml'>('institution');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [trainingModel, setTrainingModel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [mlModels, setMlModels] = useState<any[]>([]);

  // Institution Settings State
  const [instSettings, setInstSettings] = useState({
    institution_name: 'Academia Shield Academic Institute',
    allow_usb_blocking: true,
    fail_safe_grace_seconds: 120,
    max_session_duration_minutes: 240,
    require_student_consent: true
  });

  // Devices & Audit Logs State
  const [devices, setDevices] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({
    total_professors: 0,
    total_students: 0,
    total_devices: 0,
    active_devices: 0,
    active_sessions: 0,
    total_violations: 0
  });

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsRes, statsRes, devicesRes, logsRes, modelsRes] = await Promise.all([
        api.get('/api/v1/admin/institution').catch(() => ({ data: {} })),
        api.get('/api/v1/admin/stats').catch(() => ({ data: {} })),
        api.get('/api/v1/admin/devices').catch(() => ({ data: [] })),
        api.get('/api/v1/admin/audit-logs?limit=50').catch(() => ({ data: [] })),
        getMLModels().catch(() => [])
      ]);

      if (settingsRes.data && settingsRes.data.institution_name) {
        setInstSettings(settingsRes.data);
      }
      if (statsRes.data) {
        setStats(statsRes.data);
      }
      setDevices(Array.isArray(devicesRes.data) ? devicesRes.data : []);
      setAuditLogs(Array.isArray(logsRes.data) ? logsRes.data : []);
      setMlModels(Array.isArray(modelsRes) ? modelsRes : []);
    } catch (err: any) {
      setError(err.message || 'Failed to load IT Administrator telemetry.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg(null);
    setError(null);
    try {
      const res = await api.put('/api/v1/admin/institution', instSettings);
      setSuccessMsg('Institution governance policies updated successfully.');
      if (res.data?.settings) {
        setInstSettings(res.data.settings);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update institution settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleRevokeDevice = async (deviceId: string) => {
    if (!confirm('Are you sure you want to revoke this student device? It will be disconnected from the active policy.')) return;
    try {
      await api.post(`/api/v1/agent/devices/${deviceId}/revoke`);
      setSuccessMsg(`Device ${deviceId} revoked successfully.`);
      fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to revoke device.');
    }
  };

  const handleApproveModel = async (modelId: string) => {
    try {
      await approveMLModel(modelId);
      setSuccessMsg(`Model approved and deployed as the ACTIVE live inference model.`);
      fetchData();
    } catch (err: any) {
      setError(err.message || 'Failed to approve model.');
    }
  };

  const handleTrainNewModel = async () => {
    setTrainingModel(true);
    setError(null);
    try {
      const res = await trainMLModel({ n_estimators: 100 });
      const accuracy = res.metrics_json?.accuracy;
      const accuracyMessage = typeof accuracy === 'number'
        ? ` with ${(accuracy * 100).toFixed(1)}% accuracy`
        : '';
      setSuccessMsg(`Trained new model '${res.version_tag}'${accuracyMessage}. Ready for review.`);
      fetchData();
    } catch (err: any) {
      setError(err.message || 'Failed to train ML model.');
    } finally {
      setTrainingModel(false);
    }
  };

  const exportAuditLogs = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(auditLogs, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `academiashield_audit_logs_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
              <Building2 size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                IT Administrator Governance
                <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Institution Active
                </span>
              </h1>
              <p className="text-sm text-slate-400">
                Institutional compliance policies, student device controls, and immutable audit logs.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-sm font-medium transition-all border border-slate-700"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh Metrics
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400">Total Enrolled Devices</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.total_devices}</p>
          <span className="text-xs text-indigo-400 mt-1 block">{stats.active_devices} online & synced</span>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400">Active Classroom Sessions</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">{stats.active_sessions}</p>
          <span className="text-xs text-slate-500 mt-1 block">Live enforcement active</span>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400">Faculty & Students</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.total_professors + stats.total_students}</p>
          <span className="text-xs text-slate-400 mt-1 block">{stats.total_professors} Profs / {stats.total_students} Students</span>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400">Blocked Incidents (Session)</p>
          <p className="text-2xl font-bold text-amber-400 mt-1">{stats.total_violations}</p>
          <span className="text-xs text-slate-500 mt-1 block">Logged to audit trail</span>
        </div>
      </div>

      {/* Notifications */}
      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
          <CheckCircle2 size={18} />
          {successMsg}
        </div>
      )}
      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('institution')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'institution'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          <Sliders size={16} />
          Institution Policies
        </button>
        <button
          onClick={() => setActiveTab('devices')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'devices'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          <Laptop size={16} />
          Enrolled Devices ({devices.length})
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'audit'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          <FileText size={16} />
          Immutable Audit Logs
        </button>
        <button
          onClick={() => setActiveTab('ml')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'ml'
              ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          <Brain size={16} />
          ML Engagement Models ({mlModels.length})
        </button>
      </div>

      {/* Tab 1: Institution Policies */}
      {activeTab === 'institution' && (
        <form onSubmit={handleSaveSettings} className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-white">Global Institutional Compliance</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              These settings enforce baseline safety rules across all faculty sessions in the institution.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Institution Name
              </label>
              <input
                type="text"
                value={instSettings.institution_name}
                onChange={(e) => setInstSettings({ ...instSettings, institution_name: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500"
                required
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Timer size={14} className="text-indigo-400" />
                Fail-Safe Offline Grace Period (Seconds)
              </label>
              <input
                type="number"
                min="30"
                max="600"
                value={instSettings.fail_safe_grace_seconds}
                onChange={(e) => setInstSettings({ ...instSettings, fail_safe_grace_seconds: Number(e.target.value) })}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500"
                required
              />
              <p className="text-xs text-slate-500">
                If student endpoint is disconnected for this duration, temporary classroom restrictions automatically self-terminate.
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Usb size={14} className="text-indigo-400" />
                Removable Storage / Pen Drive Restriction Policy
              </label>
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-white">Enable USB Storage Restrictions for Exams</p>
                  <p className="text-xs text-slate-400">
                    Allows professors to enforce removable disk read/write blocks. Never affects mouse or keyboard.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={instSettings.allow_usb_blocking}
                  onChange={(e) => setInstSettings({ ...instSettings, allow_usb_blocking: e.target.checked })}
                  className="w-5 h-5 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <UserCheck size={14} className="text-indigo-400" />
                Student Transparency & Consent Protocol
              </label>
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-white">Mandatory Active Session Indicator</p>
                  <p className="text-xs text-slate-400">
                    Ensures student desktop agent always displays active restrictions and professor identity openly.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={instSettings.require_student_consent}
                  onChange={(e) => setInstSettings({ ...instSettings, require_student_consent: e.target.checked })}
                  className="w-5 h-5 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-indigo-500"
                />
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t border-slate-800">
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold transition-all shadow-lg shadow-indigo-600/20 disabled:opacity-50"
            >
              {saving ? 'Saving Changes...' : 'Save Institution Configuration'}
            </button>
          </div>
        </form>
      )}

      {/* Tab 2: Enrolled Devices */}
      {activeTab === 'devices' && (
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Approved & Enrolled Student Endpoints</h2>
              <p className="text-xs text-slate-400">
                All devices enrolled through institutional identity or single-use verification tokens.
              </p>
            </div>
          </div>

          {devices.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-sm">
              No student devices currently registered.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                  <tr>
                    <th className="py-3 px-4">Device Identifier</th>
                    <th className="py-3 px-4">Student</th>
                    <th className="py-3 px-4">Platform</th>
                    <th className="py-3 px-4">Agent Version</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Last Seen</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                  {devices.map((d) => (
                    <tr key={d.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-4 text-white font-semibold">{d.device_identifier}</td>
                      <td className="py-3 px-4 font-sans text-sm">
                        <p className="text-white">{d.student?.name || 'Unassigned'}</p>
                        <p className="text-xs text-slate-500">{d.student?.roll || d.student?.email}</p>
                      </td>
                      <td className="py-3 px-4 capitalize font-sans">{d.platform}</td>
                      <td className="py-3 px-4 text-indigo-300">v{d.agent_version}</td>
                      <td className="py-3 px-4 font-sans">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          d.is_active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-slate-800 text-slate-400'
                        }`}>
                          {d.is_active ? 'Enrolled / Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-sans">
                        {d.last_seen_at ? new Date(d.last_seen_at).toLocaleTimeString() : 'Never'}
                      </td>
                      <td className="py-3 px-4 text-right font-sans">
                        {d.is_active && (
                          <button
                            onClick={() => handleRevokeDevice(d.id)}
                            className="px-3 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-medium transition-all"
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Immutable Audit Logs */}
      {activeTab === 'audit' && (
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Immutable Institutional Audit Trail</h2>
              <p className="text-xs text-slate-400">
                Cryptographically verifiable record of policy creations, session state transitions, and security incidents.
              </p>
            </div>
            <button
              onClick={exportAuditLogs}
              className="flex items-center gap-2 px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-medium transition-all"
            >
              <Download size={14} />
              Export JSON
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                <tr>
                  <th className="py-3 px-4">Timestamp (UTC)</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Actor</th>
                  <th className="py-3 px-4">Entity Type</th>
                  <th className="py-3 px-4">Audit Metadata</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-xs font-mono">
                {auditLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-semibold text-indigo-300">{log.action}</span>
                    </td>
                    <td className="py-3 px-4 text-white font-sans">{log.actor_name}</td>
                    <td className="py-3 px-4 text-slate-400">{log.entity_type}</td>
                    <td className="py-3 px-4 text-slate-500 truncate max-w-xs font-sans">
                      {JSON.stringify(log.metadata)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 4: ML Engagement Models */}
      {activeTab === 'ml' && (
        <div className="space-y-6">
          <div className="p-6 rounded-2xl bg-gradient-to-r from-indigo-950/40 via-purple-950/20 to-slate-900 border border-indigo-500/20">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-indigo-400 font-semibold text-sm">
                  <Brain size={18} />
                  <span>Privacy-Preserving Machine Learning Engine</span>
                </div>
                <h2 className="text-xl font-bold text-white">Student Engagement Classification Models</h2>
                <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
                  Academia Shield analyzes 5-minute rolling window telemetry (focus stability, window switching rhythm, keystroke cadence, and academic window ratio) without logging sensitive keystrokes or content.
                  Active models automatically infer student engagement levels (High, Medium, Low) in live faculty monitoring sessions.
                </p>
              </div>
              <button
                onClick={handleTrainNewModel}
                disabled={trainingModel}
                className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold transition-all shadow-lg shadow-indigo-600/20 disabled:opacity-50"
              >
                {trainingModel ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" />
                    Training Model...
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    Train New Model Version
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Model Registry Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {mlModels.map((model) => {
              const metrics = model.metrics_json || {};
              const accuracy = typeof metrics.accuracy === 'number' ? (metrics.accuracy * 100).toFixed(1) : 'N/A';
              const f1 = typeof metrics.f1_macro === 'number' ? (metrics.f1_macro * 100).toFixed(1) : 'N/A';
              const isApproved = model.status === 'approved';
              const isDraft = model.status === 'draft';

              return (
                <div
                  key={model.id}
                  className={`p-5 rounded-2xl border transition-all ${
                    isApproved
                      ? 'bg-slate-900/90 border-emerald-500/40 ring-1 ring-emerald-500/20 shadow-lg shadow-emerald-950/20'
                      : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <div className={`p-2 rounded-xl ${isApproved ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-slate-800 text-slate-400'}`}>
                        <Cpu size={20} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-bold text-white text-base font-mono">
                            v{model.version_tag}
                          </h3>
                          {isApproved && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                              Active in Production
                            </span>
                          )}
                          {isDraft && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              Draft / Candidate
                            </span>
                          )}
                          {model.status === 'retired' && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-500 border border-slate-700">
                              Retired
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5">{model.algorithm}</p>
                      </div>
                    </div>

                    {isDraft && (
                      <button
                        onClick={() => handleApproveModel(model.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition-all shadow-sm"
                      >
                        <Play size={12} fill="currentColor" />
                        Deploy to Live
                      </button>
                    )}
                  </div>

                  {/* Metrics Row */}
                  <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-slate-800/80">
                    <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/60 text-center">
                      <p className="text-[10px] font-medium text-slate-400 uppercase">Accuracy</p>
                      <p className="text-base font-bold text-emerald-400 mt-0.5">{accuracy}%</p>
                    </div>
                    <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/60 text-center">
                      <p className="text-[10px] font-medium text-slate-400 uppercase">Macro F1</p>
                      <p className="text-base font-bold text-indigo-400 mt-0.5">{f1}%</p>
                    </div>
                    <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/60 text-center">
                      <p className="text-[10px] font-medium text-slate-400 uppercase">Status</p>
                      <p className="text-xs font-semibold text-slate-300 mt-1 capitalize">{model.status}</p>
                    </div>
                  </div>

                  {/* Metadata & File Path */}
                  <div className="mt-4 pt-3 border-t border-slate-800/60 text-xs text-slate-500 space-y-1">
                    <div className="flex items-center justify-between">
                      <span>Artifact:</span>
                      <span className="font-mono text-slate-400 truncate max-w-[240px]" title={model.artifact_path}>
                        {model.artifact_path}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Trained By:</span>
                      <span className="text-slate-400">{model.trained_by || 'System Automated'}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Registered:</span>
                      <span className="text-slate-400">{new Date(model.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {mlModels.length === 0 && (
            <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 text-slate-400 space-y-3">
              <Brain size={40} className="mx-auto text-slate-600" />
              <p className="font-medium text-slate-300">No ML models registered yet</p>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Click "Train New Model Version" above to initialize a RandomForestClassifier with baseline engagement telemetry data.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
