# HOC Overclocking Wizard

A guided, adaptive Nintendo Switch overclocking assistant for **Horizon OC** on **Mariko** systems (Switch V2 / Lite / OLED).

The Wizard is intentionally **device-specific**. It does not copy one console's MHz or mV values. RAM, GPU and CPU limits are measured on the current console and the final recommendations are derived from stability, real clocks, benchmark performance and electrical cost.

## Core workflow

1. Detect console and DRAM type.
2. Create a safety backup and establish a known HOC baseline.
3. Apply the DRAM-specific **Common** timing baseline from the Horizon OC RAM table.
4. Measure the RAM clock curve, then validate optional Super Tight timings and optimize RAM rails / SoC one variable at a time.
5. Measure and tune the GPU curve, then validate GPU + RAM together.
6. Measure the CPU curve with final RAM, determine Low/High UV behavior and TBreak from the measured transition, then tune High VMIN and VMAX last.
7. Re-open earlier recommendations when a later combined test proves that another system-level point is better.
8. Show graphs for Stable Max, Sweet Spot and Recommended values.
9. Save the final HOC profile to **Performance Modes · OC Mode**.

## Adaptive decisions

The Wizard keeps all measured points instead of treating a completed section as permanently fixed. A later CPU + RAM or GPU + RAM failure can cause the Wizard to compare one-step backoffs and revise an earlier RAM/GPU/CPU recommendation when the performance loss is small but stability or electrical cost improves substantially.

**Only one setting is changed at a time during diagnosis.** If a diagnostic change does not fix the failure, that setting is restored before another domain is tested.

## Benchmark conditions

For comparable measurements the Wizard expects the console to remain on the same charger and in the same operating state for a measurement series. Start with a fully charged battery, set brightness to **100%**, and disable automatic screen dimming / sleep while tuning.

Performance measurements are based on the embedded Horizon OC / Benchmark Toolbox workloads:

- RAM: memory bandwidth + latency benchmark
- GPU: Furmark/Benchmark Toolbox FPS measurement plus GPU stability verification
- CPU: Benchmark Toolbox CPU Ray Trace FPS plus CPU/combined stability tests

HOC voltage and battery-side power telemetry are recorded alongside benchmark data. Battery-fuel-gauge power is treated as supplemental telemetry, not as wall-power measurement.

## Safety

Overclocking and RAM tuning can crash the console and can risk SD/NAND corruption. Keep current backups before starting. The Wizard uses Horizon OC's documented platform limits as safety/search boundaries, but no overclock is guaranteed safe or stable on every device.

This is an early beta. Review every requested change and keep a known-good CFW/No-OC recovery path available.

## Credits / license

HOC Overclocking Wizard is GPL-2.0. It incorporates/adapts GPL-compatible components and interfaces from Horizon OC / Benchmark Toolbox and the existing HOC Undervolting Wizard foundation. See source headers and `LICENSE` for attribution.
