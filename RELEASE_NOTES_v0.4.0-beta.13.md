# HOC Undervolting Wizard v0.4.0-beta.13

This beta keeps the beta.12 Ultrahand-friendly right-side layout and makes the app/menu hierarchy explicit.

## Clear app hierarchy

Horizon OC settings now appear in the same visual structure used while navigating the overlay:

```text
@ Horizon OC

General:
 - Uncapped Clocks : OFF

RAM Settings:
 - HP Mode         : OFF
 - RAM Max         : 1600 MHz
 - VDD2            : 1175 mV
 - VDDQ            : 600 mV

CPU Settings:
 - ...

CPU UV:
 - ...

@ HOC Toolkit
 - CPU Boost       : 1785 MHz
```

The same hierarchy is used during tuning stages: the application is named first, followed by the actual submenu and the setting to change. Temporary Overrides are also named explicitly.

## No tuning changes

Tuning order, reboot points, stress tests, VMIN detection, override validation, known-result shortcuts and updater logic are unchanged from beta.12.

This remains a pre-release until validated on real hardware.
