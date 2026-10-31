# HOC Undervolting Wizard v0.4.0-beta.7

This beta makes the Preparation screen match the Battery guide exactly.

## Fixed starting baseline

The setup screen no longer suggests replacing guide defaults with previously known personal values. It now always asks for the defined guide baseline:

- HP Mode: OFF
- RAM Max Clock: 1600 MHz
- VDD2: 1175 mV
- VDDQ: 600 mV
- CPU Max Clock: lowest selectable (currently 1963 MHz on current Mariko HOC builds)
- CPU UV Table: 1683 MHz Tbreak
- Low UV / High UV: 0 / 0
- Low VMIN: 620 mV
- High VMIN: 750 mV
- CPU Boost Clock: lowest selectable, stock workflow target 1785 MHz

Users who already know stable values should keep using **KNOWN PASS / SKIP** during the corresponding tuning stages. This preserves one consistent starting state for every new run while still allowing experienced users to fast-forward.

Full Application Mode remains mandatory; Applet Mode is blocked at startup.

This remains a pre-release until validated on real Mariko / Switch OLED hardware.
