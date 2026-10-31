# HOC Undervolting Wizard v0.4.0-beta.9

This beta redesigns the Wizard screens for practical use together with the Ultrahand / Horizon OC overlay.

## Ultrahand-friendly right-side layout

The tuning-stage information is now shown as a compact table on the right side of the screen so the Horizon OC overlay can remain open on the left while the required values stay readable.

Each stage shows only the information needed at that moment:

- current Wizard step
- persistent Horizon OC value to set
- whether `Save KIP + Reboot` is required
- CPU / GPU / RAM Temporary Override targets
- built-in test type and duration
- relevant controls

Example structure:

```text
Battery Wizard
Step : CPU Low UV

Set in HOC:
Low UV : 10
Action : Save KIP + Reboot

Overrides:
CPU : 1020 MHz
GPU : 384 MHz
RAM : 1331.2 MHz

Test:
1 min - Matrix + Hanoi
```

## Low VMIN presentation

The beta.8 Low VMIN logic is unchanged. When the persistent Low VMIN value is changed, the UI still explicitly requests `Save KIP + Reboot` before testing.

The later dynamic floor sweep does not require another reboot because no persistent HOC setting changes. Its live CPU-voltage sampling remains automatic in the background; the normal UI simply shows the Temporary Overrides to set and asks the user to continue.

## No tuning-logic changes

This release intentionally changes presentation only. The following beta.8 behavior is retained:

- startup self-updater
- Full Application Mode requirement
- CPU/GPU/RAM override preflight before every test
- dynamic Low VMIN floor detection
- CPU / RAM / Combined / GPU stress tests
- KNOWN PASS / FAIL shortcuts
- crash/reboot recovery
- tuning order, voltage steps, test durations and reboot points

This remains a pre-release until validated on real Mariko / Switch OLED hardware.
