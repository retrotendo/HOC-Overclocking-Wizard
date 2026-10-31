# HOC Undervolting Wizard v0.4.0-beta.48

## Guide-wide UI cleanup
- Left-side guide content is cleaner and more readable, with improved spacing and key/value presentation.
- The right-side panel is now treated consistently as the user's current task instead of repeating page information.
- Hardware Detection removes unnecessary technical details and focuses on the detected memory profile and the next action.
- Preparation explains why a known baseline is needed, while the right panel keeps the required SET / ACTIVE values visible.

## Search actions
- Search steps use direction-aware wording.
- CPU Low UV / High UV failures clearly return to a lower last-known-good level.
- Low VMIN / VDDQ / VDD2 failures clearly return to a higher last-known-good voltage.
- Long and final validation pages no longer show a misleading manual `Known FAIL` option.
- If a running validation freezes, crashes or reboots, the existing interrupted-test popup handles the failure when the Wizard is reopened.

## CPU voltage scan
- Removed user-facing `Floor Sweep @ 510 / 612 / ...` page titles.
- The scan is now presented as a neutral CPU Voltage Floor Scan.
- Automatic voltage measurements use the same graphical popup language as the rest of the Wizard and show the current CPU frequency and scan progress.

## Stability and tuning logic
- Existing tuning limits, voltage search order, stress-test engines, recovery behavior and validation durations are unchanged.
