# HOC Undervolting Wizard v1.0.0-beta

## First graphical interface beta
- Introduces the new minimal fullscreen Horizon OC / Undervolting Wizard interface while retaining the v0.4.0-beta.42 tuning and validation logic.
- Adds a persistent top progress strip for Baseline, Low UV, Low VMIN, VDDQ, VDD2, High UV and Finalize.
- Adds a right-side `Current Instruction` panel that shows the exact Horizon OC value currently requested by the Wizard.
- Adds a right-side `Actual Active Values` panel for CPU Low UV, CPU Low VMIN, VDDQ, VDD2 and CPU High UV.
- If a currently requested value does not match the active Horizon OC value, that active value is highlighted in red.
- Search pages no longer duplicate the requested setting in the left content area; the requested value is shown once in `Current Instruction`.
- The left pane keeps the existing Wizard wording and actions from v0.4.0-beta.42.
- Controller actions use compact color-coded panels without a duplicate footer legend.
- Adds a subtle pulse animation to the active progress step.
- No decorative hardware/brand imagery is used.

## Existing tuning flow retained
- Explicit Wizard-limit confirmation remains active for Low UV, Low VMIN, VDDQ, VDD2 and High UV boundaries.
- Voltage-region scans retain 2 settling reads, 9 measured samples, median selection and noisy-sample retry.
- VDDQ final validation remains 30 minutes.
- Final VDDQ + VDD2 pair validation remains 1 hour.
- Handheld 1020 / 384 / 1331 validation remains 1 hour.
- High UV CPU memtester and the separate High UV + RAM combined validation remain 1 hour each.
- Startup update check and risk/liability warning remain in place.

This is the first UI beta. Tuning behavior is intentionally based on the proven v0.4.0-beta.42 core so interface feedback can be tested without redesigning the undervolting logic at the same time.
