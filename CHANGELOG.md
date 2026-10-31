## v0.4.0-beta.16
- Detect the installed Mariko DRAM through Horizon OC before Preparation and choose the RAM-specific VDDQ baseline automatically (600 or 640 mV).
- Read persistent Horizon OC config values before every reboot-required tuning step.
- Block reboot if the requested value is not actually set; show Required / Current / WRONG.
- Show a green confirmation when the requested value is detected, then reboot only after a second A-button confirmation.
- Persist the reboot handoff and ask whether CFW booted normally when the Wizard is reopened.
- Separate setting pages from test pages so already-confirmed UV/voltage values are not repeatedly shown.
- Add a fully automatic Low VMIN voltage scan using Horizon OC's public Temporary Override IPC.
- Save the previous CPU/GPU/RAM overrides, automatically apply GPU 384 / RAM 1331.2 and CPU 510/612/714/816/918/1020, then restore the previous overrides after the scan.
- Add a visible 3-sample progress bar to CPU voltage scans and automatically retry once if HOC/context settling is late.
- Group the observed CPU voltages into 5 mV regions.
- Run the 1-hour CPU validation at the highest frequency of **each** detected voltage region instead of only the Low VMIN floor region.
- Record detected RAM and CPU voltage regions in `results.txt`.
- Keep beta.15's vertical Required / Current / OK-WRONG Temporary Override blocker.

## v0.4.0-beta.15
- Redesign TEST BLOCKED override screen into vertical Required / Current / Status blocks.
- Show actual Horizon OC override values for CPU/GPU/RAM.
- Color WRONG red and OK green.
- Keep applied CPU clock visible during VMIN floor checks.
- No tuning or test logic changes.

## v0.4.0-beta.14
- Fix Horizon OC menu naming: CPU UV controls are part of CPU Settings.
- Merge CPU Max / VMIN / UV controls into one CPU Settings block in Preparation.
- Use CPU Settings on all Low UV / High UV / recovery screens.
- No tuning/test logic changes.

## v0.4.0-beta.13
- Add top-level `@ Horizon OC` / `@ HOC Toolkit` headings.
- Keep Horizon OC submenu names as second-level headings.
- Use compact child-row formatting for settings and Temporary Overrides.
- No tuning/test logic changes.

# Changelog

## v0.4.0-beta.12

- Remove manual Save KIP / Save Toolkit prompts from the active Wizard flow and documentation.
- Keep required CFW reboot instructions where persistent settings change.
- Label set points by their HOC menu area: General, RAM Settings, CPU Settings, CPU UV, HOC Toolkit and Temporary Overrides.
- Preserve beta.11 tuning, stress-test, VMIN, skip and recovery logic.
- Increase the GitHub Releases API fallback window from 5 to 100 releases.

## v0.4.0-beta.11

- Make startup update checks resilient to GitHub API failures.
- Add a lightweight public `UPDATE.txt` manifest as a second update source.
- Keep the GitHub Releases API as a fallback and choose the newest version returned by either source.
- Show update-check errors instead of silently continuing, with A = Retry and B = Continue.
- Send no-cache headers for update metadata requests.
- No tuning/test/UI-position logic changes from beta.10.

## v0.4.0-beta.10

- Fix the beta.9 right-side UI start column after real-hardware validation.
- Move the compact Wizard panel from console column 82 to column 36 so it sits immediately to the right of Ultrahand.
- Shorten the divider and override-error table to prevent wrapping at the right edge.
- No tuning, test, updater, VMIN, reboot or recovery logic changes.

## v0.4.0-beta.9

- Redesign tuning-stage UI into a compact right-side table layout for use alongside the Ultrahand/Horizon OC overlay.
- Keep Set in HOC values, Temporary Overrides, test type/duration and controls visible on the right half of the screen.
- Preserve beta.8 tuning/test/reboot/skip logic unchanged.
- Hide dynamic VMIN probe implementation details from the normal workflow while retaining the same automatic voltage measurement.
- Show Save KIP + Reboot only when a persistent HOC setting was changed.

## v0.4.0-beta.8

- Add an opt-in startup self-updater for public GitHub releases.
- Check the newest release before loading Wizard state, only in Full Application Mode.
- Ask before installation: A installs, B continues the current build.
- Download updates to `.new`, verify against the release SHA256, then replace the current NRO.
- Keep the previous NRO as `.bak` and restore it automatically if replacement fails.
- Use the actual hbloader `argv[0]` NRO path when available, with the standard Wizard path as fallback.
- Network/update failures are non-fatal and do not affect tuning state.
- Link the devkitPro `switch-curl` portlib for HTTPS GitHub access.

## v0.4.0-beta.7

- Use only the exact Battery-guide baseline values on the Preparation screen.
- Remove alternative "known-stable" and "known-working" setup values.
- Keep previously validated user values supported through KNOWN PASS / SKIP at the relevant test stages.
- Clarify Full Application Mode as required rather than recommended.

## v0.4.0-beta.6

- Block startup completely when hbmenu launches the Wizard in Applet Mode.
- Detect Full Memory Mode using `appletGetAppletType()`; only Application/SystemApplication are accepted.
- Show a dedicated warning with R-button title-takeover instructions instead of opening the guide.
- Keep beta.5 dynamic VMIN probing and known PASS/FAIL shortcuts unchanged.

## v0.4.0-beta.5

- Changed the dynamic CPU Low VMIN crossover sweep from repeated 1-minute stress tests to a fast **measurement-only floor probe**.
- Floor probing still verifies all three Horizon OC Temporary Overrides before every step.
- At each probe point, the Wizard samples the live CPU rail voltage **3 times with 1.1 seconds between reads** and uses the **median** of valid samples and only accepts them while HOC reports the requested CPU clock as actually applied so a stale single HOC poll cannot decide the crossover.
- Probe sequence remains **510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz** with GPU 384 / RAM 1331.2.
- The Wizard still selects the **highest CPU clock actually operating on the configured Low VMIN floor** and runs the single 1-hour CPU confirmation there.
- Lower CPU clocks on the same voltage floor are no longer stress-tested redundantly; transition checks such as Home, Sleep/Wake and game launch/close remain part of final validation.
- `[+] KNOWN PASS / SKIP` remains available for real test stages. During VMIN floor-probe stages, pressing `+` performs the required live-voltage measurement instead of blindly skipping it.
- `[X] KNOWN FAIL / SKIP` is disabled during measurement-only VMIN floor-probe stages because a voltage probe itself is not a stability PASS/FAIL test.
- Override-block screens now distinguish between a blocked stress test and a blocked VMIN measurement.

## v0.4.0-beta.4

- Synced the Wizard with the revised Battery Tuning guide.
- Added **[+] KNOWN PASS / SKIP** so already-proven settings can be accepted without rerunning every built-in test.
- Kept **[X] KNOWN FAIL / SKIP** for manually known failures.
- Corrected preparation guidance: CPU Max Clock is the **lowest selectable Horizon OC value** (currently 1963 MHz on Mariko), while Nintendo CPU Boost is handled separately through HOC Toolkit.
- Changed the recommended CPU UV table guidance to **1683 MHz Tbreak** (or another user-known stable table).
- Kept CPU Low VMIN at a **620 mV conservative baseline** with a hard Wizard floor of **570 mV**.
- Reworked Low VMIN tuning to use **dynamic floor detection** instead of assuming the same crossover frequency on every console.
- The Wizard now reads Horizon OC's live CPU rail voltage from `hoc:clk` during the Low VMIN sweep.
- Low VMIN quick search now runs at **510 / 384 / 1331.2 MHz**.
- After the VMIN candidate is found, the Wizard sweeps CPU **510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz** and automatically remembers the highest CPU clock still operating at the configured VMIN floor (within one 5 mV PMIC step).
- The long 1-hour Low VMIN confirmation is then run only at that dynamically detected highest floor-bound CPU clock.
- Added a separate **VDDQ + VDD2 combined RAM validation at 1785 / 76.8 / 1600** before normal-handheld RAM validation.
- Changed the Wizard's VDDQ search interval to **10 mV** to match the simplified guide workflow (two 5 mV Horizon OC UI steps).
- Added guide-style RAM-pair recovery: first retry combined RAM validation with VDDQ +10 mV; if it still fails, restore VDDQ and try VDD2 +12.5 mV.
- Results now record the dynamically detected highest Low VMIN floor clock when available.

## v0.4.0-beta.3

- Changed CPU Low VMIN hard floor from 550 mV to **570 mV**.
- Moved Low VMIN quick search to **612 / 384 / 1331.2 MHz**.
- Added sequential 1-hour Low VMIN validation at **612 -> 816 -> 1020 MHz**.
- CPU/GPU/RAM Temporary Overrides are verified before every validation run.
- Any failure in the three-stage VMIN validation raises Low VMIN by **5 mV** and restarts validation.
- Existing beta.2 state files are clamped to the new 570 mV minimum on load.

## v0.4.0-beta.2

- Added the full Battery-guide starting setup to the Wizard preparation screen.
- Added a hard Horizon OC pre-flight before every built-in test.
- CPU, GPU and RAM Temporary Overrides are all read from `hoc:clk` and compared with the exact test target.
- A missing/wrong override blocks the test and shows Expected vs Current values; no PASS/FAIL is recorded.

All notable changes to HOC Undervolting Wizard are documented here.

The project follows semantic versioning where practical. Pre-release builds are used until the integrated stress-test engine has been validated on real Switch hardware.

## [0.4.0-beta.1] - 2026-10-22

### Added
- Integrated CPU stability testing using the GPLv2 Matrixprod workload from Horizon-OC / Benchmark Toolbox plus Hanoi verification.
- Integrated memtester v4 RAM validation with automatic mismatch detection.
- Combined CPU + RAM validation mode.
- Integrated deko3d GPU compute / memory stress test with result verification.
- 1-minute quick-search tests and 1-hour validation tests with on-screen timer and progress.
- Persistent `testRunning` marker for crash/reboot detection.
- Automatic PASS/FAIL handling for detected test results.
- Recovery flow for unfinished tests and no-boot HOC settings.
- `THIRD_PARTY_LICENSES.md` with upstream attribution and provenance.

### Changed
- Project renamed to **HOC Undervolting Wizard**.
- Project license changed to **GPL-2.0-only** because GPLv2 CPU/RAM test code is incorporated into the executable.
- README expanded with installation, safe-boot recovery, test workflow and Performance Modes integration guidance.
- GitHub Actions now builds `HOC-Undervolting-Wizard.nro`.

### Notes
- This is a **beta pre-release**. The source compiles successfully in GitHub Actions, but the integrated test engines still require validation on real Mariko / Switch OLED hardware before a stable v0.4.0 release.
- HOC settings are still changed manually in Horizon OC. The Wizard never edits `hoc.kip` directly.

## [0.2.0] - 2026-10-22

### Added
- Guided undervolting workflow with persistent state.
- Battery-profile-oriented CPU and RAM tuning sequence.
- Safe recovery guidance after no-boot settings.
- Migration from the original HOC Battery Wizard state path.

### Changed
- Renamed from HOC Battery Wizard to HOC Undervolting Wizard.
