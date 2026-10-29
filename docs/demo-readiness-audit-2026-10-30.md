# Demo readiness audit — 30 October 2026

## Verified locally

- Professor dashboard, batches, rules, sessions, live monitor, and coverage loaded against an isolated local database.
- Explicit local demo mode allowed a synthetic student to request an OTP, create a profile, join a batch, view an automatic session, and mark attendance. The temporary database was removed after testing.
- API security tests passed; Python agent tests used mocks and temporary files. No real Windows hosts or DNS settings were changed.
- Web and API production builds passed.

## Fixes

- Student logout now clears the browser token and disconnects the socket.
- Student login no longer asks for an unused phone number. The OTP screen shows the server's five-minute code lifetime and a separate one-minute resend cooldown.
- Outside explicit local demo mode, OTP requires configured email delivery. Existing students receive the code at their stored address. New students require an explicitly configured `STUDENT_EMAIL_DOMAIN` and a genuine `SAP_ID@domain` institutional format. Unknown mappings fail closed. Profile email comes from the verified OTP session, not browser input.
- The live monitor no longer treats attendance as device presence or invents an engagement score. Attention events include a session ID so one monitor cannot display another session's score.
- Session summaries are available after completion. They count only observed agent activity as attention evidence, identify students without telemetry, and regenerate older cached summaries once. The UI does not claim Gemini generated a report when the rule-based fallback was used.

## Deployed demo prerequisites

1. Confirm Render has `EMAIL_SERVICE`, `EMAIL_USER`, and `EMAIL_PASS` set privately. Never place values in Git or chat. Leave `DEMO_MODE` unset on the public service.
2. For a **new** student, set `STUDENT_EMAIL_DOMAIN` only after confirming the institution actually uses `SAP_ID@domain`. If it does not, use a pre-registered test student whose stored email is controlled by the demonstrator. The current app does not discover the institution's identity mapping automatically.
3. Use an existing professor account, or configure `ALLOWED_PROFESSOR_DOMAINS` for intended faculty self-registration. Confirm the deployed frontend points to the deployed API and the API allows the frontend origin.
4. For a web-only demonstration, show enrollment, attendance, coverage, and session scheduling. Website/app enforcement and live device telemetry require a separately installed and enrolled Windows agent; the web page alone cannot block software.
5. A configured `GEMINI_API_KEY` enables AI-written summaries when activity exists. Without one, or without agent activity, the system returns a factual rule-based report.

The deployed student login was **not** confirmed end to end: the institution's email mapping and Render SMTP settings are unknown, and no real credentials or production OTP were used during this audit. Verify those prerequisites with a dedicated test account before the presentation.
