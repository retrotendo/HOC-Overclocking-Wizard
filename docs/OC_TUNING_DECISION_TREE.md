# HOC Overclocking Wizard – Adaptive Tuning Decision Tree

This document defines the tuning logic for the OC Wizard. It is the behavioral specification for the app.

## Core principle

The Wizard must never copy end values from a reference console. A reference console is useful only to learn relationships between domains and to validate the method.

Every recommendation must be derived from the current device using measured stability, real clock, rail voltage and benchmark performance.

The Wizard distinguishes three different results for every domain:

- **Technical / Stable Max** – highest point that passed the defined validation.
- **Validated Stable** – point that passed the required long/combined validation.
- **Recommended / Daily Sweet Spot** – device-specific point selected from the measured performance-vs-cost curve, with stability reserve.

Maximum is not automatically the recommendation.

## Global safety rules

1. Change only one variable at a time during diagnosis.
2. If the changed variable does not fix the failure, restore it before trying another variable.
3. Before every benchmark, stress test and reboot, verify all Wizard-controlled settings against the expected state.
4. Always verify **Real Clock**, not only the requested/target clock. A voltage cap that lowers Real Clock is not a successful undervolt.
5. Persistent KIP/config changes are saved, rebooted and verified before continuing.
6. Temporary frequency overrides are restored after each measurement series.
7. Later combined tests are allowed to reopen an earlier RAM/GPU/CPU recommendation.
8. If an earlier recommendation changes, all dependent later validations are invalidated and repeated where necessary.
9. HOC safety limits define the allowed search envelope. They are ceilings/floors, not target values.
10. Unknown DRAM / ambiguous 8 GB upgrade IDs never receive guessed automatic timings.

## Benchmark preparation

For comparable measurements the app requires a fixed environment for one tuning run:

- console charged to 100% before starting; app accepts >=95% to avoid false rejection at the fuel-gauge boundary
- charger connected and reported as sufficient power
- fixed brightness: 100%
- screen dimming / auto-sleep disabled while tuning
- same dock/handheld condition for one measurement series
- no downloads or unrelated background stress where practical

The app records HOC telemetry with each benchmark point:

- requested and Real CPU/GPU/RAM clocks
- CPU/GPU/SoC/VDD2/VDDQ rails where exposed
- HOC/MAX17050 battery-side Power/Current when available
- benchmark performance
- stability result
- test context (isolated vs combined)

Battery-side power is supplementary telemetry. It is not labeled as wall/input power and is not trusted as the primary efficiency metric when the battery is full and charging.

---

# Phase 1 – Hardware and RAM preparation

## 1. Detect hardware

Detect console type and DRAM ID.

Map a known Mariko DRAM ID to the current HOC RAM profile table:

- expected clock class / search envelope
- safe VDD2 baseline
- safe VDDQ baseline
- Common timing preset
- Super Tight timing preset

These table values are **starting conditions and search bounds only**.

## 2. Establish a recoverable baseline

Before writing tuning values:

- back up current HOC config and hoc.kip
- record current active values
- set uncapped clocks and the required test controls
- use HP mode and the profile-defined safe electrical baseline
- apply Common timings first

Do not begin with Super Tight timings. Clock capability must be found before aggressive timing validation.

---

# Phase 2 – RAM clock capability

## 3. RAM clock sweep with conservative rails

Sweep supported RAM frequency steps inside the detected profile envelope.

For each point:

1. set only RAM frequency through Temporary Override
2. verify requested and Real RAM frequency (PLL/drop check)
3. run short RAM stability screening
4. run Benchmark Toolbox memory benchmark
5. record bandwidth, full-RAM latency, score and telemetry

Stop upward search after the first confirmed unstable / PLL-invalid point. The previous point becomes the current Stable Max candidate.

Do not call it Daily/Recommended yet.

## 4. RAM timing comparison

After the clock sweep:

- apply Super Tight timings
- reboot and verify
- retest the current Recommended/upper candidate

If ST fails:

- restore Common timings first
- optionally test ST one RAM step lower
- compare Common@higher-clock vs ST@lower-clock by measured performance and electrical cost

Choose the better device-specific branch. Do not assume ST is always superior.

---

# Phase 3 – RAM electrical optimization

The purpose of this phase is to measure the real cost of the upper RAM region before selecting the Daily point.

## 5. VDD2

At the current RAM candidate:

- lower VDD2 one HOC step at a time
- reboot / verify
- quick RAM test after every step
- first fail -> restore one step above the failure
- long validate the retained point

VDD2 is a global RAM rail. A higher RAM maximum can therefore make lower clocks more expensive too. This is one reason the technical max can lose to a lower Daily point.

## 6. VDDQ

With validated VDD2 fixed:

- lower VDDQ one HOC step at a time
- never lower VDDQ and VDD2 simultaneously while discovering limits
- fail -> restore previous VDDQ
- validate retained point

## 7. SoC voltage table

For the relevant upper RAM frequency points:

- tune the matching SoC table point downward one step at a time
- quick stability first
- final candidate gets long RAM validation and a real-world/combined check later

Keep one-domain-at-a-time diagnostics.

## 8. Re-benchmark upper RAM points

After rails are tuned, remeasure the upper candidate points so that the graph reflects the actual cost of each point, not the initial conservative baseline.

RAM analysis outputs:

- Stable Max
- Sweet Spot (curve knee)
- Recommended

The graph shows RAM MHz vs measured performance and electrical cost, with all three markers.

---

# Phase 4 – GPU intrinsic curve

RAM can raise the GPU DVFS minimum voltage. Therefore the intrinsic GPU curve must not be discovered only under maximum RAM.

## 9. Establish a controlled RAM context

Temporarily use a controlled/base RAM state that does not mask the GPU table with a high RAM-induced GPU floor.

Keep CPU conservative.

## 10. GPU frequency and voltage sweep

For each supported safe GPU frequency:

1. set GPU frequency
2. verify Real Clock
3. determine the lowest stable GPU voltage / table point using one voltage step at a time
4. run GPU benchmark/stress and require zero mismatches
5. record GFLOPS/performance and telemetry

The Wizard builds a device-specific GPU curve. No sample-device mV value is used.

GPU DVFS floor behavior is left on the HOC safe/automatic path during initial tuning. Negative DVFS offset is not blindly optimized.

## 11. GPU graph

Analyze the intrinsic GPU curve and mark:

- Stable Max
- Sweet Spot
- preliminary Recommended

This is not final until RAM interaction is checked.

---

# Phase 5 – GPU + RAM interaction

## 12. Validate GPU against Recommended RAM

Restore the current Recommended RAM configuration and validate GPU anchors around:

- GPU Recommended
- GPU Stable Max
- any frequency where the RAM-induced GPU floor intersects the manual GPU voltage curve

## 13. GPU+RAM failure decision tree

If a combined GPU+RAM test fails:

### Trial A – GPU side

- make GPU voltage one step less aggressive
- keep RAM unchanged
- repeat the same combined test

If PASS: record that GPU margin was the limiter and keep the smallest correction that validates.

If FAIL: restore GPU to the previous value before continuing.

### Trial B – RAM electrical side

Change only one of the following at a time, restoring it if it does not help:

1. SoC one step higher
2. VDD2 one step higher

If either fixes the combination, compare its electrical cost against backing RAM down one clock step.

### Trial C – RAM frequency backstep

- restore rail changes that did not help
- reduce RAM by one step
- repeat combined GPU test

If one RAM step costs little measured performance but removes a large voltage/stability penalty, the Wizard may revise the earlier RAM recommendation downward.

The previous RAM Stable Max remains visible in the graph; only Recommended changes.

Any changed RAM recommendation invalidates downstream combined validations.

---

# Phase 6 – CPU High region

CPU tuning is performed with the current Recommended RAM because high RAM can invalidate a CPU curve that looked stable with stock RAM.

A stock/base-RAM diagnostic is used only when a failure needs attribution.

## 14. Find device-specific CPU usable range

Sweep supported HOC CPU clocks inside the safe envelope.

At each point:

- verify Real Clock
- run CPU Ray Trace benchmark (FPS)
- record CPU voltage and telemetry
- perform quick CPU stability screening

Stop or recommend backing down when the next clock requires a disproportionate voltage increase for little performance gain, even if it is technically stable.

The safety envelope comes from HOC/platform rules; the final clock comes from the current device.

## 15. High UV search

Find the most aggressive High-UV level that is stable with Recommended RAM.

Do not validate only the highest frequency. Validate at least:

- top High-region point
- lower High-region / near-TBreak point
- any point where prior screening reports instability

If a High-UV level fails in combination, move one level less aggressive and retest. If that does not fix it, restore the CPU change and enter the CPU+RAM diagnostic tree rather than assuming the CPU is at fault.

---

# Phase 7 – CPU Low region

## 16. Low UV and Low VMIN are optimized as a pair

Do **not** search for the smallest Low VMIN and the highest UV level independently.

Low VMIN anchors/floors the lower part of the curve while Low UV changes the shape/steepness above that floor. The best combination is device-specific.

For each promising combination, measure a small set of anchor frequencies:

- very low/boot region
- 1020 MHz normal CPU clock
- one middle point
- highest Low-region point below TBreak

## 17. Critical Low stability test

1020 MHz is a primary combined CPU+RAM stability anchor because it can sit close to the lowest voltage while being a real normal operating clock.

Validate:

- 1020 + Recommended RAM
- highest Low-region point + Recommended RAM

If either fails, do not infer the cause from displayed mV alone. Compare another Low-UV/VMIN combination and, if necessary, isolate with lower/base RAM.

---

# Phase 8 – TBreak selection

## 18. Choose TBreak only after both CPU curves are known

Do not hardcode the reference console's TBreak.

For the supported TBreak candidates around the Low/High transition:

- measure the boundary frequency on the Low table
- measure the same/adjacent boundary frequency on the High table
- compare real voltage, stability and continuity of the curve

Choose the split that gives the lower stable cost and avoids an unnecessary voltage spike.

A CPU that is more efficient on the High table at a lower transition frequency may receive a lower TBreak. Another CPU may keep the standard/higher TBreak.

After changing TBreak, revalidate any frequency that moved from Low to High or High to Low with Recommended RAM.

---

# Phase 9 – High VMIN and VMAX

## 19. High VMIN

Tune High VMIN only after High UV and TBreak are fixed.

It is primarily a floor. Lower it one step at a time and retest the lower High-region anchor. Do not chase a lower floor if it no longer changes the actual voltage curve.

## 20. CPU VMAX

Tune VMAX last.

At the highest retained CPU frequency:

- lower VMAX one step at a time
- run load
- verify **Real Clock remains at the requested frequency**
- validate stability

If Real Clock drops, the cap is too low even if the test itself does not crash. Restore the previous VMAX.

---

# Phase 10 – CPU + RAM adaptive validation

## 21. Combined anchors

Validate at minimum:

- critical Low point (1020)
- upper Low / TBreak boundary
- lower High point
- CPU Recommended
- CPU Stable Max when it is retained as an available benchmark point

## 22. CPU+RAM failure decision tree

If a combined CPU+RAM test fails:

### Trial A – CPU side

- make the relevant CPU UV setting one step less aggressive
- change nothing else
- retest

PASS -> CPU margin was the limiting side.

FAIL -> restore the CPU UV setting before continuing.

### Trial B – RAM SoC

- raise only the relevant SoC table point one step
- retest

FAIL -> restore SoC.

### Trial C – VDD2

- raise only VDD2 one step
- retest

FAIL -> restore VDD2.

### Trial D – RAM backstep

- reduce RAM one frequency step
- retest the original CPU configuration

The Wizard compares the alternatives using measured performance and electrical cost. If a one-step RAM reduction loses little performance but avoids a much larger CPU/rail penalty, it revises RAM Recommended downward and revalidates GPU+RAM and CPU+RAM dependencies.

This is the key adaptive loop: later CPU/GPU information is allowed to improve an earlier RAM decision.

---

# Phase 11 – Sweet-spot analysis

## 23. Curve analysis

The Wizard does not use a sample-console percentage or fixed MHz threshold.

For each domain it uses the measured curve:

- performance
- electrical cost proxy (actual rail voltage/frequency and reliable power telemetry when available)
- stability
- combined stability

The primary knee detector is normalized and device-relative. A later combined failure can override the first knee result.

Graphs must show the actual measurement points and mark:

- Stable Max
- Sweet Spot
- Recommended

If Recommended changed because of a later combined test, show that explicitly.

---

# Phase 12 – Final profile

## 24. Final dependency validation

Before saving:

- verify every Wizard-controlled HOC setting
- rerun the critical combined validation set
- ensure no unexpected setting changed
- ensure all requested clocks match Real Clock within tolerance

## 25. Save to Performance Modes

Save current:

- `/config/horizon-oc/config.ini`
- `/atmosphere/kips/hoc.kip`

to:

`/switch/.packages/Performance Modes/OCMode/`

The final page reports the device-specific Recommended values and also keeps the technical Stable Max values in results/measurement data.

## 26. Real-world confirmation

The synthetic Wizard validates the tuning methodically, but a final game test is still recommended.

If real-world instability occurs, use the same rule as every internal diagnostic:

**change one setting only -> retest -> if the failure remains, restore that setting before trying another domain.**
