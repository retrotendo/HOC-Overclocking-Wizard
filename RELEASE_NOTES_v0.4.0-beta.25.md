# HOC Undervolting Wizard v0.4.0-beta.25

## Current-settings baseline

Preparation now offers `X : Use current settings as baseline` both on the Preparation page and on the Preparation check page.

When selected, the Wizard keeps the controlled test environment requirements (Uncapped Clocks OFF, HP Mode OFF, RAM Max 1600 MHz, CPU Max 1963.5 MHz, 1683 MHz Tbreak table and 1785 MHz Boost) but adopts already-tuned values from `config.ini` as the starting baseline:

- CPU Low UV
- CPU Low VMIN
- RAM VDDQ
- RAM VDD2
- CPU High UV

Later tuning stages continue downward from those adopted values instead of returning to the guide defaults.

## CPU Low UV boot-limit search

CPU Low UV no longer runs a stress test after every successful reboot.

New flow:

1. Set the next Low UV step.
2. Reboot.
3. If the console boots, continue to the next Low UV step.
4. Repeat until a value does not boot, or the Wizard search limit is reached.
5. Restore the last bootable Low UV value.
6. Run the 1-minute CPU validation.
7. If that passes, run the 1-hour CPU validation.
8. If the 1-minute validation fails, back off one additional Low UV step and retry the quick validation.

The new validation stage was appended to the stage enum so existing persisted stage numbers remain compatible.
