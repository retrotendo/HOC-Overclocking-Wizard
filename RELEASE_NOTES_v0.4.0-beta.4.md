# HOC Undervolting Wizard v0.4.0-beta.4

Fourth public beta of the integrated-test HOC Undervolting Wizard.

## Main changes

### Dynamic CPU Low VMIN validation

The Wizard no longer assumes that the Low VMIN floor ends at the same CPU frequency on every Mariko/OLED console.

Horizon OC's live `hoc:clk` context is now used to read the **actual CPU rail voltage** while sweeping:

**510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz**

GPU remains at **384 MHz** and RAM at **1331.2 MHz**.

The Wizard automatically remembers the **highest CPU clock still running at the configured VMIN floor** (within one 5 mV PMIC step). Once CPU voltage clearly rises above VMIN, the sweep stops and the final **1-hour VMIN validation is run at that highest floor-bound CPU clock**.

This avoids hardcoding a crossover that can vary with CPU Speedo, selected CPU voltage table and CPU UV tuning.

Low VMIN still starts conservatively from **620 mV** and the Wizard never searches below **570 mV**.

### Known PASS / FAIL shortcuts

Already tuned your console before using the Wizard?

Built-in test stages now support:

- **[+] KNOWN PASS / SKIP** — accept the current test/value without running the stress test.
- **[X] KNOWN FAIL / SKIP** — record the current test/value as a known failure.

These shortcuts are intended for values that were already stability-tested previously.

### Revised Battery-guide alignment

Preparation guidance now matches the revised Battery Tuning guide:

- Uncapped Clocks **OFF**
- HP Mode **OFF**
- RAM Max Clock **1600 MHz**
- VDD2 **1175 mV** or known-stable lower value
- VDDQ **600 mV** or known-stable lower value
- CPU Max Clock = **lowest selectable Horizon OC value** (currently 1963 MHz on Mariko)
- CPU UV Table = **1683 MHz Tbreak** or another known-working table
- CPU Boost Clock = **lowest selectable HOC Toolkit value** (stock workflow target 1785 MHz)

### RAM workflow updates

- VDDQ search interval changed to **10 mV** to match the simplified guide workflow. Horizon OC itself exposes 5 mV VDDQ steps, so one Wizard step equals two HOC UI steps.
- Added a separate **1-hour VDDQ + VDD2 combined validation at 1785 / 76.8 / 1600** before the normal-handheld RAM test.
- If the pair fails, the Wizard first retries with **VDDQ +10 mV**. If it still fails, VDDQ is restored and **VDD2 +12.5 mV** is tried.

## Existing integrated tests

- CPU Matrixprod + Hanoi verification
- memtester v4 RAM algorithms
- Combined CPU + RAM validation
- deko3d GPU compute/memory validation
- Automatic CPU/GPU/RAM Temporary Override verification before every built-in test
- Persistent crash/reboot detection
- Safe no-boot recovery guidance

## Installation

1. Download `HOC-Undervolting-Wizard.nro` from Assets.
2. Copy it to:

   `/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro`

3. Launch through Homebrew Menu. Full application/title-takeover mode is strongly recommended for RAM testing.

Existing state remains at:

`/switch/HOC-Undervolting-Wizard/state.ini`

## Beta notice

This build compiles successfully in CI but the new dynamic VMIN flow still needs real-hardware validation on Mariko / Switch OLED before it should be considered stable.

## License / credits

HOC Undervolting Wizard is licensed under **GNU GPL version 2 only**. See `LICENSE` and `THIRD_PARTY_LICENSES.md` for complete attribution and provenance.
