#include "oc_config.hpp"
#include "hoc_monitor.h"

#include <algorithm>
#include <array>
#include <cstring>

namespace occonfig {
namespace {

struct Idx {
    int kipVersion;
    int uncapped, hp, memVolt, ramMax, vddq, dvb, socVmax, timing0;
    int cpuLowUv, cpuHighUv, tableConf, cpuLowVmin, cpuHighVmin, cpuMaxVolt, cpuMax;
    int gpuUv, gpuVmin, gpuVmax, gpuOffset, gpuVolt0, socVolt0;
    int gpuVoltCount;
};

constexpr Idx I251 = {34,5,35,36,39,40,41,42,43,72,73,74,75,76,77,78,83,84,85,86,87,138,24};
constexpr Idx ICUR = {39,5,40,41,44,45,46,47,48,77,78,79,80,81,82,83,88,89,90,91,92,144,25};

const std::uint32_t GPU_FREQS[] = {
    76,153,230,307,384,460,537,614,691,768,844,921,998,1075,1152,1228,
    1267,1305,1344,1382,1420,1459,1497,1536,1574
};

const std::uint32_t SOC_FREQS[] = {
    1866,2000,2133,2200,2266,2333,2400,2433,2466,2533,2566,2600,2666,2700,
    2733,2766,2800,2833,2900,2933,3000,3033,3100,3133,3166,3200,3266,3333
};

bool read(std::array<u64,256>& v, bool& is251, const Idx*& idx, std::string& error) {
    int old = 0;
    Result rc = hocmonReadRawOcConfig(v.data(), v.size(), &old);
    if (R_FAILED(rc)) {
        char b[64];
        std::snprintf(b, sizeof(b), "HOC config read failed: 0x%08X", rc);
        error = b;
        return false;
    }
    is251 = old != 0;
    idx = is251 ? &I251 : &ICUR;
    return true;
}

bool write(std::array<u64,256>& v, std::string& error) {
    Result rc = hocmonWriteRawOcConfig(v.data(), v.size());
    if (R_FAILED(rc)) {
        char b[64];
        std::snprintf(b, sizeof(b), "HOC config write failed: 0x%08X", rc);
        error = b;
        return false;
    }
    return true;
}

int findFreq(const std::uint32_t* list, int n, std::uint32_t mhz) {
    int best = -1;
    std::uint32_t bestDelta = 100000;
    for (int i = 0; i < n; ++i) {
        const std::uint32_t d = list[i] > mhz ? list[i]-mhz : mhz-list[i];
        if (d < bestDelta) { best = i; bestDelta = d; }
    }
    return bestDelta <= 2 ? best : -1;
}

bool mutateOne(int index, u64 value, std::string& error) {
    std::array<u64,256> v{};
    bool old = false; const Idx* idx = nullptr;
    if (!read(v, old, idx, error)) return false;
    (void)old; (void)idx;
    if (index < 0 || index >= int(v.size())) { error = "Unsupported HOC config index."; return false; }
    v[index] = value;
    return write(v, error);
}

} // namespace

LayoutInfo detect() {
    std::array<u64,256> v{};
    bool old = false; const Idx* idx = nullptr; std::string error;
    LayoutInfo out;
    if (!read(v, old, idx, error)) return out;
    out.ok = true;
    out.hoc251 = old;
    out.kipVersion = int(v[idx->kipVersion]);
    return out;
}

bool setRamPreparation(bool hpMode, std::uint32_t ramMaxMHz,
                       std::uint32_t vdd2Mv, std::uint32_t vddqMv,
                       int dvbShift, int socVmaxMv,
                       const std::uint32_t timings[8], std::string& error) {
    std::array<u64,256> v{};
    bool old = false; const Idx* i = nullptr;
    if (!read(v, old, i, error)) return false;
    v[i->uncapped] = 1;
    v[i->hp] = hpMode ? 1 : 0;
    v[i->memVolt] = u64(vdd2Mv) * 1000ULL;
    v[i->ramMax] = u64(ramMaxMHz) * 1000ULL;
    v[i->vddq] = u64(vddqMv) * 1000ULL;
    v[i->dvb] = std::max(0, std::min(6, dvbShift));
    v[i->socVmax] = std::max(0, std::min(1200, socVmaxMv));
    for (int n = 0; n < 8; ++n) v[i->timing0+n] = timings[n];
    return write(v, error);
}

bool setRamTimings(const std::uint32_t timings[8], std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    for (int n=0;n<8;++n) v[i->timing0+n]=timings[n];
    return write(v,error);
}

bool setRamMax(std::uint32_t mhz, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->ramMax]=u64(mhz)*1000ULL; return write(v,error);
}

bool setVdd2(std::uint32_t mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->memVolt]=u64(mv)*1000ULL; return write(v,error);
}

bool setVddq(std::uint32_t mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->vddq]=u64(mv)*1000ULL; return write(v,error);
}

bool setDvbShift(int shift, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->dvb]=std::max(0,std::min(6,shift)); return write(v,error);
}

bool setSocVmax(int mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->socVmax]=std::max(0,std::min(1200,mv)); return write(v,error);
}

bool setSocPoint(std::uint32_t mhz, int mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    int p=findFreq(SOC_FREQS,int(sizeof(SOC_FREQS)/sizeof(SOC_FREQS[0])),mhz);
    if(p<0){error="Unsupported RAM/SoC frequency.";return false;}
    v[i->socVolt0+p]=std::max(0,std::min(1200,mv)); return write(v,error);
}

bool getSocPoint(std::uint32_t mhz, int& mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    int p=findFreq(SOC_FREQS,int(sizeof(SOC_FREQS)/sizeof(SOC_FREQS[0])),mhz);
    if(p<0){error="Unsupported RAM/SoC frequency.";return false;}
    mv=int(v[i->socVolt0+p]); return true;
}

bool setGpuPoint(std::uint32_t mhz, int mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    int p=findFreq(GPU_FREQS,i->gpuVoltCount,mhz);
    if(p<0){error="Unsupported GPU frequency.";return false;}
    v[i->gpuVolt0+p]=std::max(0,std::min(1200,mv)); return write(v,error);
}

bool getGpuPoint(std::uint32_t mhz, int& mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    int p=findFreq(GPU_FREQS,i->gpuVoltCount,mhz);
    if(p<0){error="Unsupported GPU frequency.";return false;}
    mv=int(v[i->gpuVolt0+p]); return true;
}

bool setGpuVmin(int mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->gpuVmin]=std::max(0,std::min(1200,mv)); return write(v,error);
}

bool setGpuVmax(int mv, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->gpuVmax]=std::max(0,std::min(1200,mv)); return write(v,error);
}

bool setGpuUvTable(int table, std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false; v[i->gpuUv]=std::max(0,std::min(2,table)); return write(v,error);
}

bool setCpuTuning(int lowUv, int highUv, int tableConf,
                  int lowVminMv, int highVminMv,
                  int maxVoltMv, std::uint32_t maxClockMHz,
                  std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    v[i->cpuLowUv]=std::max(0,std::min(13,lowUv));
    v[i->cpuHighUv]=std::max(0,std::min(13,highUv));
    v[i->tableConf]=std::max(1,std::min(3,tableConf));
    v[i->cpuLowVmin]=std::max(570,std::min(1000,lowVminMv));
    v[i->cpuHighVmin]=std::max(570,std::min(1200,highVminMv));
    v[i->cpuMaxVolt]=std::max(800,std::min(1300,maxVoltMv));
    v[i->cpuMax]=u64(maxClockMHz)*1000ULL;
    return write(v,error);
}

bool getCpuTuning(int& lowUv, int& highUv, int& tableConf,
                  int& lowVminMv, int& highVminMv,
                  int& maxVoltMv, std::uint32_t& maxClockMHz,
                  std::string& error) {
    std::array<u64,256> v{}; bool old=false; const Idx* i=nullptr;
    if (!read(v,old,i,error)) return false;
    lowUv=int(v[i->cpuLowUv]); highUv=int(v[i->cpuHighUv]); tableConf=int(v[i->tableConf]);
    lowVminMv=int(v[i->cpuLowVmin]); highVminMv=int(v[i->cpuHighVmin]); maxVoltMv=int(v[i->cpuMaxVolt]);
    maxClockMHz=std::uint32_t(v[i->cpuMax]/1000ULL); return true;
}

} // namespace occonfig
