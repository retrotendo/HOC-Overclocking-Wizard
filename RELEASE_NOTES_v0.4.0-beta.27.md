# HOC Undervolting Wizard v0.4.0-beta.27

## CPU Low UV search now tests every step

Low UV now follows the intended step-by-step stability search:

1. Set the next Low UV value.
2. Reboot.
3. Apply/check Temporary Overrides `1020 / 384 / 1331.2 MHz`.
4. Run the built-in 1-minute CPU test.
5. PASS: that UV value becomes the new last-known-good value and the Wizard advances to the next UV step.
6. FAIL or no boot: restore the previous last-known-good Low UV value and run the 1-hour CPU validation there.

A successful boot alone is no longer counted as a passing Low UV step.

### No-boot recovery

If a candidate does not boot, use Hekate `CFW No OC`, restore the previous Low UV value, restart normal CFW and reopen the Wizard. When the Wizard sees that the last-known-good Low UV value is already active, it proceeds directly to the 1-hour validation instead of asking for another redundant reboot.

No changes were made to the Low VMIN, RAM-rail, High UV or final validation algorithms in this beta.
