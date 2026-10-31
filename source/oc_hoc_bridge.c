#define NX_SERVICE_ASSUME_NON_DOMAIN
#include <switch.h>
#include <string.h>

#include "hoc_monitor.h"

#define SVC_NAME "hoc:clk"
#define CMD_GET_API 0
#define CMD_GET_VERSION 1
#define CMD_GET_CONTEXT 2
#define CMD_GET_CONFIG 9
#define CMD_SET_CONFIG 10
#define CMD_SAVE_KIP 12

#define MODS 5
#define TEMPS 11
#define POWERS 2
#define LOADS 10
#define VOLTS 7

typedef struct {
    u32 freqs[MODS];
    u32 realFreqs[MODS];
    u32 overrideFreqs[MODS];
    s32 temps[TEMPS];
    s32 power[POWERS];
    u32 partLoad[LOADS];
    u32 voltages[VOLTS];
} Stable;

typedef struct {
    Stable stable;
    u8 reserved[0x500 - sizeof(Stable)];
} RawContext;

typedef struct { u64 values[256]; } RawConfig;

static Result openHoc(Service* s, u32* api) {
    Result rc = smGetService(s, SVC_NAME);
    if (R_FAILED(rc)) return rc;
    u32 v = 0;
    rc = serviceDispatchOut(s, CMD_GET_API, v);
    if (R_FAILED(rc)) { serviceClose(s); return rc; }
    if (api) *api = v;
    return 0;
}

static Result readCfg(Service* s, RawConfig* c) {
    memset(c, 0, sizeof(*c));
    return serviceDispatch(s, CMD_GET_CONFIG,
        .buffer_attrs = { SfBufferAttr_HipcAutoSelect | SfBufferAttr_Out },
        .buffers = {{ c, sizeof(*c) }},
    );
}

/*
 * Supported layouts. HOC 2.5.1 exposes KIP version at index 34.
 * Current 2.6+/main exposes it at 39. We reject any layout that matches neither.
 */
typedef struct {
    int kipVersion;
    int uncapped, hp, memVolt, ramMax, vddq, dvb, socVmax, timing0;
    int cpuLowUv, cpuHighUv, tableConf, cpuLowVmin, cpuHighVmin, cpuMaxVolt, cpuMax, cpuBoost;
    int gpuUv, gpuVmin, gpuVmax, gpuOffset, gpuVolt0, socVolt0;
    int gpuVoltCount;
} Layout;

static const Layout L251 = {
    34, 5,35,36,39,40,41,42,43,
    72,73,74,75,76,77,78,80,
    83,84,85,86,87,138,24
};

static const Layout LCUR = {
    39, 5,40,41,44,45,46,47,48,
    77,78,79,80,81,82,83,85,
    88,89,90,91,92,144,25
};

static const Layout* detectLayout(const RawConfig* c) {
    if ((u32)c->values[L251.kipVersion] == 251U) return &L251;
    /* Newer builds store a three-digit or larger revision here. */
    u64 v = c->values[LCUR.kipVersion];
    if (v >= 250U && v < 10000U) return &LCUR;
    return NULL;
}

Result hocmonGetTelemetry(HocMonClocks* out) {
    if (!out) return 1;
    memset(out, 0, sizeof(*out));
    Service s = {0};
    Result rc = openHoc(&s, NULL);
    if (R_FAILED(rc)) return rc;
    RawContext c;
    memset(&c, 0, sizeof(c));
    rc = serviceDispatch(&s, CMD_GET_CONTEXT,
        .buffer_attrs = { SfBufferAttr_HipcAutoSelect | SfBufferAttr_Out },
        .buffers = {{ &c, sizeof(c) }},
    );
    serviceClose(&s);
    if (R_FAILED(rc)) return rc;
    for (int i = 0; i < 3; ++i) {
        out->targetHz[i] = c.stable.freqs[i];
        out->realHz[i] = c.stable.realFreqs[i];
        out->overrideHz[i] = c.stable.overrideFreqs[i];
    }
    out->socVoltageUv = c.stable.voltages[0];
    out->vdd2VoltageUv = c.stable.voltages[1];
    out->cpuVoltageUv = c.stable.voltages[2];
    out->gpuVoltageUv = c.stable.voltages[3];
    out->vddqVoltageUv = c.stable.voltages[4];
    out->powerNowMw = c.stable.power[0];
    out->powerAvgMw = c.stable.power[1];
    return 0;
}

static Result writeCfg(Service* s, RawConfig* c) {
    Result rc = serviceDispatch(s, CMD_SET_CONFIG,
        .buffer_attrs = { SfBufferAttr_HipcAutoSelect | SfBufferAttr_In },
        .buffers = {{ c, sizeof(*c) }},
    );
    if (R_SUCCEEDED(rc)) {
        const u32 dummy = 0;
        rc = serviceDispatchIn(s, CMD_SAVE_KIP, dummy);
    }
    return rc;
}

Result hocmonApplyOcPreparation(const HocMonOcPreparation* d) {
    if (!d) return 1;
    Service s = {0};
    Result rc = openHoc(&s, NULL);
    if (R_FAILED(rc)) return rc;
    RawConfig c;
    rc = readCfg(&s, &c);
    if (R_FAILED(rc)) { serviceClose(&s); return rc; }
    const Layout* l = detectLayout(&c);
    if (!l) { serviceClose(&s); return 4; }

    c.values[l->uncapped] = d->uncappedClocks ? 1 : 0;
    c.values[l->hp] = d->hpMode ? 1 : 0;
    c.values[l->memVolt] = d->vdd2Uv;
    c.values[l->ramMax] = d->ramMaxKHz;
    c.values[l->vddq] = d->vddqUv;
    c.values[l->dvb] = d->dvbShift;
    c.values[l->socVmax] = d->socVmaxUv;
    for (int i = 0; i < 8; ++i) c.values[l->timing0 + i] = d->timings[i];

    c.values[l->cpuLowUv] = d->lowUv;
    c.values[l->cpuHighUv] = d->highUv;
    c.values[l->tableConf] = d->tableConf;
    c.values[l->cpuLowVmin] = d->lowVminMv;
    c.values[l->cpuHighVmin] = d->highVminMv;
    c.values[l->cpuMaxVolt] = d->cpuMaxVoltMv;
    c.values[l->cpuMax] = d->cpuMaxKHz;
    c.values[l->cpuBoost] = d->cpuBoostKHz;

    rc = writeCfg(&s, &c);
    serviceClose(&s);
    return rc;
}

Result hocmonVerifyOcPreparation(const HocMonOcPreparation* d, u32* mismatchMask) {
    if (!d) return 1;
    if (mismatchMask) *mismatchMask = 0;
    Service s = {0};
    Result rc = openHoc(&s, NULL);
    if (R_FAILED(rc)) return rc;
    RawConfig c;
    rc = readCfg(&s, &c);
    serviceClose(&s);
    if (R_FAILED(rc)) return rc;
    const Layout* l = detectLayout(&c);
    if (!l) return 4;

    u32 m = 0;
    if (!!c.values[l->uncapped] != d->uncappedClocks) m |= 1u << 0;
    if (!!c.values[l->hp] != d->hpMode) m |= 1u << 1;
    if ((u32)c.values[l->memVolt] != d->vdd2Uv) m |= 1u << 2;
    if ((u32)c.values[l->ramMax] != d->ramMaxKHz) m |= 1u << 3;
    if ((u32)c.values[l->vddq] != d->vddqUv) m |= 1u << 4;
    if ((u32)c.values[l->dvb] != d->dvbShift) m |= 1u << 5;
    if ((u32)c.values[l->socVmax] != d->socVmaxUv) m |= 1u << 6;
    for (int i = 0; i < 8; ++i)
        if ((u32)c.values[l->timing0 + i] != d->timings[i]) m |= 1u << 7;
    if (mismatchMask) *mismatchMask = m;
    return 0;
}

Result hocmonReadRawOcConfig(u64* outValues, u32 count, int* is251) {
    if (!outValues || count == 0) return 1;
    Service s = {0};
    Result rc = openHoc(&s, NULL);
    if (R_FAILED(rc)) return rc;
    RawConfig c;
    rc = readCfg(&s, &c);
    serviceClose(&s);
    if (R_FAILED(rc)) return rc;
    const Layout* l = detectLayout(&c);
    if (!l) return 4;
    if (is251) *is251 = (l == &L251) ? 1 : 0;
    if (count > 256) count = 256;
    memcpy(outValues, c.values, count * sizeof(u64));
    return 0;
}

Result hocmonWriteRawOcConfig(u64* values, u32 count) {
    if (!values || count == 0) return 1;
    Service s = {0};
    Result rc = openHoc(&s, NULL);
    if (R_FAILED(rc)) return rc;
    RawConfig c;
    rc = readCfg(&s, &c);
    if (R_FAILED(rc)) { serviceClose(&s); return rc; }
    const Layout* l = detectLayout(&c);
    if (!l) { serviceClose(&s); return 4; }
    if (count > 256) count = 256;
    memcpy(c.values, values, count * sizeof(u64));
    rc = writeCfg(&s, &c);
    serviceClose(&s);
    return rc;
}
