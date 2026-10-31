/*
 * HOC Overclocking Wizard - Horizon OC monitor.
 *
 * Uses the public Horizon-OC hoc:clk IPC service. Stable context fields are
 * used for clocks/voltages/power; API-v2 context/config fields are used for
 * DRAM identification and persistent-setting verification.
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
    /* Stable voltage order: SOC, VDD2, CPU, GPU, VDDQ, display, battery. */
    u32 socVoltageUv;
    u32 vdd2VoltageUv;
    u32 cpuVoltageUv;
    u32 gpuVoltageUv;
    u32 vddqVoltageUv;
    /* HOC battery-side MAX17050 power sensors, in mW. */
    s32 powerNowMw;
    s32 powerAvgMw;
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

/* Persistent OC preparation fields used before the RAM search. */
typedef struct {
    bool uncappedClocks;
    bool hpMode;
    u32 ramMaxKHz;
    u32 vdd2Uv;
    u32 vddqUv;
    u32 dvbShift;
    u32 socVmaxUv;
    u32 timings[8];
    int lowUv;
    int highUv;
    int tableConf;
    int lowVminMv;
    int highVminMv;
    u32 cpuMaxVoltMv;
    u32 cpuMaxKHz;
    u32 cpuBoostKHz;
} HocMonOcPreparation;

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

Result hocmonGetClocks(HocMonClocks* out);
Result hocmonSetOverride(u32 module, u32 hz);
Result hocmonGetHardware(HocMonHardware* out);
Result hocmonGetHardwareDebug(HocMonHardwareDebug* out);
Result hocmonGetConfig(HocMonConfig* out);
Result hocmonApplyPreparation251(const HocMonConfig* desired);
Result hocmonApplyCpuLow251(int lowUv, int lowVminMv, u32 fieldsMask);
Result hocmonGetConfig251(HocMonConfig* out);
Result hocmonGetConfigDebug(HocMonConfigDebug* out);

/*
 * Apply the OC-Wizard preparation through HOC's own config IPC + Save KIP.
 * Supports the 2.5.1 layout and the current 2.6+/main layout. Unknown layouts
 * are rejected instead of writing guessed indexes.
 */
Result hocmonApplyOcPreparation(const HocMonOcPreparation* desired);

/* Verify the OC preparation fields against the current persistent config. */
Result hocmonVerifyOcPreparation(const HocMonOcPreparation* desired, u32* mismatchMask);

#ifdef __cplusplus
}
#endif
