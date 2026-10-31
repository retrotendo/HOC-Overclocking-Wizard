# HOC Undervolting Wizard v0.4.0-beta.26

## Preparation cleanup

- Removed `Known PASS / Skip` from the Preparation page.
- The hidden `+` Preparation skip input is disabled as well.
- On the `SETTING NOT READY` Preparation page, `Use current settings as baseline` now appears with the normal action options at the bottom.
- Removed the `RAW CONFIG DEBUG` option/hotkey from the Preparation check page.

## Reboot recovery hint

Before the Wizard restarts the console, it now shows recovery instructions in case the new setting does not boot.

For CPU Low UV the page explicitly instructs:

1. Start `CFW No OC` from Hekate.
2. Lower CPU Low UV by one step.
3. Restart normal CFW.
4. Open the Wizard again.

For other rebooted tuning values, the Wizard tells the user to restore the previous safe value before restarting normal CFW.
