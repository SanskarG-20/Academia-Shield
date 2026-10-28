import React, { useEffect, useState } from 'react';
import { Card } from './ui/Card';
import { Button } from './ui/Button';
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Download,
  Copy,
  Check,
  RefreshCw,
  Laptop,
  Apple,
  Terminal,
  Clock,
  KeyRound,
  AlertCircle,
  CheckCircle2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { generateEnrollmentToken, getAgentReleasesLatest, getMyDeviceStatus } from '../lib/api';

export const DeviceProtectionAgent: React.FC = () => {
  const [deviceStatus, setDeviceStatus] = useState<any>(null);
  const [releases, setReleases] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedOs, setSelectedOs] = useState<'windows' | 'macos'>('windows');
  const [enrollmentToken, setEnrollmentToken] = useState<string | null>(null);
  const [tokenExpiresAt, setTokenExpiresAt] = useState<string | null>(null);
  const [tokenTimeLeft, setTokenTimeLeft] = useState<number>(0);
  const [generatingToken, setGeneratingToken] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);

  // Detect platform from navigator.userAgent
  useEffect(() => {
    const userAgent = window.navigator.userAgent.toLowerCase();
    if (userAgent.includes('mac')) {
      setSelectedOs('macos');
    } else {
      setSelectedOs('windows');
    }
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [statusRes, releaseRes] = await Promise.all([
        getMyDeviceStatus().catch(() => null),
        getAgentReleasesLatest().catch(() => null),
      ]);
      setDeviceStatus(statusRes);
      setReleases(releaseRes);
    } catch (err) {
      console.error('Failed to load agent info', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000); // Polling every 15s for live agent heartbeat
    return () => clearInterval(interval);
  }, []);

  // Token countdown timer
  useEffect(() => {
    if (!tokenExpiresAt) return;
    const updateCountdown = () => {
      const remaining = Math.max(0, Math.floor((new Date(tokenExpiresAt).getTime() - Date.now()) / 1000));
      setTokenTimeLeft(remaining);
    };
    updateCountdown();
    const timer = setInterval(updateCountdown, 1000);
    return () => clearInterval(timer);
  }, [tokenExpiresAt]);

  const handleGenerateToken = async () => {
    try {
      setGeneratingToken(true);
      const res = await generateEnrollmentToken();
      setEnrollmentToken(res.enrollment_token);
      setTokenExpiresAt(res.expires_at);
      setCopiedToken(false);
    } catch (err: any) {
      alert(err.message || 'Failed to generate enrollment token');
    } finally {
      setGeneratingToken(false);
    }
  };

  const handleCopyToken = () => {
    if (enrollmentToken) {
      navigator.clipboard.writeText(enrollmentToken);
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2000);
    }
  };

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  const activeRelease = releases?.releases?.[selectedOs];
  const isInstalled = deviceStatus?.is_installed;
  const isEnrolled = deviceStatus?.is_enrolled;
  const isOnline = deviceStatus?.is_online;
  const agentState = deviceStatus?.agent_state || 'NOT_INSTALLED';

  const getStateBadgeColor = (state: string) => {
    switch (state) {
      case 'ENFORCING':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'ENROLLED_IDLE':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'WAITING_FOR_STUDENT_JOIN':
      case 'WAITING_FOR_SESSION':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'RESTORING':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case 'ERROR':
        return 'bg-red-500/20 text-red-400 border-red-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  return (
    <div className="space-y-6">
      <Card title="Device Protection Agent">
        {/* Status Dashboard Header */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 rounded-xl bg-slate-100/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 mb-6">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-lg ${isInstalled ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500'}`}>
              <Shield size={22} />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Installation</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {isInstalled ? 'Agent Installed' : 'Not Installed'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-lg ${isEnrolled ? 'bg-blue-500/10 text-blue-500' : 'bg-slate-500/10 text-slate-500'}`}>
              <Laptop size={22} />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Device Enrollment</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {isEnrolled ? 'Enrolled & Verified' : 'Not Enrolled'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-lg ${isOnline ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-500/10 text-slate-500'}`}>
              {isOnline ? <Wifi size={22} className="animate-pulse" /> : <WifiOff size={22} />}
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Connectivity</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {isOnline ? 'Connected (Live)' : 'Offline / Idle'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-500">
              <ShieldCheck size={22} />
            </div>
            <div>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Agent State</p>
              <span className={`inline-flex items-center px-2 py-0.5 mt-0.5 rounded text-xs font-medium border ${getStateBadgeColor(agentState)}`}>
                {agentState.replace(/_/g, ' ')}
              </span>
            </div>
          </div>
        </div>

        {/* Registered Device Details (if available) */}
        {deviceStatus?.device && (
          <div className="mb-6 p-4 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/60 text-xs">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-slate-600 dark:text-slate-300">
              <div>
                <span className="text-slate-400 block">Device Name:</span>
                <span className="font-semibold text-slate-900 dark:text-white">{deviceStatus.device.device_name}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Platform:</span>
                <span className="capitalize">{deviceStatus.device.platform} {deviceStatus.device.platform_version || ''}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Agent Version:</span>
                <span className="font-mono">{deviceStatus.device.agent_version}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Last Heartbeat:</span>
                <span>{deviceStatus.device.last_seen_at ? new Date(deviceStatus.device.last_seen_at).toLocaleTimeString() : 'Never'}</span>
              </div>
            </div>
          </div>
        )}

        {/* OS Platform Selector */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3 mb-4">
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedOs('windows')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedOs === 'windows'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <Laptop size={16} />
              Windows Agent
            </button>
            <button
              onClick={() => setSelectedOs('macos')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedOs === 'macos'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <Apple size={16} />
              macOS Agent
            </button>
          </div>

          <span className="text-xs text-slate-500">
            Detected: <strong className="capitalize">{window.navigator.userAgent.toLowerCase().includes('mac') ? 'macOS' : 'Windows'}</strong>
          </span>
        </div>

        {/* Installer Download Card */}
        {activeRelease ? (
          <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h4 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  Academia Shield {selectedOs === 'windows' ? 'Windows Setup' : 'macOS Package'} v{activeRelease.version}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  Supported: {activeRelease.min_os_version} | Digital Signature Verified (Ed25519)
                </p>
              </div>

              <a
                href={activeRelease.download_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg shadow-sm transition-all"
              >
                <Download size={16} />
                Download {selectedOs === 'windows' ? '.exe Installer' : '.pkg Package'}
              </a>
            </div>

            {/* SHA-256 Package Hash */}
            <div className="p-2.5 rounded-lg bg-slate-100 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 overflow-hidden">
                <span className="font-mono text-slate-400 shrink-0">SHA-256:</span>
                <span className="font-mono text-slate-700 dark:text-slate-300 truncate select-all">{activeRelease.sha256}</span>
              </div>
              <button
                onClick={() => handleCopyHash(activeRelease.sha256)}
                className="p-1 text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 shrink-0 ml-2"
                title="Copy SHA-256 Hash"
              >
                {copiedHash ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
              </button>
            </div>
          </div>
        ) : (
          <div className="p-4 text-center text-sm text-slate-500">Loading release information...</div>
        )}

        {/* One-Time Enrollment Flow */}
        <div className="mt-6 pt-6 border-t border-slate-200 dark:border-slate-800">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <div>
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                <KeyRound size={16} className="text-brand-500" />
                One-Time Device Enrollment Token
              </h4>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Generate a single-use code to link the installed desktop agent to your student profile.
              </p>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleGenerateToken}
              disabled={generatingToken}
              className="shrink-0"
            >
              {generatingToken ? 'Generating...' : 'Generate New Token'}
            </Button>
          </div>

          {enrollmentToken && (
            <div className="p-4 rounded-xl bg-brand-50 dark:bg-brand-950/30 border border-brand-200 dark:border-brand-900/50 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-brand-800 dark:text-brand-300">
                  Your One-Time Setup Code (Expires in {Math.floor(tokenTimeLeft / 60)}:{(tokenTimeLeft % 60).toString().padStart(2, '0')}):
                </span>
                <span className="text-xs text-slate-500">Single-use only</span>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex-1 text-center font-mono text-2xl tracking-widest font-bold py-3 bg-white dark:bg-slate-900 rounded-lg border border-brand-300 dark:border-brand-800 text-brand-600 dark:text-brand-400 select-all">
                  {enrollmentToken}
                </div>
                <Button variant="primary" onClick={handleCopyToken} className="h-12 px-5">
                  {copiedToken ? <Check size={18} /> : <Copy size={18} />}
                </Button>
              </div>

              <p className="text-xs text-slate-600 dark:text-slate-400">
                Open Academia Shield on your computer and paste this code when prompted.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
