# HOC Undervolting Wizard v0.4.0-beta.24

## Persistent settings now read from Horizon OC config.ini

This beta replaces version-dependent `GetConfigValues()` index mapping for persistent Wizard settings with direct parsing of:

`sdmc:/config/horizon-oc/config.ini`

The Wizard now reads the named Horizon OC 2.5.1 keys used for Preparation and later persistent tuning steps, including:

- `uncapped_clocks`
- `kip_hp_mode`
- `mariko_emc_max_clock`
- `common_emc_mem_volt`
- `mariko_emc_vddq_volt`
- `mariko_cpu_uv_low`
- `mariko_cpu_uv_high`
- `kip_table_conf`
- `mariko_cpu_low_vmin`
- `mariko_cpu_high_vmin`
- `mariko_cpu_max_clock`
- `mariko_cpu_boost_clock`

Missing zero-default keys such as Uncapped Clocks, HP Mode and CPU UV values are treated as zero/OFF. Non-zero required values must be present and match the Wizard target.

Temporary Overrides, live CPU voltage measurements, RAM detection and the automatic VMIN scan still use the `hoc:clk` service.

The raw config debug screen is kept as a diagnostic fallback.
