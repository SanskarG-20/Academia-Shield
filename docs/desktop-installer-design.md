# Windows desktop installer design

The Windows installer bundles the built React interface and the Python agent. The API and MongoDB database remain shared hosted services. The desktop renderer uses the same routes and authentication as the browser app.

The Electron main process serves only the bundled web assets under the fixed `academia://academia-shield` origin. Node integration is disabled, context isolation and sandboxing are enabled, and navigation outside the bundled UI is blocked. The API and Socket.IO allow only this additional exact origin. No server or device secret is packaged.

An elevated, per-machine NSIS installer copies the desktop app and calls the bundled agent's install-only command. This registers the existing agent and recovery tasks without blocking the installer. Uninstall calls the agent's safe uninstall and aborts if restoration fails. The installed student app exchanges a one-time enrollment claim through a narrow Electron IPC bridge and the agent's stdin; the long-lived credential remains in the operating-system credential store and is never returned to renderer JavaScript. The existing web UI continues to support browser-based enrollment instructions.

The login page links to the setup executable rather than the agent-only binary. GitHub Actions builds the agent, web assets, and desktop installer on Windows and publishes both setup and agent binaries to the nightly release. Builds use only the public API URL. No real Windows hosts or DNS state is touched by automated tests.

This version requires installation and enrollment under the same administrator-capable Windows account, matching the current agent design. The installer is unsigned until a code-signing certificate is configured.
