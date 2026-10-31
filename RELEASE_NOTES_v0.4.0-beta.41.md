# HOC Undervolting Wizard v0.4.0-beta.41

## Low VMIN minimum handling
- When an imported/current baseline already uses 570 mV Low VMIN, the Wizard no longer silently skips straight into the clock/voltage scan.
- A dedicated Low VMIN Boot Search notice now shows that 570 mV is the minimum recommended value used by the Wizard.
- The notice explains that going lower is not recommended because very low VMIN values may cause Sleep / Standby / Wake problems.
- No value below 570 mV is tested by the Wizard.
- `A : Confirm 570 mV and continue` then proceeds to the Low VMIN clock/voltage scan.
- Normal Low VMIN quick search behavior above 570 mV is unchanged.

## Existing beta40 behavior retained
- VDDQ final validation: 30 minutes.
- Final VDDQ + VDD2 pair validation: 1 hour.
- Handheld 1020 / 384 / 1331 validation: 1 hour.
- High UV CPU memtester and separate Combined CPU + RAM validation remain 1 hour each.
- Startup risk/liability warning remains in place.
