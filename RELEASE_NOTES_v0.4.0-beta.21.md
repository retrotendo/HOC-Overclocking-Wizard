# HOC Undervolting Wizard v0.4.0-beta.21

## Fix: correct Horizon OC 2.6.0 RAM hardware layout

The beta.19 hardware debug dump revealed the exact Horizon OC 2.6.0 field positions on real hardware:

- `dramID` at byte **400**
- `isDram8GB` at byte **401**
- `consoleType` at bytes **404-407**

On the tested OLED, the dump was `dramID=5`, `isDram8GB=0`, `consoleType=3`, which maps to **NEE 4GB / Aula (OLED)**.

Beta.20 still used the wrong candidate positions. Beta.21 fixes the hardware detector by validating the complete known layout tuple for both Horizon OC 2.6.0 and current HOC main.

No tuning, stress-test, automatic VMIN scan, reboot flow, or Temporary Override behavior changed.
