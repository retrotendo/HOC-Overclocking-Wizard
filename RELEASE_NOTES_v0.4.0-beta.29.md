# v0.4.0-beta.29

Preparation baseline/automatic-setup fix.

- `Use current settings as baseline` no longer performs an unnecessary Preparation reboot. The captured values are stored and the Wizard moves directly to the next Low UV candidate.
- Automatic Preparation now uses Horizon OC's own public `SetConfigValues` IPC and `SetKipData` (Save KIP) instead of editing `config.ini` behind the running sysmodule.
- Automatic writing is guarded to the confirmed Horizon OC 2.5.1 config layout. Unsupported versions fail safely without writing version-dependent indexes.
- Preparation values are read back from the named config keys before reboot is allowed.
