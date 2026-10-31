# HOC Undervolting Wizard v0.4.0-beta.28

## Automatic Preparation setup

Preparation now offers a third path:

- `A`: Check settings manually
- `X`: Use the current compatible settings as the tuning baseline
- `Y`: Set the displayed Preparation values automatically and reboot

The automatic path first asks for confirmation, then updates only the required keys in `sdmc:/config/horizon-oc/config.ini`, reads the file back, and requests a reboot only when the expected values are verified.

The automatic Preparation values are the same ones shown on the Preparation page:

- Uncapped Clocks: OFF
- HP Mode: OFF
- RAM Max: 1600 MHz
- VDD2: 1175 mV
- VDDQ: detected module-specific starting value
- CPU Max: 1963.5 MHz
- Low VMIN: 620 mV
- High VMIN: 750 mV
- UV Table: 1683 MHz Tbreak
- Low UV: 0
- High UV: 0
- CPU Boost: 1785 MHz

A backup of the previous Horizon OC config is created as `config.ini.wizard.bak`. Other Horizon OC keys are preserved.

The normal manual Preparation check remains unchanged and still proceeds to the reboot page after a successful check.
