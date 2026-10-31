# HOC Undervolting Wizard v0.4.0-beta.47

## Preparation layout
- Preparation now uses a dedicated full-height Current Instruction panel on the right.
- All required Preparation values remain visible while an Ultrahand overlay is open.
- The right panel shows SET and ACTIVE values side by side.
- ACTIVE values that do not match the required value are highlighted in red.
- Horizon OC settings and HOC Toolkit settings are clearly separated.
- Compact category prefixes keep all Preparation values readable within the 720p layout.

## Setting not ready
- Preparation's Setting Not Ready screen uses the same SET / ACTIVE table instead of printing a long list into the left guide card.
- Even if every Preparation value is wrong, all values remain visible without overlapping the action buttons.

## Boot checks
- Post-reboot stability confirmation is now a focused popup instead of a full technical guide page.
- The popup asks a simple Yes / No question such as "Did Low UV 1 boot normally?".
- Yes advances to the next candidate; No returns to the previous known-good value.
- Freeze, crash and unexpected reboot checks are shown in plain language.

## Stability test display
- Running tests now show the tuning purpose instead of only the underlying test engine name.
- CPU voltage-region validation clearly shows the current CPU clock, region number and observed voltage, for example: CPU 510 MHz | Region 1 of 4 | ~570 mV.
- Low UV, Low VMIN, VDDQ, VDD2 and High UV tests use clear purpose-specific titles so repeated region tests are easy to distinguish.
- The underlying stress-test engines and validation logic are unchanged.

## Safety notice
- Resetting Wizard progress now clears the disclaimer acknowledgement.
- After a reset, the safety notice appears again on the next app start while the Wizard is back at Baseline.
- Existing tuning runs beyond Baseline do not get interrupted by the disclaimer after a reboot or crash.

## Tuning logic
- No tuning thresholds, test logic, recovery behavior, or validation durations were changed.
