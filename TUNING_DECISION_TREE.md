# OC Wizard tuning decision tree

This document is the implementation contract for the adaptive OC guide.

## Non-negotiable rule

**No end value from the development/test console is a target.** Development measurements are evidence for relationships and diagnostic rules only. HOC/platform documentation supplies safety boundaries; the active console supplies the tuning results.

## Measurement model

Every retained point should record, where available:

- requested and real clock
- relevant rail voltage(s)
- benchmark performance (RAM score/latency, GPU FPS, CPU FPS)
- stability result
- combined-stability context
- comparable battery-side power telemetry

Each domain exposes three distinct results:

- **Stable Max**: highest validated point inside the supported safety envelope
- **Sweet Spot**: knee of measured performance versus electrical cost
- **Recommended**: daily/system recommendation after all later combination tests

## RAM

1. Detect DRAM and select the matching HOC table row.
2. Use Common timings and conservative table voltages as the starting baseline.
3. Sweep RAM clocks within the DRAM-informed search range; do not assume the table average is the device maximum.
4. Build the RAM performance curve and identify Stable Max / initial Sweet Spot.
5. Only after the clock region is known, optionally test Super Tight timings.
6. Optimize HP/DVB/VDD2/VDDQ/SoC one domain at a time with rollback on failure.
7. Keep measurement history because later GPU/CPU combination tests may lower the final RAM recommendation.

## GPU

1. Keep CPU conservative and use a safe RAM context for the initial GPU voltage/performance curve.
2. Tune GPU points individually and record real voltage + FPS/performance.
3. Do not assume an individually stable GPU point is stable with fast RAM.
4. Re-test important/recommended GPU points with the RAM recommendation.
5. On GPU + RAM failure, diagnose one domain at a time: first make the GPU point safer and retest; if that does not solve it, restore GPU and test the RAM/SoC side. Compare one-step backoffs before choosing the final system recommendation.
6. Keep HOC's RAM-dependent GPU DVFS floor relationship intact unless a later dedicated test proves a change beneficial.

## CPU

1. Use final/recommended RAM for the decisive CPU validation, because RAM can change CPU voltage requirements.
2. Measure the High region and the Low region rather than assuming one fixed TBreak.
3. High UV must be checked at more than only the maximum CPU clock; a lower point can be the combined-load failure point.
4. Low UV and Low VMIN are a coupled curve problem. Do not independently chase the lowest VMIN and most aggressive Low UV.
5. Use 1020 MHz as an important Low-region stability anchor and also validate an upper Low-region point near the eventual TBreak.
6. Choose TBreak after both Low and High curves are known. Place the transition where the measured curves give the cleaner/lower stable voltage transition, then revalidate the moved boundary with final RAM.
7. Tune High VMIN after TBreak.
8. Tune VMAX last. Every VMAX test must verify **real clock**; a voltage cap that silently reduces real frequency is not a successful undervolt.

## Combined-failure diagnosis

A failure proves only that the combination is unstable. It does not identify the guilty domain.

- Change exactly **one** variable/domain.
- Re-run the same test.
- PASS: that change identifies a likely limiting side; validate it longer.
- FAIL: restore the change before trying the next domain.
- Never accumulate several speculative changes.

For CPU + RAM failures, compare a safer CPU UV step against a one-step RAM/SoC/VDD2 correction/backoff. For GPU + RAM failures, compare a safer GPU point against a one-step RAM-side correction/backoff. Prefer the system solution with the smallest measured performance loss and best stability/electrical cost.

## Feedback loop

RAM, GPU and CPU sections are not final when their first graph is shown. Later combined validation may reopen an earlier recommendation. The graph/history should preserve the original measurement and mark the final recommendation as adjusted by combined validation.

## Daily recommendation

The lowest technically stable value or highest technically stable clock is not automatically the daily recommendation. Prefer a small stability margin when the extra performance/efficiency from the edge point is negligible.
