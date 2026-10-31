# HOC Undervolting Wizard v0.4.0-beta.22

## Hardware Detection: RAM OC guide range

The Hardware Detection result now shows the Horizon OC Mariko guide's typical RAM overclocking range for the detected DRAM family.

Example for NEE / DRAM ID 5:

- Module: NEE 4GB
- VDDQ start: 640 mV
- OC range: 3100-3300 MHz

The displayed range is informational only and is explicitly marked as a guide estimate because real maximum stable clocks vary with silicon quality, SoC/PLL behavior, voltage and timings.

Ranges are included for NEE/x267, WT:B, AA-MGCL, WT:E, AM-MGCJ, WT:F, AB-MGCL and NME families.

No hardware-detection, tuning, test or voltage logic changed.
