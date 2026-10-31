# HOC Undervolting Wizard v0.4.0-beta.23

## Preparation raw config debug

This diagnostic beta adds a read-only raw Horizon OC config viewer to investigate version-dependent `HocClkConfigValue` index layouts.

When Preparation shows `SETTING NOT READY`, press **Y** to open **RAW CONFIG DEBUG**.

The debug viewer shows:
- Horizon OC version string
- hoc:clk API version
- raw `GetConfigValues()` indexes 0-95 across four pages

Controls:
- **A**: next page
- **X**: previous page
- **B**: return to the Preparation check

No tuning, stress-test, reboot, Temporary Override, or automatic VMIN-scan logic was changed in this beta.
