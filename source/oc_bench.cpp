#include "oc_bench.hpp"
#include "oc_engine.hpp"
#include "hoc_monitor.h"

extern "C" {
#include "benchmark/bench.h"
#include "benchmark/furmark/run_furmark.h"
}

#include <switch.h>
#include <algorithm>
#include <cmath>

namespace ocbench {
namespace {

void sample(Telemetry& t) {
    HocMonClocks c{};
    if (R_FAILED(hocmonGetTelemetry(&c))) return;
    t.realCpuMHz = c.realHz[0] / 1.0e6;
    t.realGpuMHz = c.realHz[1] / 1.0e6;
    t.realRamMHz = c.realHz[2] / 1.0e6;
    t.socMv = c.socVoltageUv / 1000.0;
    t.vdd2Mv = c.vdd2VoltageUv / 1000.0;
    t.cpuMv = c.cpuVoltageUv / 1000.0;
    t.gpuMv = c.gpuVoltageUv / 1000.0;
    t.vddqMv = c.vddqVoltageUv / 1000.0;
    if (c.powerAvgMw != 0) {
        const double p = std::abs(c.powerAvgMw) / 1000.0;
        if (t.powerSamples == 0) t.batteryPowerW = p;
        else t.batteryPowerW = (t.batteryPowerW * t.powerSamples + p) / double(t.powerSamples + 1);
        ++t.powerSamples;
    }
}

bool runFpsScene(int which, int seconds, double& fps, Telemetry& telemetry) {
    seconds = std::max(5, seconds);
    run_furmark_start(which);
    svcSleepThread(1'500'000'000LL);
    if (!run_furmark_running()) return false;

    double sum = 0.0;
    int samples = 0;
    const int loops = seconds * 2;
    for (int i = 0; i < loops && run_furmark_running(); ++i) {
        const float f = run_furmark_fps();
        sample(telemetry);
        if (i >= 2 && f > 0.0f && std::isfinite(f)) {
            sum += f;
            ++samples;
        }
        svcSleepThread(500'000'000LL);
    }
    run_furmark_stop();
    sample(telemetry);
    fps = samples ? sum / samples : 0.0;
    return samples > 0 && fps > 0.0;
}

}

RamResult runRam() {
    RamResult r;
    bench_ctx* ctx = bench_begin();
    if (!ctx) {
        r.error = "Memory benchmark could not initialize.";
        return r;
    }
    bench_results_t out{};
    const char* label = nullptr;
    float frac = 0.0f;
    while (bench_step(ctx, &out, &label, &frac)) {
        sample(r.telemetry);
        svcSleepThread(2'000'000);
    }
    bench_end(ctx);
    sample(r.telemetry);

    r.cpuCopy = out.cpu_copy;
    r.cpuRead = out.cpu_read;
    r.cpuWrite = out.cpu_write;
    r.gpuCopy = out.gpu_copy;
    r.gpuRead = out.gpu_read;
    r.gpuWrite = out.gpu_write;
    r.l2Ns = out.l2_ns;
    r.ramNs = out.ram_ns;
    r.score = oc::ramPerformanceScore(r.cpuCopy, r.cpuRead, r.cpuWrite,
                                      r.gpuCopy, r.gpuRead, r.gpuWrite, r.ramNs);
    r.ok = std::isfinite(r.score) && r.score > 0.0 && r.ramNs > 0.0;
    if (!r.ok) r.error = "Memory benchmark returned incomplete data.";
    return r;
}

GpuResult runGpu(int seconds) {
    GpuResult r;
    // Benchmark Toolbox Furmark scene. Stability/mismatch detection is handled
    // separately by the Wizard's deko3d verifier before this FPS measurement.
    r.ok = runFpsScene(0, seconds, r.fps, r.telemetry);
    if (!r.ok) r.error = "GPU benchmark returned no FPS.";
    return r;
}

CpuResult runCpu(int seconds) {
    CpuResult r;
    // Benchmark Toolbox CPU Ray Trace scene.
    r.ok = runFpsScene(4, seconds, r.fps, r.telemetry);
    if (!r.ok) r.error = "CPU Ray Trace benchmark returned no FPS.";
    return r;
}

} // namespace ocbench
