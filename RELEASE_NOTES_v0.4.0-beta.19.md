# HOC Undervolting Wizard v0.4.0-beta.19

## Hardware Detection Diagnostic Build

Beta.19 adds an on-device diagnostic readout when RAM detection fails. The screen shows the HOC API version, raw HocClkContext bytes 400-411, the 32-bit console-type value at byte 408, and both known DRAM-ID layout candidates.

This build intentionally does not guess a RAM type. Please photograph the diagnostic screen so the exact runtime HOC layout can be identified.

No tuning, stress-test, updater, reboot, override, or automatic VMIN behavior changed from beta.18.
