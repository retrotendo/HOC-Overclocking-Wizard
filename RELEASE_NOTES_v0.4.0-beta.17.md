# HOC Undervolting Wizard v0.4.0-beta.17

This beta hardens the new hardware-aware/reboot/automatic VMIN workflow introduced in beta.16.

## Fixes

- Old beta.15 manual VMIN sweep states migrate back into the automatic 510->1020 MHz scan instead of entering plateau validation with empty observations.
- RAM is detected for upgraded in-progress states too. If RAM tuning already started, detection records the module/baseline without overwriting the user's tuned VDDQ values.
- `KNOWN PASS / SKIP` can no longer silently advance a persistent-setting step while Horizon OC still contains the wrong value. The value is verified first; if it is wrong, the Required/Current screen is shown. A correct known value may still skip reboot/stress validation.
- Preparation mismatch reporting now lists every incorrect Horizon OC/HOC Toolkit value compactly with Required, Current and red WRONG status.

## Retained beta.16 workflow

- automatic RAM detection and 600/640 mV VDDQ baseline
- green setting confirmation before user-confirmed system reboot
- boot-normal confirmation after restart
- fully automatic Temporary Override CPU voltage scan at 510/612/714/816/918/1020 MHz
- visible scan/sample progress
- automatic restoration of previous Temporary Overrides
- voltage-region grouping and 1-hour validation at the highest clock of every region

This remains a pre-release pending real-hardware validation.
