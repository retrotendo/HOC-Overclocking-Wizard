#include "oc_bench.hpp"
#include "oc_engine.hpp"
#include "hoc_monitor.h"

extern "C" {
#include "benchmark/bench.h"
#include "benchmark/gpu_bench.h"
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
    if (c.powerAvgMw > 0) {
        const double p = c.powerAvgMw / 1000.0;
        if (t.powerSamples == 0) t.batteryPowerW = p;
        else t.batteryPowerW = (t.batteryPowerW * t.powerSamples + p) / double(t.powerSamples + 1);
        ++t.powerSamples;
    }
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

GpuResult runGpu(int windows) {
    GpuResult r;
    windows = std::max(3, windows);
    double sum = 0.0;
    int samples = 0;
    for (int i = 0; i < windows; ++i) {
        double gflops = 0.0;
        std::uint64_t dispatches = 0, mismatches = 0;
        if (!gpu_stress_run(&gflops, &dispatches, &mismatches)) {
            r.error = "GPU benchmark could not initialize.";
            gpu_stress_shutdown();
            return r;
        }
        sample(r.telemetry);
        r.dispatches += dispatches;
        r.mismatches += mismatches;
        if (i >= 1 && gflops > 0.0 && std::isfinite(gflops)) {
            sum += gflops;
            ++samples;
        }
        svcSleepThread(5'000'000);
    }
    gpu_stress_shutdown();
    r.gflops = samples ? sum / samples : 0.0;
    r.ok = samples > 0 && r.gflops > 0.0 && r.mismatches == 0;
    if (!r.ok && r.error.empty()) r.error = r.mismatches ? "GPU mismatch detected." : "GPU benchmark returned no score.";
    return r;
}

CpuResult runCpu(int seconds) {
    CpuResult r;
    seconds = std::max(5, seconds);
    run_furmark_start(4); // Benchmark Toolbox CPU Ray Trace
    svcSleepThread(1'500'000'000LL);
    if (!run_furmark_running()) {
        r.error = "CPU Ray Trace benchmark could not initialize.";
        return r;
    }

    double sum = 0.0;
    int samples = 0;
    const int loops = seconds * 2;
    for (int i = 0; i < loops && run_furmark_running(); ++i) {
        const float fps = run_furmark_fps();
        sample(r.telemetry);
        if (i >= 2 && fps > 0.0f && std::isfinite(fps)) {
            sum += fps;
            ++samples;
        }
        svcSleepThread(500'000'000LL);
    }
    run_furmark_stop();
    sample(r.telemetry);
    r.fps = samples ? sum / samples : 0.0;
    r.ok = samples > 0 && r.fps > 0.0;
    if (!r.ok) r.error = "CPU Ray Trace benchmark returned no FPS.";
    return r;
}

} // namespace ocbench
