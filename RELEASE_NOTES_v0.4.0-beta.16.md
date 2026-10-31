# HOC Undervolting Wizard v0.4.0-beta.16

This beta is a larger workflow update focused on hardware-aware RAM setup, clearer reboot handoffs and more complete CPU Low VMIN validation.

## Automatic RAM detection and VDDQ baseline

Before Preparation, the Wizard now reads Horizon OC's DRAM ID and identifies the installed Mariko RAM module.

The VDDQ starting point is selected automatically from the Horizon OC RAM guidance:

- **640 mV:** NEE/x267, AA-MGCL, AM-MGCJ, AB-MGCL, NME
- **600 mV:** WT:B, WT:F, WT:E

The detected module, DRAM ID and selected baseline are shown before Preparation. Unknown/unsupported DRAM IDs are not guessed.

## Verified setting and guided reboot

Persistent HOC changes now use a separate setting/reboot phase:

1. The Wizard shows only the value that must be changed now.
2. A reads the current Horizon OC persistent configuration.
3. A wrong value blocks reboot and shows **Required / Current / WRONG**.
4. A correct value shows a green confirmation such as **Low VMIN 615 mV is set**.
5. Press A again to request the console restart.
6. After reopening the Wizard, confirm whether CFW booted normally with the new value.
7. The relevant 1-minute or 1-hour test is shown only after a successful boot confirmation.

Already-confirmed persistent values are no longer repeated on later test pages.

## Fully automatic CPU Low VMIN voltage scan

The first automatic Temporary Override workflow is now implemented for the Low VMIN scan.

After the Low VMIN candidate has booted successfully, the Wizard asks once before starting. Press **A = START SCAN** and it then runs the complete measurement without further user input:

1. Saves the currently active CPU/GPU/RAM Temporary Overrides.
2. Sets GPU to **384 MHz** and RAM to **1331.2 MHz** automatically.
3. Switches CPU automatically through **510 -> 612 -> 714 -> 816 -> 918 -> 1020 MHz**.
4. Waits for HOC/governor to settle at each frequency.
5. Takes **3 valid HOC CPU-rail samples** at each point and uses the median.
6. Groups the readings into HOC's 5 mV CPU-voltage regions.
7. Restores the Temporary Overrides that were active before the scan.
8. Shows the detected regions and the highest clock still on the configured Low VMIN floor.

The scan automatically retries once if a clock/context update is late. If HOC refuses an override or three valid readings cannot be obtained, the scan stops and reports the problem instead of accepting incomplete data.

The Wizard does **not** write persistent Low VMIN/UV/RAM voltage settings. Only Temporary Overrides are written during this automatic scan.

## CPU voltage-region validation

Instead of validating only the highest clock still on the Low VMIN floor, beta.16 identifies every distinct measured CPU-voltage region and runs the 1-hour CPU test at the **highest frequency of each region**.

Example:

- 510-816 MHz @ ~570 mV -> validate **816 MHz**
- 918 MHz @ ~585 mV -> validate **918 MHz**
- 1020 MHz @ ~600 mV -> validate **1020 MHz**

Detected voltage regions are written to `results.txt` together with the final tuning values.

## Existing beta.15 behavior retained

- Ultrahand-friendly right-side layout
- vertical TEST BLOCKED Required / Current / OK-WRONG display for manual test overrides
- actual live CPU/GPU/RAM override values
- Full Application Mode requirement
- built-in CPU/RAM/Combined/GPU stress engines
- known PASS / FAIL shortcuts
- startup self-updater

## Important beta note

The code builds in the devkitPro CI environment, but the new DRAM detection, persistent-setting verification, automatic reboot handoff and automatic Temporary Override scan still require real-hardware validation. This remains a pre-release.
