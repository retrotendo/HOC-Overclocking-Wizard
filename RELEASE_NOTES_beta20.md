# HOC Undervolting Wizard v0.4.0-beta.20

Fixes RAM hardware detection with Horizon OC 2.6.x context layouts.

- keeps dual-layout DRAM-ID detection
- stops treating the non-stable `consoleType` field as a hard requirement
- an unambiguous known DRAM ID plus valid 8 GB flag is now sufficient
- no tuning/test logic changes
