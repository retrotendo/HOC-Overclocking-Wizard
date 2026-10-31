# HOC Undervolting Wizard v0.4.0-beta.39

## Voltage scan reliability
- CPU voltage-region scans now discard 2 settling reads before measurement.
- Each frequency uses 9 valid voltage samples and the median value.
- Noisy measurements are retried automatically before a region is accepted.
- Voltage regions are still grouped in 5 mV steps.

## Validation flow aligned with OC Part 1
- Keeps short screening tests while searching for limits.
- VDDQ/VDD2 still use quick search followed by a 1-hour validation of the final candidate.
- Adds one critical 1-hour CPU-memtester validation at the normal handheld state: 1020 / 384 / 1331.
- High UV continues with 1-minute screening while searching.
- The final High UV candidate is validated once with a 1-hour CPU-memtester at Nintendo Boost state: 1785 / 76.8 / 1600.
- Removes redundant standalone final CPU/RAM/GPU/Boost one-hour tests.
- Final real-world validation remains: game launch/loading, Home, Sleep/Wake, CPU Boost transitions and 1 hour of active Tears of the Kingdom gameplay.

This keeps the same principle used during the original OC Part 1 tuning: find the edge quickly, then spend long test time only on the critical final combinations.
