#include "oc_engine.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace oc {

namespace {

double costProxy(const SweepPoint& p, bool usePower) {
    if (usePower && p.powerReliable && p.batteryPowerW > 0.01)
        return p.batteryPowerW;
    if (p.railMv == 0) return std::max(1.0, p.realMHz);
    const double v = double(p.railMv) / 1000.0;
    // Dynamic power proxy. RAM is less frequency-linear than CPU/GPU, but this
    // still gives a useful monotonic electrical-cost axis without pretending
    // to be a wall-power measurement.
    const double f = std::max(1.0, p.realMHz > 0.0 ? p.realMHz : double(p.requestedMHz));
    return v * v * f;
}

bool hasReliablePower(const std::vector<SweepPoint>& pts, const std::vector<int>& idx) {
    if (idx.size() < 3) return false;
    int good = 0;
    for (int i : idx) {
        const auto& p = pts[i];
        if (p.powerReliable && p.batteryPowerW > 0.01) ++good;
    }
    return good >= int(idx.size()) - 1;
}
}

SweepAnalysis analyzeSweep(const std::vector<SweepPoint>& points) {
    SweepAnalysis out;
    std::vector<int> stable;
    for (int i = 0; i < int(points.size()); ++i) {
        if (points[i].stable && points[i].combinedStable && points[i].performance > 0.0)
            stable.push_back(i);
    }
    if (stable.empty()) {
        out.reason = "No validated stable measurement points.";
        return out;
    }

    out.stableMax = stable.back();
    if (stable.size() == 1) {
        out.sweetSpot = out.recommended = stable.front();
        out.reason = "Only one stable measured point is available.";
        return out;
    }

    const bool usePower = hasReliablePower(points, stable);
    out.usedPower = usePower;

    double minPerf = std::numeric_limits<double>::infinity();
    double maxPerf = 0.0;
    double minCost = std::numeric_limits<double>::infinity();
    double maxCost = 0.0;
    for (int i : stable) {
        minPerf = std::min(minPerf, points[i].performance);
        maxPerf = std::max(maxPerf, points[i].performance);
        const double c = costProxy(points[i], usePower);
        minCost = std::min(minCost, c);
        maxCost = std::max(maxCost, c);
    }

    const double perfSpan = std::max(1e-9, maxPerf - minPerf);
    const double costSpan = std::max(1e-9, maxCost - minCost);

    // Kneedle-style elbow: maximize normalized performance progress minus
    // normalized electrical cost. This adapts to each console and does not
    // encode a fixed MHz/mV threshold from the developer's sample device.
    int best = stable.front();
    double bestScore = -1e9;
    for (int i : stable) {
        const double py = (points[i].performance - minPerf) / perfSpan;
        const double cx = (costProxy(points[i], usePower) - minCost) / costSpan;
        double score = py - cx;

        // Prefer points that retain most of the available performance. This
        // prevents a very low early point from winning only because it is cheap.
        const double retain = points[i].performance / std::max(1e-9, maxPerf);
        if (retain < 0.85) score -= (0.85 - retain) * 2.0;

        // Mild preference for an interior point when scores are nearly equal.
        if (i == stable.back()) score -= 0.015;
        if (score > bestScore) {
            bestScore = score;
            best = i;
        }
    }

    out.kneeScore = bestScore;
    out.sweetSpot = best;
    out.recommended = best;

    // If the knee is effectively the maximum and the previous point loses very
    // little performance, prefer the previous point as the daily recommendation.
    if (best == stable.back() && stable.size() >= 2) {
        const int prev = stable[stable.size() - 2];
        const double loss = 100.0 * (points[best].performance - points[prev].performance) /
                            std::max(1e-9, points[best].performance);
        const double cBest = costProxy(points[best], usePower);
        const double cPrev = costProxy(points[prev], usePower);
        const double saving = 100.0 * (cBest - cPrev) / std::max(1e-9, cBest);
        if (loss <= 2.5 && saving >= 4.0)
            out.recommended = prev;
    }

    out.reason = usePower
        ? "Recommended point is the measured performance/power knee."
        : "Recommended point is the measured performance/electrical-cost knee.";
    return out;
}

int reconsiderAfterCombination(const std::vector<SweepPoint>& points,
                               int currentRecommendation,
                               int failingIndex,
                               double maxPerformanceLossPct) {
    if (points.empty() || currentRecommendation < 0 || failingIndex < 0)
        return currentRecommendation;
    if (currentRecommendation >= int(points.size()) || failingIndex >= int(points.size()))
        return currentRecommendation;

    const double refPerf = std::max(1e-9, points[currentRecommendation].performance);
    int best = currentRecommendation;
    double bestCost = costProxy(points[currentRecommendation], points[currentRecommendation].powerReliable);

    // Search only lower/easier validated points. A later combined failure is
    // resolved by backing off one domain, never by changing several at once.
    for (int i = std::min(currentRecommendation - 1, failingIndex - 1); i >= 0; --i) {
        const auto& p = points[i];
        if (!p.stable || !p.combinedStable || p.performance <= 0.0) continue;
        const double loss = 100.0 * (refPerf - p.performance) / refPerf;
        if (loss > maxPerformanceLossPct) continue;
        const double c = costProxy(p, p.powerReliable);
        if (c < bestCost) {
            bestCost = c;
            best = i;
        }
    }
    return best;
}

double ramPerformanceScore(double cpuCopy, double cpuRead, double cpuWrite,
                           double gpuCopy, double gpuRead, double gpuWrite,
                           double ramLatencyNs) {
    const double bw = std::max(0.0,
        cpuCopy * 0.18 + cpuRead * 0.22 + cpuWrite * 0.10 +
        gpuCopy * 0.14 + gpuRead * 0.26 + gpuWrite * 0.10);
    if (ramLatencyNs <= 0.0) return bw;
    // Keep units intuitive: bandwidth dominates, latency provides a meaningful
    // tie-breaker. 75 ns contributes ~1333 score units.
    const double latencyBonus = 100000.0 / ramLatencyNs;
    return bw + latencyBonus;
}

const char* domainName(Domain d) {
    switch (d) {
        case Domain::Ram: return "RAM";
        case Domain::Gpu: return "GPU";
        case Domain::Cpu: return "CPU";
        default: return "OC";
    }
}

} // namespace oc
