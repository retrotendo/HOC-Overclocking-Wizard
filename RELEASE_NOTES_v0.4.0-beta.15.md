# HOC Undervolting Wizard v0.4.0-beta.15

This beta redesigns the TEST BLOCKED override screen for readability while keeping all tuning and validation logic unchanged.

## Clear Required / Current / Status blocks

Each CPU/GPU/RAM override is shown vertically:

```text
CPU
  Required : 1020 MHz
  Current  : 918 MHz
  Status   : WRONG
```

- `Current` is the actual Horizon OC override value currently set.
- If no override is set, the Wizard shows `NOT SET`.
- `WRONG` is shown in red.
- `OK` is shown in green.
- VMIN floor checks also show the applied CPU clock as a separate Required / Current / Status block.

## No tuning changes

Tuning order, reboot points, override validation, stress tests, VMIN detection, known-result shortcuts, updater behavior and the Ultrahand-friendly right-side layout are unchanged from beta.14.

This remains a pre-release until validated on real hardware.
