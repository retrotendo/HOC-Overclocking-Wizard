# HOC Undervolting Wizard v0.4.0-beta.18

## Fix: RAM detection on Horizon OC 2.6.0

Horizon OC 2.6.0 contains an additional `isUsingRetroSuper` byte in `HocClkContext` compared with current HOC main. That shifts `maxDisplayFreq`, `dramID`, and `isDram8GB` by one byte while keeping the full context size at 0x500.

The Wizard previously assumed the current-main layout and therefore read HOC 2.6.0 `maxDisplayFreq` as the DRAM ID, producing `hoc:clk result : 0x00000003` during Hardware Detection.

Beta.18 now supports both known layouts:

- current HOC main: DRAM ID at byte 403
- Horizon OC 2.6.0: DRAM ID at byte 404

Both candidates are validated against the known Mariko DRAM-ID table and the adjacent `isDram8GB` boolean. Ambiguous or unknown future layouts are rejected rather than guessed.

No tuning logic, stress tests, automatic VMIN scan, or override behavior changed from beta.17.
