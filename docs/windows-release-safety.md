# Windows release safety

The current nightly `AcademiaShieldSetup.exe` and `AcademiaShield.exe` were verified as **NotSigned** with `Get-AuthenticodeSignature`. A SmartScreen “Windows protected your PC” prompt is therefore expected. It is an application-reputation warning, not proof that the file is malware or proof that the installer is safe.

Do not deploy the unsigned preview to student or personal computers. The release workflow builds artifacts for checking but publishes new Windows assets only if both the setup executable and the standalone agent have valid trusted Authenticode signatures. The repository and login page label the preview; the existing GitHub release assets remain available until they are replaced or withdrawn.

## Obtain signing capability

1. Ask the university IT/security team whether they can sign both executables under the university's existing trusted code-signing identity. This is usually the simplest route for an academic project.
2. If the university cannot help, obtain an organization-validated (OV) code-signing certificate from a trusted certificate authority. Identity validation and secure key storage are required. Microsoft currently lists Azure Artifact Signing for organizations in the US, Canada, EU, and UK, and individuals in the US and Canada; an individual in India should check eligibility before choosing that route.
3. Keep certificate private keys and signing credentials out of Git, the app, the agent, and chat. Configure the chosen provider in GitHub Actions secrets or its supported short-lived identity flow. The exact CI signing integration depends on whether the institution uses a certificate file, hardware token/HSM, or cloud signing service.
4. Sign the PyInstaller agent **before** bundling it into the desktop installer. Sign the desktop executable and final NSIS setup with the same trusted publisher identity. Verify both release assets with `Get-AuthenticodeSignature` before uploading.

A trusted signature identifies the publisher and helps build reputation; Microsoft does not guarantee that a brand-new signed binary will avoid SmartScreen immediately. Self-signing is useful for internal development but does not solve public SmartScreen warnings.

## Device-safety gate before student use

On a disposable, consented Windows VM: record hosts-file bytes and permissions, install and enroll the app, run a short session, let it expire, then check that only the agent-managed block was removed and normal DNS access returned. Repeat with the API offline, agent crash, reboot, and uninstall. Review Task Scheduler entries and ProgramData files. Do not run this test on a student's normal computer.

References: [Microsoft SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation), [Microsoft code-signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options), [electron-builder Windows signing](https://www.electron.build/docs/features/code-signing/code-signing-win/).
