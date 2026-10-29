import React, { useEffect, useState } from 'react';
import { EnrolledDevice, getEnrolledDevices, issueEnrollmentClaim, revokeEnrolledDevice } from '../lib/api';
import { Button } from './ui/Button';

export const DeviceEnrollmentPanel: React.FC = () => {
  const [devices, setDevices] = useState<EnrolledDevice[]>([]);
  const [claim, setClaim] = useState<{ claim: string; expiresAt: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = async () => {
    try { setDevices(await getEnrolledDevices()); } catch (e: any) { setError(e.message || 'Could not load devices'); }
  };
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (!claim) return;
    const timer = setTimeout(() => setClaim(null), Math.max(0, new Date(claim.expiresAt).getTime() - Date.now()));
    return () => clearTimeout(timer);
  }, [claim]);

  const issue = async () => {
    setBusy(true); setError('');
    try { setClaim(await issueEnrollmentClaim()); }
    catch (e: any) { setError(e.message || 'Could not create enrollment code'); }
    finally { setBusy(false); }
  };
  const revoke = async (id: string) => {
    setBusy(true); setError('');
    try { await revokeEnrolledDevice(id); await refresh(); }
    catch (e: any) { setError(e.message || 'Could not revoke device'); }
    finally { setBusy(false); }
  };
  const enrollLocalAgent = async () => {
    if (!claim || !window.academiaDesktop) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await window.academiaDesktop.enrollAgent(claim.claim);
      if (!result.ok) throw new Error(result.error || 'Enrollment failed');
      setClaim(null);
      setNotice('Device enrolled. The agent starts at your next Windows sign-in.');
      await refresh();
    } catch (e: any) { setError(e.message || 'Could not enroll this device'); }
    finally { setBusy(false); }
  };

  return <section className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 space-y-3">
    <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Local agent enrollment</h2>
    <p className="text-sm text-slate-600 dark:text-slate-300">{window.academiaDesktop ? 'The desktop installer includes the local agent. Generate a one-time code to enroll this computer.' : 'Install the Windows agent on your own laptop, then enter a one-time code locally. The code expires after 10 minutes.'}</p>
    <p className="text-sm text-slate-600 dark:text-slate-300">Sessions of batches you joined that use Auto enforcement apply their blocking and activity monitoring policy to this device during the scheduled time, without requiring you to mark attendance. Opt-in sessions require you to join first.</p>
    <Button onClick={issue} disabled={busy}>Generate enrollment code</Button>
    <Button variant="ghost" onClick={refresh} disabled={busy}>Refresh devices</Button>
    {claim && <div className="text-sm space-y-1">
      <p className="font-mono break-all text-slate-900 dark:text-white">{claim.claim}</p>
      <p className="text-slate-500">Expires {new Date(claim.expiresAt).toLocaleTimeString()}</p>
      {window.academiaDesktop
        ? <Button onClick={enrollLocalAgent} disabled={busy}>Enroll this computer</Button>
        : <p className="text-slate-500">On the student computer, run <code>AcademiaShield.exe enroll</code> and enter this code at the prompt.</p>}
    </div>}
    {notice && <p role="status" className="text-sm text-emerald-600 dark:text-emerald-400">{notice}</p>}
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    <div className="space-y-2">
      {devices.filter(device => !device.revokedAt).map(device => <div key={device._id} className="flex items-center justify-between gap-3 text-sm text-slate-700 dark:text-slate-200">
        <span>Device {device._id.slice(-6)} · {device.lastSeenAt ? `last seen ${new Date(device.lastSeenAt).toLocaleString()}` : 'waiting for agent'}</span>
        <Button variant="danger" onClick={() => revoke(device._id)} disabled={busy}>Revoke</Button>
      </div>)}
      {!devices.some(device => !device.revokedAt) && <p className="text-sm text-slate-500">No enrolled device yet.</p>}
    </div>
  </section>;
};
