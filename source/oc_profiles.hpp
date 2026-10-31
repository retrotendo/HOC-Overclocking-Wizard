#pragma once

#include <cstdint>
#include <cstddef>

namespace oc {

struct RamTimings {
    std::uint32_t t[8];
};

struct RamProfile {
    const char* name;
    const char* tier;
    std::uint32_t minMHz;
    std::uint32_t maxMHz;
    std::uint32_t vdd2Mv;
    std::uint32_t vddqMv;
    RamTimings common;
    RamTimings st;
    const std::uint8_t* ids;
    std::size_t idCount;
};

static constexpr std::uint8_t IDS_WTB[]   = {32,33,34};
static constexpr std::uint8_t IDS_NEE[]   = {3,5,6,29,30,31};
static constexpr std::uint8_t IDS_MGCL[]  = {17,19,24};
static constexpr std::uint8_t IDS_WTE[]   = {11,15};
static constexpr std::uint8_t IDS_MGCJ[]  = {8,12};
static constexpr std::uint8_t IDS_WTF[]   = {25,26,27};
static constexpr std::uint8_t IDS_ABMGCL[]= {20,21,22};
static constexpr std::uint8_t IDS_NME[]   = {10,14};

// Current Horizon-OC Mariko guide values. These are starting ranges and safe
// preparation values only; the Wizard still measures each console individually.
static constexpr RamProfile RAM_PROFILES[] = {
    {"WT:B", "GOD", 3066, 3200, 1175, 600,
        {{4,4,5,4,2,6,5,6}}, {{6,6,7,5,2,6,5,6}}, IDS_WTB, sizeof(IDS_WTB)},
    {"NEI / NEE / x267", "GOD", 3100, 3300, 1175, 640,
        {{3,3,2,1,5,5,4,6}}, {{4,4,4,2,7,6,5,6}}, IDS_NEE, sizeof(IDS_NEE)},
    {"AA-MGCL / MGCR", "S", 2766, 3100, 1175, 640,
        {{4,4,5,4,5,5,6,6}}, {{4,4,8,5,5,6,7,6}}, IDS_MGCL, sizeof(IDS_MGCL)},
    {"WT:E", "A", 2500, 3033, 1175, 600,
        {{2,2,2,1,4,4,4,6}}, {{3,5,3,2,5,4,5,6}}, IDS_WTE, sizeof(IDS_WTE)},
    {"AM-MGCJ", "B", 2633, 2933, 1175, 640,
        {{3,2,4,1,4,4,4,6}}, {{4,3,8,1,5,4,4,6}}, IDS_MGCJ, sizeof(IDS_MGCJ)},
    {"WT:F", "C", 2633, 2800, 1175, 600,
        {{4,4,2,4,4,6,3,6}}, {{5,5,4,4,5,6,5,6}}, IDS_WTF, sizeof(IDS_WTF)},
    {"AB-MGCL", "D", 2500, 2766, 1175, 640,
        {{4,4,4,3,4,5,6,6}}, {{4,4,8,4,5,6,8,6}}, IDS_ABMGCL, sizeof(IDS_ABMGCL)},
    {"NME", "E", 2300, 2766, 1175, 640,
        {{2,2,3,0,1,2,2,6}}, {{5,3,4,1,8,3,3,6}}, IDS_NME, sizeof(IDS_NME)},
};

inline const RamProfile* findRamProfile(std::uint8_t id, bool is8GB) {
    // HOC itself warns that the common 8 GB upgrade IDs are not sufficient to
    // infer the actual memory IC. Never auto-apply a timing preset in that case.
    if (is8GB) return nullptr;
    for (const auto& p : RAM_PROFILES) {
        for (std::size_t i = 0; i < p.idCount; ++i)
            if (p.ids[i] == id) return &p;
    }
    return nullptr;
}

static constexpr std::uint32_t RAM_STEPS_MHZ[] = {
    2133, 2200, 2266, 2300, 2333, 2400, 2433, 2466, 2500, 2533,
    2566, 2600, 2633, 2666, 2700, 2733, 2766, 2800, 2833, 2866,
    2900, 2933, 2966, 3000, 3033, 3066, 3100, 3133, 3166, 3200,
    3233, 3266, 3300, 3333, 3366, 3400
};

inline int firstRamSearchIndex(const RamProfile* p) {
    const std::uint32_t target = p ? (p->minMHz > 150 ? p->minMHz - 150 : p->minMHz) : 2400;
    int best = 0;
    for (int i = 0; i < int(sizeof(RAM_STEPS_MHZ)/sizeof(RAM_STEPS_MHZ[0])); ++i) {
        if (RAM_STEPS_MHZ[i] <= target) best = i;
        else break;
    }
    return best;
}

inline int maxRamSearchIndex(const RamProfile* p) {
    const std::uint32_t target = p ? p->maxMHz : 2933;
    int best = 0;
    for (int i = 0; i < int(sizeof(RAM_STEPS_MHZ)/sizeof(RAM_STEPS_MHZ[0])); ++i) {
        if (RAM_STEPS_MHZ[i] <= target) best = i;
        else break;
    }
    return best;
}

} // namespace oc
