# HOC Undervolting Wizard v0.4.0-beta.46

## Full-width modal UI
- Update check, update prompt, installation status and update errors now use the same graphical design as the Wizard.
- The safety disclaimer now uses the graphical full-width modal design.
- Reboot confirmation is now a large full-width modal without the right-side Current Instruction / Actual Active Values cards.
- Reboot guidance is shorter and clearer: apply the saved value, reboot, reopen the Wizard, and use CFW No OC + the last known-good value if normal CFW does not boot.

## Disclaimer behavior
- The disclaimer is now a one-time acknowledgement stored independently from Wizard tuning progress.
- Resetting Wizard progress does not make the disclaimer appear again.
- Existing installations with an existing state.ini are treated as already acknowledged, so an in-progress tuning run is not interrupted by the new disclaimer after updating.

## Tuning logic
- No tuning thresholds, search logic, recovery behavior, validation durations or stress-test logic were changed.
