# HOC Undervolting Wizard v0.4.0-beta.5

This beta refines the dynamic CPU Low VMIN workflow introduced in beta.4.

## VMIN floor sweep is now measurement-only

After the Wizard finds a stable Low VMIN candidate, it still checks the CPU curve at:

**510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz**

with GPU **384 MHz** and RAM **1331.2 MHz**.

However, those crossover points no longer each run another 1-minute CPU stress test. Their purpose is only to determine where the configured Low VMIN stops controlling the CPU rail.

For every probe point the Wizard:

1. verifies CPU + GPU + RAM Temporary Overrides;
2. reads Horizon OC's live CPU rail voltage multiple times;
3. keeps valid readings with the requested overrides active;
4. uses the **median of 3 samples**;
5. records the highest CPU clock still within one 5 mV PMIC step of the configured Low VMIN.

The actual **1-hour CPU stability confirmation** is then run once at that highest floor-bound CPU clock. This avoids redundant long/short testing at lower clocks that use the same voltage floor.

Example: if a console stays around 570 mV through 816 MHz but rises above the floor at 918 MHz, the 1-hour VMIN validation is performed at 816 MHz.

The detected crossover is intentionally dynamic because it can vary with CPU Speedo, selected CPU voltage table and CPU UV tuning.

## Known PASS / FAIL behavior

- `[+] KNOWN PASS / SKIP` still skips real stress-test stages when the value was already validated previously.
- `[X] KNOWN FAIL / SKIP` still records a known failure on real test stages.
- During the VMIN measurement-only sweep, `A` performs the required live-voltage probe.
- Pressing `+` during a VMIN probe performs the same measurement instead of blindly skipping it.
- `X` is disabled during VMIN probe stages because the probe itself is not a stability PASS/FAIL test.

## Existing beta.4 workflow retained

- Low VMIN search floor: **570 mV**
- VDDQ simplified search interval: **10 mV**
- VDD2 step: **12.5 mV**
- combined VDDQ + VDD2 Boost validation at **1785 / 76.8 / 1600**
- automatic CPU/GPU/RAM Temporary Override verification before stress tests
- Matrixprod + Hanoi CPU validation
- memtester v4 RAM validation
- combined CPU + RAM validation
- deko3d GPU compute/memory validation
- crash/reboot detection and safe recovery flow

## Installation

Download `HOC-Undervolting-Wizard.nro` from Assets and copy it to:

`/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro`

This remains a **pre-release** until the revised flow has been validated on real Mariko / Switch OLED hardware.
