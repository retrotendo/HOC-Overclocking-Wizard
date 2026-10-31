# HOC Undervolting Wizard v0.4.0-beta.3

Third public beta of the integrated-test HOC Undervolting Wizard.

## New in beta.3 — refined CPU Low VMIN tuning

CPU Low VMIN is now treated as a separate voltage-floor tuning step after CPU Low UV.

### Search range

- Safe starting baseline: **620 mV**
- Search step: **-5 mV**
- Hard Wizard floor: **570 mV**
- The Wizard never requests or accepts a saved Low VMIN below 570 mV.
- Existing beta.2 state files are clamped to 570 mV if they contain a lower value.

### Quick search at 612 MHz

Low VMIN quick-search tests now use:

- CPU **612 MHz**
- GPU **384 MHz**
- RAM **1331.2 MHz**

This intentionally exercises the voltage floor instead of searching VMIN at a CPU clock where the normal UV curve may still sit above the floor.

### Three-stage final Low VMIN validation

After the lowest working VMIN candidate is found, it is validated for **1 hour at each CPU clock**:

1. **612 MHz**
2. **816 MHz**
3. **1020 MHz**

GPU remains at **384 MHz** and RAM at **1331.2 MHz** for all three stages.

Before each individual run, the Wizard reads Horizon OC's live `hoc:clk` context and verifies **CPU + GPU + RAM Temporary Overrides**. The test cannot start unless all three are correct.

If any one of the three long validations fails, Low VMIN is moved **+5 mV safer** and the validation sequence restarts from 612 MHz.

## Existing beta.2 features

- Complete Battery-profile starting setup.
- Hard CPU/GPU/RAM Temporary Override pre-flight before every built-in test.
- CPU Matrixprod + Hanoi verification.
- memtester v4 RAM algorithms.
- Combined CPU + RAM validation.
- deko3d GPU compute/memory stress test.
- Persistent crash/reboot detection and last-known-good recovery.
- The Wizard never writes Horizon OC UV/voltage settings and never modifies `hoc.kip`.

## Installation

1. Download `HOC-Undervolting-Wizard.nro` from Assets.
2. Copy it to:

   `/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro`

3. Launch through Homebrew Menu. Full application/title-takeover mode is strongly recommended for RAM testing.

Existing Wizard state remains in `/switch/HOC-Undervolting-Wizard/state.ini`.

## Beta notice

This build is intended for real-hardware validation on Mariko / Switch OLED. Start from known-stable Horizon OC settings and verify the new Low VMIN flow before relying on the resulting values.

## License / credits

HOC Undervolting Wizard is licensed under **GNU GPL version 2 only**. See `LICENSE` and `THIRD_PARTY_LICENSES.md` for full attribution and provenance.