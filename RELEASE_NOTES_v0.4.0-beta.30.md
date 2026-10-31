# v0.4.0-beta.30

Guided CPU Low UV / Low VMIN boot-search and validation flow.

- Preparation check can now automatically set required values when one or more entries are wrong.
- Reboot handoff now clearly instructs the user to reopen the wizard after boot and explains recovery through Hekate / CFW No OC if normal boot fails.
- CPU Low UV discovery now searches the boot limit first, starting from Low UV 1 and increasing one step at a time.
- After reboot, the wizard reads the active Horizon OC 2.5.1 configuration through `hoc:clk` and compares the requested value with the actually active value.
- A successful candidate is only accepted after the user confirms normal CFW boot with no freeze, crash, spontaneous reboot, or other system failure.
- If recovery returns to a safer previous value, the wizard explicitly shows the requested value, the active value, and `Last good value`, then asks the user to confirm it.
- After the boot limit is found, the wizard automatically scans CPU voltage regions across 510 / 612 / 714 / 816 / 918 / 1020 MHz and selects the highest frequency representing each distinct voltage region.
- The selected representative frequencies are then tested automatically for 1 minute each using temporary CPU/GPU/RAM overrides.
- CPU Low UV validation failure backs off Low UV by one step and repeats the scan/validation flow.
- CPU Low VMIN now follows the same boot-limit method in 10 mV steps, then performs the same automatic voltage-region scan and 1-minute representative-frequency validation.
- CPU Low VMIN validation failure backs off by +10 mV before repeating validation.
- Existing RAM/VDDQ/VDD2 stages remain unchanged in this beta.

Automatic persistent CPU setting writes are guarded to the confirmed Horizon OC 2.5.1 config layout and use Horizon OC's `SetConfigValues` + `SetKipData` path.
