# HOC Undervolting Wizard v0.4.0-beta.2

Second public beta of the integrated-test HOC Undervolting Wizard.

## New in beta.2

### Complete Battery-profile starting setup

The Wizard now starts with the conservative Battery setup used by the Performance Modes Battery tuning guide:

- CPU Max Clock: **1785 MHz**
- CPU Boost Clock: **1785 MHz**
- GPU Max Clock: **384 MHz**
- RAM Max Clock: **1600 MHz**
- Uncapped Clocks: **OFF**
- RAM HP Mode: **OFF**
- Overwrite Boost Mode: **OFF**
- Auto CPU RAM OC: **OFF**
- CPU UV Table: **Normal**
- Low UV / High UV: **0 / 0**
- Low VMIN / High VMIN: **620 / 750 mV**
- RAM VDD2 / VDDQ: **1175 / 600 mV**
- Per-game CPU/GPU/RAM clocks: **stock/default**

After setting the baseline, apply/save the HOC Toolkit values, **Save KIP**, reboot CFW and reopen the Wizard.

### Hard override pre-flight before every built-in test

Before the test timer or stress engine can start, the Wizard now reads Horizon OC's live `hoc:clk` context and verifies **all three Temporary Overrides**:

- CPU
- GPU
- RAM

The expected combination depends on the active Wizard stage, including:

- normal handheld: **1020 / 384 / 1331.2 MHz**
- low-VMIN validation: **510 / 384 / 1331.2 MHz**
- Nintendo Boost: **1785 / 76.8 / 1600 MHz**

If even one override is missing or incorrect, the test is blocked and the Wizard displays **Expected vs Current** with an OK/WRONG status for CPU, GPU and RAM.

A blocked test does **not** set the persistent running-test marker and records **no PASS or FAIL**. After correcting the values in Horizon OC, press **A** to check all three again and start only when everything matches.

If the `hoc:clk` service cannot be read, the test is also blocked rather than silently continuing.

## Existing beta.1 features

- CPU Matrixprod + Hanoi verification based on the GPLv2 Horizon-OC / Benchmark Toolbox implementation.
- memtester v4 RAM algorithms with automatic mismatch detection.
- Combined CPU + RAM validation.
- Project-original deko3d GPU compute/memory stress test.
- 1-minute quick tests and 1-hour validation runs.
- Persistent crash/reboot detection.
- Last-known-good recovery workflow.
- The Wizard never writes Horizon OC voltage/UV settings or modifies `hoc.kip`.

## Installation

1. Download `HOC-Undervolting-Wizard.nro` from Assets.
2. Copy it to:

   `/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro`

3. Launch through Homebrew Menu. Full application/title-takeover mode is strongly recommended for RAM testing.

Existing Wizard state remains in `/switch/HOC-Undervolting-Wizard/state.ini`.

## Beta notice

This build is intended for real-hardware validation on Mariko / Switch OLED. Start with known-stable Horizon OC values and confirm the CPU, RAM, Combined, GPU and new override pre-flight behavior before using it to search aggressively for voltage limits.

## License / credits

HOC Undervolting Wizard is licensed under **GNU GPL version 2 only**. See `LICENSE` and `THIRD_PARTY_LICENSES.md` for full attribution and provenance.