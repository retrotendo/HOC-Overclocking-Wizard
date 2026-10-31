# v0.4.0-beta.35

Automatic stability-test flow cleanup.

- Removed `Previous overrides : RESTORED` from the successful CPU voltage-scan screen.
- Renamed the action to `A : Start automatic stability test`.
- Added a clear crash instruction: reboot and reopen the Wizard if the stability test crashes.
- Pressing A on the completed voltage-scan screen now starts the automatic region stability test directly.
- The redundant second `Start automatic validation` confirmation page is skipped in the normal flow.
- Automatic override setting and verification still run in the background; an error is only surfaced if verification fails.
- Interrupted-test recovery remains unchanged: after reopening the Wizard, it asks whether the console froze, crashed, or rebooted so the result can be counted as FAIL or retried.
