# HOC Undervolting Wizard v0.4.0-beta.6

This beta adds a hard **Full Memory Mode** requirement before the Wizard is allowed to open.

## Applet Mode is blocked at startup

The Wizard now checks `appletGetAppletType()` immediately after initializing input. Only `AppletType_Application` and `AppletType_SystemApplication` are accepted, matching nx-hbmenu's own distinction for Applet Mode.

If the NRO is launched through Album/Applet Mode:

- the Wizard does **not** load or modify its tuning state;
- the guide is not shown;
- no CPU, RAM, Combined or GPU stability test can be started;
- a dedicated warning screen explains how to relaunch hbmenu in Full Memory Mode.

Correct launch:

1. Return to HOME.
2. Highlight an installed game.
3. Hold **R** while starting the game.
4. Keep holding **R** until hbmenu opens.
5. Launch HOC Undervolting Wizard.

## Retained from beta.5

- dynamic measurement-only Low VMIN floor probing
- 3 HOC voltage samples spaced 1.1 seconds apart
- requested CPU clock must actually be applied before a VMIN sample is accepted
- automatic CPU/GPU/RAM Temporary Override checks
- known PASS / FAIL shortcuts for previously validated values
- 570 mV Low VMIN lower bound
- 10 mV VDDQ search interval
- combined RAM-rail validation

This remains a **pre-release** until validated on real Mariko / Switch OLED hardware.
