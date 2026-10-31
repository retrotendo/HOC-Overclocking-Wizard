/*
 * HOC Undervolting Wizard integrated stability-test controller.
 * Copyright (C) 2026 HOC Undervolting Wizard contributors.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 only.
 * See LICENSE and THIRD_PARTY_LICENSES.md.
 *
 * CPU and RAM test cores are GPLv2 components credited in
 * THIRD_PARTY_LICENSES.md. The GPU test implementation in this file was
 * written for this project against the public deko3d API.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include "stress_tests.hpp"
#include "cpu_stress.h"
#include "mt_cpu.h"
#include "gui_console.hpp"

#include <switch.h>
#include <deko3d.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <thread>
#include <vector>

namespace stress {
namespace {

using Clock = std::chrono::steady_clock;

enum FailureKind : int {
    FailureNone = 0,
    FailureCpuVerify = 1,
    FailureMemtester = 2,
    FailureGpuMismatch = 3,
    FailureGpuQueue = 4,
};

struct Context {
    std::atomic<bool> stop{false};
    std::atomic<bool> failed{false};
    std::atomic<int> initError{0};
    std::atomic<int> failureKind{FailureNone};

    std::atomic<std::uint64_t> cpuIterations{0};
    std::atomic<std::uint64_t> ramLoops{0};
    std::atomic<std::uint64_t> gpuIterations{0};
    std::atomic<std::uint64_t> errors{0};
    std::atomic<std::uint64_t> mismatches{0};

    std::atomic<std::uint64_t> mismatchIndex{0};
    std::atomic<std::uint64_t> expected{0};
    std::atomic<std::uint64_t> actual{0};

    std::atomic<std::uint64_t> ramBytes{0};
    std::atomic<const char*> ramTest{"-"};
    std::atomic<int> ramProgressPermille{0};
};

void markFailure(Context& c, FailureKind kind, std::uint64_t mismatches = 1) {
    c.failureKind.store(kind, std::memory_order_relaxed);
    c.mismatches.store(mismatches, std::memory_order_relaxed);
    c.errors.fetch_add(1, std::memory_order_relaxed);
    c.failed.store(true, std::memory_order_release);
    c.stop.store(true, std::memory_order_release);
}

void failGpuMismatch(Context& c, std::uint64_t index, std::uint64_t expected, std::uint64_t actual) {
    c.mismatchIndex.store(index, std::memory_order_relaxed);
    c.expected.store(expected, std::memory_order_relaxed);
    c.actual.store(actual, std::memory_order_relaxed);
    markFailure(c, FailureGpuMismatch, 1);
}

/*
 * CPU engine
 * ----------
 * cpu_stress mode 2 is the Wizard adaptation: the original Benchmark
 * Toolbox / Stress-NX Matrixprod workload runs continuously and each pass
 * is followed by the original Hanoi verification workload. Matrixprod itself
 * is unchanged; Hanoi gives us automatic arithmetic-error detection.
 */
void cpuWorker(Context& c) {
    cpu_stress_start(2);
    if (!cpu_stress_running()) {
        c.initError.store(20, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    while (!c.stop.load(std::memory_order_acquire)) {
        cpu_stress_status_t st{};
        cpu_stress_get(&st);
        c.cpuIterations.store(st.iters, std::memory_order_relaxed);
        if (st.mismatches) {
            markFailure(c, FailureCpuVerify, st.mismatches);
            break;
        }
        svcSleepThread(50'000'000);
    }

    cpu_stress_stop();
}

/*
 * RAM engine
 * ----------
 * mode 0 is the full CPU memtester sequence. mode 1 keeps one memtester
 * worker and adds the Benchmark Toolbox bandwidth burn-in workers; that mode
 * is used together with Matrixprod for the Wizard's combined CPU+RAM test.
 */
void ramWorker(Context& c, int mode) {
    mt_cpu_start(mode);
    if (!mt_cpu_running()) {
        c.initError.store(30, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    while (!c.stop.load(std::memory_order_acquire)) {
        mt_cpu_status_t st{};
        mt_cpu_get(&st);
        c.ramLoops.store(st.loop + st.burnin_iters, std::memory_order_relaxed);
        c.ramBytes.store(st.total_mb * 1024ULL * 1024ULL, std::memory_order_relaxed);
        c.ramTest.store(st.test ? st.test : "-", std::memory_order_relaxed);
        int p = int(st.progress * 1000.0f);
        if (p < 0) p = 0;
        if (p > 1000) p = 1000;
        c.ramProgressPermille.store(p, std::memory_order_relaxed);

        if (st.error || st.mismatches) {
            markFailure(c, FailureMemtester, st.mismatches ? st.mismatches : 1);
            break;
        }
        svcSleepThread(50'000'000);
    }

    mt_cpu_stop();
}

/* ----- Original project GPU compute/memory verifier using deko3d API. ----- */
std::uint32_t gpuTransform(std::uint32_t index, std::uint32_t value) {
    std::uint32_t x = value ^ (index * 0x9e3779b9u);
    for (std::uint32_t r = 0; r < 192u; ++r) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        x = x * 1664525u + 1013904223u;
        x ^= (r + 1u) * 0x85ebca6bu;
    }
    return x;
}

struct DkshHeader {
    std::uint32_t magic;
    std::uint32_t headerSize;
    std::uint32_t controlSize;
    std::uint32_t codeSize;
    std::uint32_t programsOffset;
    std::uint32_t numPrograms;
};

bool loadComputeShader(DkDevice device, DkShader* outShader, DkMemBlock* outCodeBlock) {
    FILE* f = std::fopen("romfs:/shaders/gpu_stress.dksh", "rb");
    if (!f) return false;

    DkshHeader hdr{};
    if (std::fread(&hdr, sizeof(hdr), 1, f) != 1 || hdr.controlSize == 0 || hdr.codeSize == 0) {
        std::fclose(f);
        return false;
    }

    void* control = std::malloc(hdr.controlSize);
    if (!control) {
        std::fclose(f);
        return false;
    }

    std::rewind(f);
    if (std::fread(control, hdr.controlSize, 1, f) != 1) {
        std::free(control);
        std::fclose(f);
        return false;
    }

    const std::uint32_t required = hdr.codeSize + DK_SHADER_CODE_UNUSABLE_SIZE;
    const std::uint32_t blockSize = (required + DK_MEMBLOCK_ALIGNMENT - 1u) & ~(DK_MEMBLOCK_ALIGNMENT - 1u);
    DkMemBlockMaker mm;
    dkMemBlockMakerDefaults(&mm, device, blockSize);
    mm.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached | DkMemBlockFlags_Code;
    DkMemBlock code = dkMemBlockCreate(&mm);
    if (!code) {
        std::free(control);
        std::fclose(f);
        return false;
    }

    if (std::fread(dkMemBlockGetCpuAddr(code), hdr.codeSize, 1, f) != 1) {
        dkMemBlockDestroy(code);
        std::free(control);
        std::fclose(f);
        return false;
    }
    std::fclose(f);

    DkShaderMaker sm;
    dkShaderMakerDefaults(&sm, code, 0);
    sm.control = control;
    sm.programId = 0;
    dkShaderInitialize(outShader, &sm);
    std::free(control);

    *outCodeBlock = code;
    return true;
}

void gpuWorker(Context& c) {
    ::Result rcRom = romfsInit();
    if (R_FAILED(rcRom)) {
        c.initError.store(10, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    DkDeviceMaker dm;
    dkDeviceMakerDefaults(&dm);
    DkDevice dev = dkDeviceCreate(&dm);
    if (!dev) {
        romfsExit();
        c.initError.store(11, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    DkQueueMaker qm;
    dkQueueMakerDefaults(&qm, dev);
    qm.flags = DkQueueFlags_Compute;
    DkQueue queue = dkQueueCreate(&qm);
    if (!queue) {
        dkDeviceDestroy(dev);
        romfsExit();
        c.initError.store(12, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    DkShader shader{};
    DkMemBlock codeBlock = nullptr;
    if (!loadComputeShader(dev, &shader, &codeBlock)) {
        dkQueueDestroy(queue);
        dkDeviceDestroy(dev);
        romfsExit();
        c.initError.store(13, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    constexpr std::uint32_t dataBytes = 4u * 1024u * 1024u;
    constexpr std::uint32_t cmdBytes = 64u * 1024u;
    constexpr std::uint32_t words = dataBytes / sizeof(std::uint32_t);

    DkMemBlockMaker mm;
    dkMemBlockMakerDefaults(&mm, dev, dataBytes);
    mm.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached;
    DkMemBlock dataBlock = dkMemBlockCreate(&mm);

    dkMemBlockMakerDefaults(&mm, dev, cmdBytes);
    mm.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached;
    DkMemBlock cmdBlock = dkMemBlockCreate(&mm);

    if (!dataBlock || !cmdBlock) {
        if (cmdBlock) dkMemBlockDestroy(cmdBlock);
        if (dataBlock) dkMemBlockDestroy(dataBlock);
        dkMemBlockDestroy(codeBlock);
        dkQueueDestroy(queue);
        dkDeviceDestroy(dev);
        romfsExit();
        c.initError.store(14, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    auto* data = static_cast<std::uint32_t*>(dkMemBlockGetCpuAddr(dataBlock));
    for (std::uint32_t i = 0; i < words; ++i)
        data[i] = 0x12345678u ^ (i * 0x27d4eb2du);

    DkCmdBufMaker cm;
    dkCmdBufMakerDefaults(&cm, dev);
    DkCmdBuf cmd = dkCmdBufCreate(&cm);
    if (!cmd) {
        dkMemBlockDestroy(cmdBlock);
        dkMemBlockDestroy(dataBlock);
        dkMemBlockDestroy(codeBlock);
        dkQueueDestroy(queue);
        dkDeviceDestroy(dev);
        romfsExit();
        c.initError.store(15, std::memory_order_release);
        c.stop.store(true, std::memory_order_release);
        return;
    }

    dkCmdBufAddMemory(cmd, cmdBlock, 0, cmdBytes);
    const DkShader* shaders[] = { &shader };
    dkCmdBufBindShaders(cmd, DkStageFlag_Compute, shaders, 1);
    dkCmdBufBindStorageBuffer(cmd, DkStage_Compute, 0, dkMemBlockGetGpuAddr(dataBlock), dataBytes);
    dkCmdBufDispatchCompute(cmd, words / 128u, 1, 1);
    DkCmdList list = dkCmdBufFinishList(cmd);

    constexpr std::uint32_t sampleCount = 64;
    std::uint32_t sampleIndex[sampleCount];
    std::uint32_t sampleExpected[sampleCount];
    for (std::uint32_t s = 0; s < sampleCount; ++s) {
        const std::uint32_t idx = (s * 16411u + 97u) % words;
        sampleIndex[s] = idx;
        sampleExpected[s] = data[idx];
    }

    while (!c.stop.load(std::memory_order_acquire)) {
        dkQueueSubmitCommands(queue, list);
        DkFence fence{};
        dkQueueSignalFence(queue, &fence, true);
        dkQueueWaitFence(queue, &fence);

        if (dkQueueIsInErrorState(queue)) {
            c.failureKind.store(FailureGpuQueue, std::memory_order_relaxed);
            c.errors.fetch_add(1, std::memory_order_relaxed);
            c.failed.store(true, std::memory_order_release);
            c.stop.store(true, std::memory_order_release);
            break;
        }

        for (std::uint32_t s = 0; s < sampleCount; ++s) {
            sampleExpected[s] = gpuTransform(sampleIndex[s], sampleExpected[s]);
            const std::uint32_t got = data[sampleIndex[s]];
            if (got != sampleExpected[s]) {
                failGpuMismatch(c, sampleIndex[s], sampleExpected[s], got);
                break;
            }
        }
        if (c.failed.load(std::memory_order_acquire)) break;
        c.gpuIterations.fetch_add(1, std::memory_order_relaxed);
    }

    dkQueueWaitIdle(queue);
    dkCmdBufDestroy(cmd);
    dkMemBlockDestroy(cmdBlock);
    dkMemBlockDestroy(dataBlock);
    dkMemBlockDestroy(codeBlock);
    dkQueueDestroy(queue);
    dkDeviceDestroy(dev);
    romfsExit();
}

const char* creditLine(Kind kind) {
    switch (kind) {
        case Kind::Cpu:
            return "Credits: Lineon / Horizon-OC - GPLv2";
        case Kind::Ram:
            return "Credits: Simon Kirby, Charles Cazabon / Horizon-OC - GPLv2";
        case Kind::Combined:
            return "Credits: Stress-NX + memtester / Horizon-OC - GPLv2";
        case Kind::Gpu:
            return "GPU code: HOC Wizard; deko3d by fincs (permissive)";
    }
    return "";
}

void renderProgress(Kind kind, int durationSeconds, std::uint64_t elapsedMs, const Context& c,
                    const std::string& displayTitle, const std::string& displayContext) {
    gui::StressView v{};
    v.title = displayTitle.empty() ? kindName(kind) : displayTitle;
    v.subtitle = displayContext.empty() ? "Stability validation in progress" : displayContext;
    v.detail1 = std::string("Test engine: ") + kindName(kind);
    v.detail2 = creditLine(kind);
    v.elapsedMs = elapsedMs;
    v.durationSeconds = durationSeconds;
    v.cpuPasses = c.cpuIterations.load(std::memory_order_relaxed);
    v.ramLoops = c.ramLoops.load(std::memory_order_relaxed);
    v.gpuPasses = c.gpuIterations.load(std::memory_order_relaxed);
    v.errors = c.errors.load(std::memory_order_relaxed);
    v.mismatches = c.mismatches.load(std::memory_order_relaxed);
    if (kind == Kind::Ram || kind == Kind::Combined) {
        const char* ramTest = c.ramTest.load(std::memory_order_relaxed);
        v.ramTest = ramTest ? ramTest : "-";
        v.ramBytes = c.ramBytes.load(std::memory_order_relaxed);
    }
    gui::presentStress(v);
}

} // namespace

const char* kindName(Kind kind) {
    switch (kind) {
        case Kind::Cpu: return "Stress-NX Matrixprod + Hanoi Verify";
        case Kind::Ram: return "memtester v4 CPU Memory Test";
        case Kind::Combined: return "Matrixprod + memtester Combined Stress";
        case Kind::Gpu: return "GPU Compute / Memory Stress";
    }
    return "Unknown Test";
}

Result run(Kind kind, int durationSeconds, const std::string& displayTitle, const std::string& displayContext) {
    Result out;
    Context c;

    std::vector<std::thread> workers;
    if (kind == Kind::Cpu) {
        workers.emplace_back(cpuWorker, std::ref(c));
    } else if (kind == Kind::Ram) {
        workers.emplace_back(ramWorker, std::ref(c), 0);
    } else if (kind == Kind::Combined) {
        workers.emplace_back(cpuWorker, std::ref(c));
        workers.emplace_back(ramWorker, std::ref(c), 1);
    } else if (kind == Kind::Gpu) {
        workers.emplace_back(gpuWorker, std::ref(c));
    }

    PadState pad;
    padInitializeDefault(&pad);

    const auto start = Clock::now();
    auto lastDraw = start - std::chrono::seconds(1);
    bool cancelled = false;

    while (true) {
        if (!appletMainLoop()) {
            cancelled = true;
            break;
        }

        const auto now = Clock::now();
        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

        if (now - lastDraw >= std::chrono::milliseconds(200)) {
            renderProgress(kind, durationSeconds, std::uint64_t(elapsed), c, displayTitle, displayContext);
            lastDraw = now;
        }

        if (c.failed.load(std::memory_order_acquire) || c.initError.load(std::memory_order_acquire) != 0)
            break;

        if (elapsed >= std::int64_t(durationSeconds) * 1000LL)
            break;

        padUpdate(&pad);
        const u64 down = padGetButtonsDown(&pad);
        if (down & HidNpadButton_B) {
            cancelled = true;
            break;
        }

        svcSleepThread(20'000'000);
    }

    c.stop.store(true, std::memory_order_release);
    for (auto& t : workers)
        if (t.joinable()) t.join();

    const auto finish = Clock::now();
    out.elapsedMs = std::uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(finish - start).count());
    out.iterations = c.cpuIterations.load(std::memory_order_relaxed)
                   + c.ramLoops.load(std::memory_order_relaxed)
                   + c.gpuIterations.load(std::memory_order_relaxed);
    out.errors = c.errors.load(std::memory_order_relaxed);
    out.mismatches = c.mismatches.load(std::memory_order_relaxed);

    if (cancelled) {
        out.outcome = Outcome::Cancelled;
        out.detail = "Test cancelled by user.";
    } else if (c.initError.load(std::memory_order_acquire) != 0) {
        out.outcome = Outcome::InitError;
        char buf[96];
        std::snprintf(buf, sizeof(buf), "Test engine initialization error %d.", c.initError.load());
        out.detail = buf;
    } else if (c.failed.load(std::memory_order_acquire) || out.errors || out.mismatches) {
        out.outcome = Outcome::Fail;
        switch (c.failureKind.load(std::memory_order_relaxed)) {
            case FailureCpuVerify:
                out.detail = "CPU Hanoi verification mismatch detected during Matrixprod stress.";
                break;
            case FailureMemtester:
                out.detail = "memtester detected one or more RAM mismatches.";
                break;
            case FailureGpuMismatch: {
                char buf[192];
                std::snprintf(buf, sizeof(buf), "GPU mismatch at index %llu: expected 0x%016llX, got 0x%016llX",
                    (unsigned long long)c.mismatchIndex.load(),
                    (unsigned long long)c.expected.load(),
                    (unsigned long long)c.actual.load());
                out.detail = buf;
                break;
            }
            case FailureGpuQueue:
                out.detail = "The deko3d GPU queue entered an error state.";
                break;
            default:
                out.detail = "The stability engine detected an error.";
                break;
        }
    } else {
        out.outcome = Outcome::Pass;
        out.detail = "Completed with zero detected errors.";
    }

    return out;
}

} // namespace stress
