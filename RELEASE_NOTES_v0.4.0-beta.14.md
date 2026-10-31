# HOC Undervolting Wizard v0.4.0-beta.14

This beta corrects the Horizon OC menu hierarchy shown by the Wizard.

## CPU controls are under CPU Settings

Horizon OC does not use a separate CPU UV submenu. The Wizard now shows all CPU-related controls under the real **CPU Settings** menu:

```text
@ Horizon OC

CPU Settings:
 - CPU Max   : 1963 MHz
 - Low VMIN  : 620 mV
 - High VMIN : 750 mV
 - UV Table  : 1683 MHz Tbreak
 - Low UV    : 0
 - High UV   : 0
```

The same correction is applied to Low UV, High UV, Low VMIN, combined CPU/RAM and recovery screens.

## No tuning changes

Tuning order, reboot points, stress tests, VMIN detection, override checks, known-result shortcuts, updater behavior and the Ultrahand-friendly right-side layout are unchanged from beta.13.

This remains a pre-release until validated on real hardware.
