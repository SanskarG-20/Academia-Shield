# Agent device-safety audit

Scope: the current `main` Python agent, installer, hosts/DNS recovery, application handling, activity capture, cached policy, and the backend policy path. This audit used code inspection, API unit mocks, and temporary files. It did not install the executable, change the real Windows hosts/DNS settings, or run live end-to-end tests.

## Major findings and changes

| Risk found | Change made |
| --- | --- |
| `psutil.terminate()` could kill applications with unsaved work or match system processes. | App rules now request `WM_CLOSE` only for exact `.exe` names, current-user GUI windows outside the Windows directory, with protected process exclusions and a per-process cooldown. No process is force-killed. A save prompt may keep the app open. Reports say `APP_CLOSE_REQUESTED`. |
| DNS redirection to a local resolver could interrupt all name resolution if its thread or the agent died. | New DNS redirection is disabled, including direct calls to the old engine. Hosts mode remains active. Legacy DNS backups are still restored conservatively; invalid or unreadable backups remain for manual recovery. |
| A crashed agent could leave managed hosts entries after policy expiry. | Installation creates a separate `--recover` task every minute. It checks the HMAC-protected, device-bound cached policy without network access and restores managed hosts/legacy DNS state if the policy is absent or expired. A stop request prevents reapplication during uninstall/logout. |
| Hosts editing could discard non-UTF-8 bytes or change file permissions/ACLs. | Hosts is read and written with a reversible byte mapping. Windows uses `ReplaceFileW` for atomic replacement with attribute/ACL preservation. Ambiguous markers and files without a final newline are left untouched; failure is reported. |
| Uninstall recursively deleted the whole installation directory and could remove unrelated files or backups before restoration. | Uninstall requests stop, removes the logon task, restores managed settings, clears the local credential, and removes the recovery task only after successful restoration. It retains installed files/backups for inspection. |
| Foreground activity was collected while no authorized policy was active. | Tracking now starts only after active policy application, and stops and clears its local buffer on policy loss or failure. |
| A frozen executable could fall back to temporary extraction storage for backup/cache state. | Frozen Windows builds require stable ProgramData state. If it is unavailable, the agent refuses to enforce. |
| A rule could target local addresses or the API endpoint and disrupt local connectivity. | Hosts normalization excludes IP literals, local/private-style names, and the configured API host. |
| Oversized or malformed server/cache policy data could consume excessive resources or interrupt recovery. | The agent bounds response/cache size and rule counts, validates cached structure, and writes cache atomically. The API rejects oversized rule sets. Invalid policy causes restoration. |
| A production agent could send its device credential to a plain HTTP server if misconfigured. | Frozen builds default to production mode and require a valid HTTPS `API_URL`; local HTTP remains available only in explicit development mode. |
| A downloaded executable could load a planted `.env` file beside it and send credentials to another server. | Frozen Windows builds load configuration from stable ProgramData or the bundled default, never from the download folder. |
| Continuous agent logs could grow without bound. | File logs now rotate at 2 MB with three backups. |
| Two agent processes could race while replacing/restoring the same hosts file. | A Windows named mutex lets only one main agent loop run; a second instance exits before touching system settings. The independent recovery check still runs when policy expires. |
| An unexpected polling error or shutdown cleanup error could leave activity recording or managed hosts entries active. | The agent now stops and clears activity on these errors, attempts direct restoration, and reports incomplete restoration for the scheduled recovery task to retry. Shutdown does not report a successful unblock until direct restoration succeeds. |
| A packaged agent could be misconfigured with an HTTP API or a different Socket.IO server and expose its device credential. | Packaged builds require an HTTPS API URL even if test mode is set, and Socket.IO must use that same HTTPS origin. |

## Practical limits

- Application handling is deliberately best-effort: apps can show save prompts, refuse to close, or lack a normal GUI window. The agent does not claim confirmed app termination.
- Hosts entries affect exact domain resolution and common `www` variants. Browser DNS-over-HTTPS, already cached resolutions, and other names may bypass them.
- The once-per-minute recovery task requires Windows Task Scheduler, the machine to be on, and access to the stable ProgramData directory. A disabled task or a damaged backup can still require manual administrator recovery.
- Windows executable packaging, installer behavior on an actual student PC, ACL preservation on the real hosts file, and real browser/app enforcement remain unverified until a separately authorized, controlled live test.
- Installation and enrollment must use the same Windows account, and that account must have administrator rights. A separate admin account used only for elevation cannot access the student's credential store or desktop activity in this architecture.

## Safe verification

`python -m unittest discover -s services/agent/tests -p test_device_policy.py -v` covers temporary hosts preservation, invalid markers, no-newline refusal, app close filtering, cached policy expiry, DNS backup failures, recovery, activity shutdown, packaged transport checks, and mocked installer/uninstaller calls. API security tests and web/API builds verify the surrounding policy/authentication path. No test writes to the real Windows hosts file, DNS adapter, or Task Scheduler.
