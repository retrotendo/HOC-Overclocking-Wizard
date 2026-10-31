#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace oc {

enum class Domain : std::uint8_t { Ram = 0, Gpu = 1, Cpu = 2 };

struct SweepPoint {
    Domain domain = Domain::Ram;
    std::uint32_t requestedMHz = 0;
    double realMHz = 0.0;
    std::uint32_t railMv = 0;
    std::uint32_t auxMv = 0;        // RAM: VDDQ, CPU/GPU: optional second rail/context
    double performance = 0.0;       // RAM composite score, CPU/GPU FPS or throughput
    double latencyNs = 0.0;         // RAM only
    double bandwidthMBs = 0.0;      // RAM only
    double batteryPowerW = 0.0;     // battery-side only; may be unusable while charging
    double batteryCurrentMa = 0.0;  // signed MAX17050 current
    bool powerReliable = false;
    bool stable = false;
    bool combinedStable = true;
    std::string context;
};

struct SweepAnalysis {
    int stableMax = -1;
    int sweetSpot = -1;
    int recommended = -1;
    bool usedPower = false;
    double kneeScore = 0.0;
    std::string reason;
};

// Device-specific knee detection. No fixed MHz or voltage target is encoded.
// Cost uses measured battery-side power only when the samples are comparable;
// otherwise it falls back to an electrical voltage/frequency proxy.
SweepAnalysis analyzeSweep(const std::vector<SweepPoint>& points);

// Re-open an earlier decision after a later combined test. Returns the index of
// the lower-cost point to recommend, or the existing recommendation if no
// meaningful improvement is demonstrated.
int reconsiderAfterCombination(const std::vector<SweepPoint>& points,
                               int currentRecommendation,
                               int failingIndex,
                               double maxPerformanceLossPct = 3.0);

// RAM benchmark composite: rewards bandwidth and lower full-RAM latency.
double ramPerformanceScore(double cpuCopy, double cpuRead, double cpuWrite,
                           double gpuCopy, double gpuRead, double gpuWrite,
                           double ramLatencyNs);

const char* domainName(Domain d);

} // namespace oc
