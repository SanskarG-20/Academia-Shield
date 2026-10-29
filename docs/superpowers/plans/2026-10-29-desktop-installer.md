# Windows Desktop Installer Implementation Plan

> **For agentic workers:** Implement each checked task in sequence and verify before claiming completion.

**Goal:** Ship one Windows installer containing the Academia Shield interface and local agent.

**Architecture:** Bundle the Vite app in Electron; retain the hosted API and database. NSIS installs the agent tasks, while a narrow IPC bridge pairs the agent using a one-time claim.

**Tech Stack:** React/Vite, Electron, electron-builder/NSIS, Python/PyInstaller, Express.

**Spec:** `docs/desktop-installer-design.md`

## Global constraints

- Never package server or device credentials.
- Do not change real hosts/DNS state in automated tests.
- Preserve device-bound policy authorization and safe restoration.

## Tasks

- [x] Add agent install-only and stdin-enrollment modes with safe mock tests.
- [x] Add Electron app and narrow enrollment bridge; package built web and agent assets.
- [x] Allow the fixed desktop origin in REST and Socket.IO, with security test.
- [x] Update enrollment UI, login download target, documentation, and release workflow.
- [x] Run agent tests, API security tests, web/API builds, typecheck, desktop origin smoke test, and Windows installer build. Live installation and hosts/DNS enforcement remain intentionally untested.
