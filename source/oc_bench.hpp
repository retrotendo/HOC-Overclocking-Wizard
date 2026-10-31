#pragma once

#include <cstdint>
#include <string>

namespace ocbench {

struct Telemetry {
    double realCpuMHz = 0.0;
    double realGpuMHz = 0.0;
    double realRamMHz = 0.0;
    double socMv = 0.0;
    double vdd2Mv = 0.0;
    double cpuMv = 0.0;
    double gpuMv = 0.0;
    double vddqMv = 0.0;
    double batteryPowerW = 0.0;
    int powerSamples = 0;
};

struct RamResult {
    bool ok = false;
    double cpuCopy = 0.0, cpuRead = 0.0, cpuWrite = 0.0;
    double gpuCopy = 0.0, gpuRead = 0.0, gpuWrite = 0.0;
    double l2Ns = 0.0, ramNs = 0.0;
    double score = 0.0;
    Telemetry telemetry;
    std::string error;
};

struct GpuResult {
    bool ok = false;
    double gflops = 0.0;
    std::uint64_t dispatches = 0;
    std::uint64_t mismatches = 0;
    Telemetry telemetry;
    std::string error;
};

struct CpuResult {
    bool ok = false;
    double fps = 0.0;
    Telemetry telemetry;
    std::string error;
};

RamResult runRam();
GpuResult runGpu(int windows = 8);
CpuResult runCpu(int seconds = 7);

} // namespace ocbench
