/*
 * HOC Overclocking Wizard - Horizon OC monitor.
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
    u32 socVoltageUv;
    u32 vdd2VoltageUv;
    u32 cpuVoltageUv;
    u32 gpuVoltageUv;
    u32 vddqVoltageUv;
    s32 powerNowMw;
    s32 powerAvgMw;
} HocMonClocks;

typedef struct { u8 dramId; bool isDram8GB; u32 consoleType; } HocMonHardware;

typedef struct {
    u32 apiVersion;
    u8 raw400_411[12];
    s32 consoleTypeAt408;
    u8 idAt403, is8At404, idAt404, is8At405;
    bool id403Known, id404Known;
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
typedef struct { u32 apiVersion; char version[64]; u64 values[HOCMON_CONFIG_DEBUG_VALUE_COUNT]; } HocMonConfigDebug;

enum { HocMonModule_CPU = 0, HocMonModule_GPU = 1, HocMonModule_MEM = 2 };

Result hocmonGetClocks(HocMonClocks* out);
Result hocmonGetTelemetry(HocMonClocks* out);
Result hocmonSetOverride(u32 module, u32 hz);
Result hocmonGetHardware(HocMonHardware* out);
Result hocmonGetHardwareDebug(HocMonHardwareDebug* out);
Result hocmonGetConfig(HocMonConfig* out);
Result hocmonApplyPreparation251(const HocMonConfig* desired);
Result hocmonApplyCpuLow251(int lowUv, int lowVminMv, u32 fieldsMask);
Result hocmonGetConfig251(HocMonConfig* out);
Result hocmonGetConfigDebug(HocMonConfigDebug* out);
Result hocmonApplyOcPreparation(const HocMonOcPreparation* desired);
Result hocmonVerifyOcPreparation(const HocMonOcPreparation* desired, u32* mismatchMask);
Result hocmonReadRawOcConfig(u64* outValues, u32 count, int* is251);
Result hocmonWriteRawOcConfig(u64* values, u32 count);

#ifdef __cplusplus
}
#endif
