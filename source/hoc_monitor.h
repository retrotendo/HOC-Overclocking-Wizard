/*
 * HOC Undervolting Wizard - Horizon OC monitor.
 *
 * Uses the public Horizon-OC hoc:clk IPC service. The stable context fields are
 * used for clocks/voltages; current API-v2 context/config fields are used for
 * DRAM identification and persistent-setting verification. Temporary CPU/GPU/
 * MEM overrides can also be written through HOC's public SetOverride IPC.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#pragma once

#include <switch.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    u32 targetHz[3];
    u32 realHz[3];
    u32 overrideHz[3];
    /* Current CPU rail voltage reported by Horizon OC, in microvolts. */
    u32 cpuVoltageUv;
} HocMonClocks;

typedef struct {
    u8 dramId;
    bool isDram8GB;
    u32 consoleType;
} HocMonHardware;

typedef struct {
    u32 apiVersion;
    u8 raw400_411[12];
    s32 consoleTypeAt408;
    u8 idAt403;
    u8 is8At404;
    u8 idAt404;
    u8 is8At405;
    bool id403Known;
    bool id404Known;
} HocMonHardwareDebug;

typedef struct {
    bool uncappedClocks;
    bool hpMode;
    u32 ramMaxKHz;
    u32 vdd2Uv;
    u32 vddqUv;
    int lowUv;
    int highUv;
    int tableConf;
    int lowVminMv;
    int highVminMv;
    u32 cpuMaxKHz;
    u32 cpuBoostKHz;
} HocMonConfig;

#define HOCMON_CONFIG_DEBUG_VALUE_COUNT 256
typedef struct {
    u32 apiVersion;
    char version[64];
    u64 values[HOCMON_CONFIG_DEBUG_VALUE_COUNT];
} HocMonConfigDebug;

enum {
    HocMonModule_CPU = 0,
    HocMonModule_GPU = 1,
    HocMonModule_MEM = 2,
};

/* Read CPU/GPU/MEM target, real and temporary override clocks + CPU voltage. */
Result hocmonGetClocks(HocMonClocks* out);

/* Set one Horizon OC Temporary Override. hz=0 clears that module override. */
Result hocmonSetOverride(u32 module, u32 hz);

/* Read DRAM identity from Horizon OC API-v2 current context. */
Result hocmonGetHardware(HocMonHardware* out);

/* Raw context diagnostics for hardware-layout troubleshooting. */
Result hocmonGetHardwareDebug(HocMonHardwareDebug* out);

/* Read the persistent Horizon OC/KIP values used by the Battery Wizard. */
Result hocmonGetConfig(HocMonConfig* out);

/*
 * Horizon OC 2.5.1 only: apply the Wizard Preparation values through HOC's
 * own SetConfigValues IPC and persist them with SetKipData (Save KIP).
 * Returns a non-zero Result when the running HOC layout/version is unsupported.
 */
Result hocmonApplyPreparation251(const HocMonConfig* desired);

/*
 * Horizon OC 2.5.1 only: update CPU Low UV and/or Low VMIN through the
 * same SetConfigValues + SetKipData path used by Horizon OC itself.
 * fieldsMask bit0 = Low UV, bit1 = Low VMIN.
 */
Result hocmonApplyCpuLow251(int lowUv, int lowVminMv, u32 fieldsMask);

/* Read the running Horizon OC 2.5.1 config through hoc:clk/GetConfigValues. */
Result hocmonGetConfig251(HocMonConfig* out);

/* Raw hoc:clk config-list diagnostics. Read-only; used by debug builds. */
Result hocmonGetConfigDebug(HocMonConfigDebug* out);

#ifdef __cplusplus
}
#endif
