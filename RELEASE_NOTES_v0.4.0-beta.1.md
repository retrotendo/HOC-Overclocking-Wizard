# HOC Undervolting Wizard v0.4.0-beta.1

First public beta of the integrated-test version of HOC Undervolting Wizard.

## Highlights

- **CPU:** Stress-NX-style Matrixprod workload from the GPLv2 Horizon-OC / Benchmark Toolbox implementation, followed by Hanoi verification for automatic calculation-error detection.
- **RAM:** memtester v4 algorithms integrated directly into the Wizard with automatic mismatch detection.
- **Combined:** CPU Matrixprod/Hanoi + RAM testing under simultaneous load.
- **GPU:** project-original deko3d compute / memory stress test with CPU-side verification.
- **Automation:** 1-minute quick tests and 1-hour validation runs with timer, progress display, automatic PASS/FAIL and persistent crash detection.
- **Recovery:** unfinished-test and no-boot flows preserve the last known-good tuning value.

## Important beta notice

This build compiles successfully in GitHub Actions, but the newly integrated test engines still need real-hardware validation on Mariko / Switch OLED before the project is promoted to stable v0.4.0.

For the first run, use known-stable Horizon OC values and verify that CPU, RAM, Combined and GPU tests behave correctly before using the Wizard to search for voltage limits.

## Installation

1. Download `HOC-Undervolting-Wizard.nro` from the Assets section below.
2. Create `/switch/HOC-Undervolting-Wizard/` on the SD card.
3. Copy the NRO to `/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro`.
4. Launch through Homebrew Menu. Full application/title-takeover mode is strongly recommended for RAM testing.

Existing progress from `/switch/HOC-Battery-Wizard/state.ini` is imported automatically when no new Wizard state exists yet.

## Safety

The Wizard does **not** write Horizon OC settings and does **not** modify `hoc.kip`. All voltage/UV changes remain manual in Horizon OC.

During deliberately unstable RAM testing, avoid installing/updating software or copying important files because unstable memory can corrupt data before a mismatch is reported.

Keep a Hekate CFW entry that can boot without Horizon OC / `hoc.kip` for recovery from settings that prevent normal boot.

## License / credits

HOC Undervolting Wizard v0.4 is licensed under **GNU GPL version 2 only**. See `LICENSE` and `THIRD_PARTY_LICENSES.md` in the source repository for full attribution and provenance, including Horizon-OC / Benchmark Toolbox, Stress-NX credit to Lineon, memtester authors Simon Kirby and Charles Cazabon, deko3d and libnx.

The complete corresponding source is available in this repository under GPL-2.0-only.
