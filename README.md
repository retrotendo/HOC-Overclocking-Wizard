# HOC Undervolting Wizard

A step-by-step Nintendo Switch homebrew assistant for finding and validating efficient **Horizon OC undervolting settings** on **Mariko / Switch V2 / Lite / OLED**.

The Wizard was created as a companion to **Performance Modes**:

https://github.com/retrotendo/Ultrahand-Performance-Modes

Use it to find stable Battery-profile CPU/RAM values, validate them with built-in stress tests, then save the proven values into Performance Modes.

The Wizard can also be used independently for Horizon OC tuning.

---

# v0.4 integrated test engine

Built-in tests use established open-source workloads:

- **CPU — Stress-NX Matrixprod + Hanoi Verify**
  - Matrixprod workload from the GPLv2 Horizon-OC / Benchmark Toolbox implementation.
  - Hanoi verification detects calculation errors automatically.
  - Benchmark Toolbox credits Stress-NX to **Lineon**.

- **RAM — memtester v4**
  - Stuck Address, Random Value, XOR/SUB/MUL/DIV, Sequential Increment, Solid Bits, Checkerboard, Bit Spread, Bit Flip, Walking Ones/Zeroes and related tests.
  - memtester credits **Simon Kirby** and **Charles Cazabon**.
  - Switch runner adapted from Horizon-OC / Benchmark Toolbox under GPLv2.

- **Combined — CPU + RAM**
  - Matrixprod/Hanoi and RAM stress run together to expose failures that only appear under combined load.

- **GPU — deko3d Compute / Memory Stress**
  - Project-original deko3d compute/memory test.
  - GPU output is verified on the CPU and mismatches fail the test.

Quick boundary tests normally run for **1 minute**. Long validation tests run for **1 hour**. The Low VMIN voltage scan is measurement-only; after the scan, the Wizard runs a long CPU test only at the highest frequency of each distinct measured voltage region.

Before **every built-in test and every VMIN floor probe**, the Wizard reads Horizon OC's live `hoc:clk` context and verifies all three Temporary Overrides:

- CPU
- GPU
- RAM

A missing or wrong override blocks the test. No result is recorded until all three match the requested target.

---

# Full Memory Mode required

The Wizard must be launched from hbmenu in **Full Memory / Application Mode**.

If it is started in **Applet Mode** (for example through Album), the Wizard stops immediately on a dedicated warning screen. The guide and tuning state are not opened and no built-in test can be started.

To launch correctly, hold **R** while starting an installed game and keep holding **R** until hbmenu opens, then start HOC Undervolting Wizard.

This check uses the same `appletGetAppletType()` distinction as nx-hbmenu: only `Application` and `SystemApplication` modes are accepted.

---

# New in v0.4.0-beta.16

## Hardware-aware VDDQ start

- Before Preparation, the Wizard reads Horizon OC's `dramID` and identifies the installed Mariko RAM module.
- The VDDQ baseline is selected automatically from the Horizon OC RAM guidance: **640 mV** for NEE/x267, AA-MGCL, AM-MGCJ, AB-MGCL and NME; **600 mV** for WT:B, WT:F and WT:E.
- The detected RAM module, DRAM ID and chosen VDDQ start are shown before Preparation.
- Unknown/unsupported DRAM IDs are not guessed; detection must succeed before the guided setup continues.

## Verified setting -> guided reboot

Persistent HOC changes now use a dedicated handoff instead of mixing setting instructions and stress tests on one page:

1. The Wizard shows only the **new value that must be changed now**.
2. Press **A** and the Wizard reads Horizon OC's current persistent configuration.
3. A wrong value is shown as **Required / Current / WRONG** and reboot is blocked.
4. A correct value gets a green confirmation such as **Low VMIN 615 mV is set**.
5. Press **A** again to request the console restart.
6. After reopening the Wizard, it first asks whether the console booted normally with the new value.
7. Only after **YES** does the 1-minute/1-hour test page appear.

Values that were already confirmed are no longer repeated as set points on later pages. Temporary Overrides are still shown whenever they must be changed for a test.

## Automatic CPU Low VMIN voltage scan

After the Low VMIN candidate has booted successfully, the Wizard offers one **A = START SCAN** action. From that point the voltage scan runs without further user input.

- The currently active CPU/GPU/RAM Temporary Overrides are saved first.
- GPU is set automatically to **384 MHz** and RAM to **1331.2 MHz**.
- CPU is switched automatically through **510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz**.
- HOC is given time to settle after every frequency change.
- At every CPU point the Wizard takes **3 valid CPU-rail samples** and uses the median.
- Readings are grouped into distinct 5 mV CPU-voltage regions.
- The Temporary Overrides that were active before the scan are restored afterward.
- For each detected voltage region, only the **highest frequency in that region** gets the later 1-hour CPU stability test.

Example: if 510-816 MHz measure ~570 mV, 918 MHz measures ~585 mV and 1020 MHz measures ~600 mV, the Wizard validates **816 @ 570**, **918 @ 585** and **1020 @ 600**.

The detected voltage regions are also written to `results.txt`. The Wizard still does not change persistent Low VMIN/UV/RAM voltage settings automatically; this scan writes only Temporary Overrides.

---

# New in v0.4.0-beta.15

- Redesign the TEST BLOCKED override screen for readability.
- Show each CPU/GPU/RAM override vertically with **Required**, live **Current**, and color-coded **OK / WRONG** status.
- `Current` uses the actual Horizon OC override value; unset overrides show `NOT SET`.
- VMIN floor checks additionally show the applied CPU clock as its own Required/Current/Status block.
- No override detection, tuning, reboot, stress-test, VMIN or updater logic changes.

---

# New in v0.4.0-beta.14

- Correct the Horizon OC menu hierarchy: there is no separate **CPU UV** menu.
- CPU Max, Low/High VMIN, UV Table, Low UV and High UV are all shown under **CPU Settings**.
- Preparation and tuning/recovery screens now use the same real Horizon OC menu path.
- No tuning, reboot, stress-test, VMIN, override or updater logic changes.

---

# New in v0.4.0-beta.13

- Keep the beta.12 right-side layout, but make the application hierarchy explicit.
- Horizon OC values are shown under one **@ Horizon OC** heading, with the actual submenu below it (General, RAM Settings, CPU Settings, CPU UV, Temporary Overrides).
- HOC Toolkit values are separated under **@ HOC Toolkit**.
- Child settings use a compact `- setting : value` table style for quick reading while Ultrahand is open.
- Tuning, reboot, test, VMIN and updater logic are unchanged.

---

# New in v0.4.0-beta.12

- Remove all manual **Save KIP / Save Toolkit** instructions from the active Wizard guide.
- Persistent setting changes now simply tell the user when a **CFW reboot** is required.
- Group every HOC set point under its actual menu area: **General**, **RAM Settings**, **CPU Settings**, **CPU UV**, **HOC Toolkit**, and **Temporary Overrides**.
- Keep the beta.11 tuning/test logic unchanged.
- Expand the GitHub Releases API fallback from 5 to 100 entries; the lightweight `UPDATE.txt` manifest remains the primary update source.

---

# New in v0.4.0-beta.11

- More robust startup updater with two independent metadata sources.
- A simple public `UPDATE.txt` manifest avoids depending only on the unauthenticated GitHub Releases API.
- Update-check failures are shown on screen and can be retried instead of being silently ignored.
- beta.10 tuning and right-side UI behavior are unchanged.

---

# New in v0.4.0-beta.10

- Correct the Ultrahand-friendly panel position based on real Switch OLED testing.
- The right-side panel now starts at console column 36 instead of 82.
- Shorter fixed-width lines avoid wrapping at the screen edge.
- beta.9/beta.8 tuning behavior remains unchanged.

---

# New in v0.4.0-beta.9

## Ultrahand-friendly right-side layout

- Reworked Wizard stage screens into a compact table-style layout.
- All values that must be entered in Horizon OC and all Temporary Override targets are displayed on the right side of the screen so they remain readable while Ultrahand/Horizon OC is open on the left.
- The tuning workflow, reboot points, test logic, dynamic Low VMIN detection, recovery behavior and KNOWN PASS/FAIL shortcuts are unchanged from beta.8.
- `Reboot CFW` is shown only on stages where the persistent HOC value has actually changed.
- Dynamic Low VMIN voltage probing remains internal; the UI simply tells the user which Overrides to set and when to continue.

---

# New in v0.4.0-beta.8

## Startup self-updater

Starting with **beta.8**, the Wizard checks its own GitHub releases when it starts in Full Application Mode.

- If the installed build is current, startup continues normally.
- If a newer build exists, the Wizard asks before doing anything: **A = Download & install**, **B = Not now**.
- The new NRO is downloaded to a temporary `.new` file first.
- The matching release `.sha256` file is downloaded and the NRO is verified with libnx SHA256 before replacement.
- Only after verification does the Wizard rename the current NRO to `.bak` and move the verified `.new` file into place.
- If replacement fails, the old NRO is restored.
- After a successful update the Wizard exits; launch it again from hbmenu to run the new build.
- The previous NRO remains beside the app as `.bak` for recovery and is replaced by the next updater run.

The updater is intentionally **not automatic**: it never installs a release without the user's A-button confirmation. Network/update-check failures are non-fatal and simply continue with the installed build.

The GitHub repository must be public for anonymous in-app update checks; no GitHub token is embedded in the NRO.

**beta.8 itself must be installed manually once. Future builds can then update beta.8 in-app.**

---

# New in v0.4.0-beta.7

- Preparation now shows only the exact Battery-guide starting values.
- Removed all "or known-stable/known-working value" alternatives from the setup screen and setup documentation.
- Previously validated personal values are handled only through **KNOWN PASS / SKIP** during the relevant tuning stages.
- Clarified that Full Application Mode is required, matching the beta.6 startup blocker.

---

# New in v0.4.0-beta.6

- hard startup block when Applet Mode is detected
- clear on-screen Full Memory Mode launch instructions
- no Wizard state/guide/test access until launched as an Application
- beta.5 dynamic VMIN probe and known-result shortcuts retained

---

# New in v0.4.0-beta.5

## Known-result shortcuts

If a value was already tested before using the Wizard, you do not have to repeat every stress test.

During any built-in test stage:

- **A** — run the built-in test normally
- **+** — **KNOWN PASS / SKIP**: accept the current test/value as already known stable
- **X** — **KNOWN FAIL / SKIP**: record the current test/value as a known failure

These shortcuts deliberately bypass the built-in stress test. Use them only for values you already trust from previous testing.

**Exception:** the dynamic VMIN floor-probe stages are measurements, not PASS/FAIL stability tests. There, `A` performs the required measurement, `+` performs the same measurement for convenience, and `X` is disabled.

## Dynamic CPU Low VMIN detection

The frequency where Low VMIN stops controlling CPU voltage is **not assumed to be identical on every Switch**.

Horizon OC builds the Mariko CPU voltage curve from the CPU's own Speedo data, the selected CPU voltage table and CPU UV tuning, then clamps low-voltage entries to Low VMIN. Because of that, the VMIN-to-normal-curve crossover can differ between consoles/settings.

After the Wizard finds a Low VMIN candidate it performs a short ascending sweep:

**510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz**

GPU remains **384 MHz** and RAM remains **1331.2 MHz**.

Starting with beta.16, the Wizard sets these Temporary Overrides itself for this scan. It saves the previous CPU/GPU/RAM overrides, applies the scan clocks, waits for HOC/governor to settle, then reads the **live CPU rail voltage reported by Horizon OC**. Every point uses **3 valid context samples** and the median; samples are accepted only while HOC reports the requested CPU clock as actually applied. After the full scan, the previous Temporary Overrides are restored.

These sweep points are **measurement-only**. They do not each run another 1-minute stress test. Starting with beta.16, all six points are measured so the Wizard can identify every distinct CPU-voltage region, not only the VMIN floor.

Readings are rounded/grouped on HOC's 5 mV voltage steps. The Wizard then selects the **highest CPU frequency in each observed voltage region** for 1-hour CPU validation.

Example: if a console reports roughly 570 mV through 816 MHz, ~585 mV at 918 MHz and ~600 mV at 1020 MHz, the long validations are **816 @ 570**, **918 @ 585** and **1020 @ 600**.

Lower CPU clocks within the same voltage region are computationally less demanding, while normal Home/Sleep/Wake/game transitions remain part of final validation.

---

# Crash / reboot detection

Before every built-in test, the Wizard saves a persistent `testRunning` marker.

If the console freezes, crashes or reboots during a test, the marker remains set. On the next launch the Wizard asks whether the previous test crashed:

- **YES** — count it as FAIL and use the safer recovery path
- **NO** — treat it as a manual interruption and rerun the same test

Cancelling a running test with **B** does not count as FAIL.

---

# Persistent tuning values remain manual

The Wizard does **not** write persistent CPU UV, Low/High VMIN, VDDQ or VDD2 tuning values and does **not** edit `hoc.kip`. Horizon OC remains the place where those tuning values are changed.

The beta.16 automatic Low VMIN scan is the first exception for **Temporary Overrides only**: the Wizard can set CPU/GPU/RAM Temporary Overrides through HOC's public `hoc:clk` IPC, perform the scan, and restore the previous overrides afterward.

Progress is stored at:

`/switch/HOC-Undervolting-Wizard/state.ini`

Final results are stored at:

`/switch/HOC-Undervolting-Wizard/results.txt`

---

# Installation

## Requirements

- Nintendo Switch **Mariko / Switch V2 / Lite / OLED**
- Atmosphere CFW
- Horizon OC installed and working
- Hekate strongly recommended for boot-failure recovery

The Wizard requires Homebrew Menu **title takeover / Full Application Mode**. Applet Mode is blocked at startup.

## Install

1. Download `HOC-Undervolting-Wizard.nro` from the latest GitHub release. Once an updater-capable build is installed, later builds can be installed by the in-app updater.
2. Create:

   `/switch/HOC-Undervolting-Wizard/`

3. Copy the NRO to:

   `/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro`

4. Boot Atmosphere and start the Wizard from Homebrew Menu.

An old state at `/switch/HOC-Battery-Wizard/state.ini` is automatically imported when no new state file exists yet.

---

# Safe boot recovery

Keep a Hekate CFW entry that does **not** load Horizon OC / `hoc.kip`.

If a tuning value prevents normal CFW from booting:

1. Boot Hekate.
2. Start CFW without Horizon OC / `hoc.kip`.
3. Open Horizon OC.
4. Restore the previous known-good value shown by the Wizard.
5. Reboot normally.
6. Continue validation.

---

# Battery starting setup

Prepare the Battery profile before tuning using the exact guide starting values below. If you already know stable values, use the Wizard's KNOWN PASS / SKIP controls during the corresponding tuning stages instead of changing the starting baseline.

## Horizon OC

### General

- **Uncapped Clocks: OFF**

### RAM Settings

- **HP Mode: OFF**
- **RAM Max Clock: 1600 MHz**
- **VDD2: 1175 mV**
- **VDDQ: automatically selected from detected RAM**
  - **640 mV:** NEE/x267, AA-MGCL, AM-MGCJ, AB-MGCL, NME
  - **600 mV:** WT:B, WT:F, WT:E

### CPU Settings

- **CPU Max Clock: lowest selectable value**
  - current Mariko HOC builds show **1963 MHz** as the lowest selectable CPU Max Clock
- **Low VMIN: 620 mV**
- **High VMIN: 750 mV**

- **CPU UV Table: 1683 MHz Tbreak**
- **Low UV: 0**
- **High UV: 0**

## HOC Toolkit

- **CPU Boost Clock: lowest selectable value**
  - stock Nintendo Boost target used by this workflow is **1785 MHz**

The Wizard verifies persistent HOC values before rebooting. When the requested value is detected, a green confirmation is shown and **A** requests the restart. After reopening, confirm whether the console booted normally before the Wizard continues to the stability test.

---

# Wizard tuning order

1. **CPU Low UV**
   - 1020 / 384 / 1331.2
   - +1 UV level per search step
   - 1-minute search, then 1-hour candidate confirmation

2. **CPU Low VMIN**
   - conservative start: 620 mV
   - -5 mV per search step
   - hard Wizard floor: **570 mV**
   - quick boundary search at **510 / 384 / 1331.2**
   - full voltage scan at 510/612/714/816/918/1020 with visible 3-sample progress
   - group the measured values into distinct 5 mV CPU-voltage regions
   - 1-hour confirmation at the **highest frequency of every detected voltage region**
   - then verify Home, Sleep/Wake, game launch/close

3. **RAM VDDQ**
   - 1785 / 76.8 / 1600
   - Wizard search interval: **10 mV**
   - Horizon OC itself exposes 5 mV VDDQ steps, so one Wizard step equals two HOC UI steps
   - 1-minute search, then 1-hour confirmation

4. **RAM VDD2**
   - 1785 / 76.8 / 1600
   - **12.5 mV** per step
   - 1-minute search, then 1-hour confirmation

5. **Final VDDQ + VDD2 together at Boost clocks**
   - 1785 / 76.8 / 1600
   - Memtester for 1 hour
   - if it fails, first try **VDDQ +10 mV**
   - if that still fails, restore VDDQ and try **VDD2 +12.5 mV**

6. **RAM at normal handheld clocks**
   - 1020 / 384 / 1331.2
   - Memtester for 1 hour

7. **CPU High UV**
   - 1785 / 76.8 / 1600
   - +1 UV level per search step
   - 1-minute search, then 1-hour confirmation

8. **High UV + final RAM voltages**
   - 1785 / 76.8 / 1600
   - combined CPU + RAM test for 1 hour
   - if it fails, make High UV one level safer before blaming RAM rails

9. **Final normal handheld validation**
   - 1020 / 384 / 1331.2
   - CPU 1 hour
   - RAM 1 hour
   - GPU 1 hour

10. **Final Nintendo Boost validation**
    - 1785 / 76.8 / 1600
    - CPU 1 hour
    - RAM 1 hour
    - combined CPU + RAM 1 hour

11. **Final real-world validation**
    - remove Temporary Overrides
    - use Home, loading, Sleep/Wake and CPU Boost transitions normally
    - play **The Legend of Zelda: Tears of the Kingdom** for at least 1 hour

---

# Search increments / limits

- CPU Low UV: **+1 level**
- CPU High UV: **+1 level**
- CPU Low VMIN: **-5 mV**, minimum **570 mV**
- RAM VDDQ Wizard search: **-10 mV**
- RAM VDD2: **-12.5 mV**

Horizon OC currently exposes VDDQ in 5 mV increments; the Wizard deliberately uses a coarser 10 mV search to keep the Battery workflow shorter.

---

# Controls

Normal built-in test stages:

- **A** — start built-in test
- **+** — known PASS / skip test
- **X** — known FAIL / skip test
- **B** — exit and save progress
- **Minus** — reset Wizard progress

When a persistent Horizon OC value must change:

- **A** — verify the requested value against Horizon OC
- if correct, a green confirmation screen appears
- **A** again — request console restart
- after reopening: **A = booted normally**, **X = did not boot**, **B = decide later**

Automatic Low VMIN voltage scan:

- **A** — start the complete automatic 510 -> 1020 MHz scan
- no manual Temporary Override changes are required during the scan
- after completion, **A** continues to voltage-region validation

During a running stress test:

- **B** — cancel without recording PASS or FAIL

After an interrupted/crashed test is detected:

- **A** — previous test crashed; record FAIL
- **X** — it was interrupted manually; rerun it

---

# Results and Performance Modes

When the workflow is complete, the Wizard writes:

`/switch/HOC-Undervolting-Wizard/results.txt`

It contains:

- detected RAM module and VDDQ starting point
- CPU Low UV
- CPU Low VMIN
- dynamically detected highest Low VMIN floor clock when available
- every detected CPU voltage region and its highest validated frequency
- RAM VDDQ
- RAM VDD2
- CPU High UV

Use the final values in:

`Performance Modes -> Save Settings -> as Battery Mode`

The Wizard intentionally does not transfer persistent HOC settings automatically.

---

# License and source availability

**HOC Undervolting Wizard v0.4 is free software licensed under GNU GPL version 2 only (`GPL-2.0-only`).**

GPLv2 CPU/RAM test code is incorporated into the executable.

- Complete project license: [`LICENSE`](LICENSE)
- Upstream authors, source paths, modification notes and permissive-library notices: [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)

The built-in test screen displays the active engine's credits and GPL/no-warranty notice.

When distributing an NRO, the corresponding complete buildable source must remain available under GPLv2. The intended release model is to publish the NRO and its source from this same repository.

### Stress-NX provenance

The Wizard does **not** copy code from an unidentified/unlicensed standalone Stress-NX repository. Matrixprod/Hanoi is sourced from the **GPLv2 Horizon-OC / Benchmark Toolbox** source tree, which credits Stress-NX to Lineon.

### memtester provenance

The memory algorithms are from **memtester v4**. The Switch runner is adapted from Horizon-OC / Benchmark Toolbox.

---

# Building from source

Most users should use the prebuilt NRO release.

Developers need devkitPro / devkitA64, libnx, deko3d and `uam`:

```bash
export DEVKITPRO=/opt/devkitpro
make
```

Output:

`HOC-Undervolting-Wizard.nro`

GitHub Actions builds the NRO automatically on pushes and pull requests.

---

# Safety notes

Undervolting stability differs from console to console. A value that works on one Switch may fail on another.

During deliberately unstable RAM testing, avoid installing/updating software or copying important files. RAM instability can corrupt data before an application reports a mismatch.

The built-in tests improve repeatability, but cannot prove absolute stability. Keep the final normal-use and gameplay validation.

## Credits summary

- **Lineon** — Stress-NX / Matrixprod lineage
- **Horizon-OC / Benchmark Toolbox contributors** — GPLv2 CPU and memtester integration source and `hoc:clk` interfaces
- **Simon Kirby** — original memtester work
- **Charles Cazabon** — memtester v2/v4 rewrite
- **fincs / devkitPro** — deko3d
- **switchbrew / libnx authors** — libnx

See `THIRD_PARTY_LICENSES.md` for full notices.
