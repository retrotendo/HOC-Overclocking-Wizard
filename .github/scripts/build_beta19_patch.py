from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta19 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta19 function missing: {signature}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta19 opening brace missing: {signature}")
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"beta19 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# Version
p=Path('Makefile'); s=p.read_text(); s=must_replace(s,'APP_VERSION := 0.1.0-beta.18','APP_VERSION := 0.1.0-beta.19','version'); p.write_text(s)

# One charger source of truth. PSM tells us whether a charger is physically connected;
# do not infer this from instantaneous power draw.
Path('source/power_guard.hpp').write_text(r'''#pragma once
#include <switch.h>
#include "hoc_monitor.h"
#include <string>

namespace powerguard {

constexpr const char* kDisconnected =
    "USB charger disconnected. The running test/benchmark was stopped and its result was discarded. Please reconnect the charger and retry.";
constexpr const char* kUnavailable =
    "USB charger status could not be verified. Please reconnect the charger and retry.";

class Session {
public:
    Session() : initialized_(R_SUCCEEDED(psmInitialize())) {}
    ~Session() { if (initialized_) psmExit(); }
    Session(const Session&) = delete;
    Session& operator=(const Session&) = delete;

    bool connected(std::string* error = nullptr) const {
        if (!initialized_) {
            if (error) *error = kUnavailable;
            return false;
        }
        PsmChargerType type = PsmChargerType_Unconnected;
        if (R_FAILED(psmGetChargerType(&type))) {
            if (error) *error = kUnavailable;
            return false;
        }
        if (type == PsmChargerType_Unconnected) {
            if (error) *error = kDisconnected;
            return false;
        }
        return true;
    }
private:
    bool initialized_ = false;
};

inline void clearOverrides() {
    hocmonSetOverride(HocMonModule_CPU, 0);
    hocmonSetOverride(HocMonModule_GPU, 0);
    hocmonSetOverride(HocMonModule_MEM, 0);
}

} // namespace powerguard
''')

# Stress outcome can explicitly report charger loss instead of looking like an unstable candidate.
p=Path('source/stress_tests.hpp'); h=p.read_text()
h=must_replace(h,
'''    Cancelled,\n    InitError,''',
'''    Cancelled,\n    PowerLost,\n    InitError,''',
'PowerLost outcome')
p.write_text(h)

p=Path('source/stress_tests.cpp'); st=p.read_text()
st=must_replace(st,'#include "gui_console.hpp"\n','#include "gui_console.hpp"\n#include "power_guard.hpp"\n','power guard include')

new_stress_run=r'''Result run(Kind kind, int durationSeconds, const std::string& displayTitle, const std::string& displayContext) {
    Result out;
    Context c;
    powerguard::Session charger;
    std::string chargerError;
    if (!charger.connected(&chargerError)) {
        powerguard::clearOverrides();
        out.outcome = Outcome::PowerLost;
        out.detail = chargerError;
        return out;
    }

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
    bool powerLost = false;

    while (true) {
        if (!appletMainLoop()) {
            cancelled = true;
            break;
        }

        if (!charger.connected(&chargerError)) {
            powerLost = true;
            c.stop.store(true, std::memory_order_release);
            powerguard::clearOverrides();
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

    if (powerLost) {
        out.outcome = Outcome::PowerLost;
        out.detail = chargerError.empty() ? powerguard::kDisconnected : chargerError;
    } else if (cancelled) {
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
}'''
st=replace_function(st,'Result run(Kind kind, int durationSeconds, const std::string& displayTitle, const std::string& displayContext)',new_stress_run)
p.write_text(st)

# Every test screen gets an independent heartbeat spinner. It uses system time, not the
# progress value, so it keeps moving when memtester/benchmark percentages stay unchanged.
p=Path('source/gui_console.cpp'); g=p.read_text()
needle='''    drawText(x + 34, y + 104, 16, C_MUTED, fitText(s.subtitle, 16, w - 68));\n\n    if (s.benchmarkMode) {'''
spinner='''    drawText(x + 34, y + 104, 16, C_MUTED, fitText(s.subtitle, 16, w - 68));\n\n    // Independent activity heartbeat: visible even while the percentage is unchanged.\n    {\n        const int cx = x + w - 74, cy = y + 72;\n        const std::uint64_t tick = armGetSystemTick();\n        const std::uint64_t stepTicks = std::max<std::uint64_t>(1, armGetSystemTickFreq() / 10);\n        const int active = int((tick / stepTicks) % 8ULL);\n        for (int i = 0; i < 8; ++i) {\n            const double a = (3.14159265358979323846 * 2.0 * double(i)) / 8.0;\n            const int px = cx + int(std::cos(a) * 15.0);\n            const int py = cy + int(std::sin(a) * 15.0);\n            fillCircle(px, py, i == active ? 5 : 3, i == active ? C_CYAN : C_BORDER);\n        }\n        drawText(cx - 100, y + 61, 14, C_GREEN, "RUNNING");\n    }\n\n    if (s.benchmarkMode) {'''
g=must_replace(g,needle,spinner,'activity spinner')
g=g.replace('drawText(198, 24, 24, C_TEXT, "Stability Test");','drawText(198, 24, 24, C_TEXT, s.benchmarkMode ? "Benchmark" : "Stability Test");',1)
g=g.replace('drawText(x + 50, y + h - 61, 17, C_TEXT, "Please wait - the next RAM clock starts automatically");','drawText(x + 50, y + h - 61, 17, C_TEXT, "Running - keep the USB charger connected");',1)
p.write_text(g)

# Benchmarks: hard charger guard before start and during execution. RAM bench runs in a worker
# while the UI thread redraws every 100 ms, so the heartbeat remains live even during a long step.
p=Path('source/oc_bench.cpp'); b=p.read_text()
b=must_replace(b,'#include "gui_console.hpp"\n','#include "gui_console.hpp"\n#include "power_guard.hpp"\n','benchmark power guard include')
b=must_replace(b,'#include <cmath>\n','#include <cmath>\n#include <atomic>\n#include <thread>\n','benchmark thread includes')

new_fps=r'''bool runFpsScene(int which, int seconds, double& fps, Telemetry& telemetry, std::string& error) {
    powerguard::Session charger;
    if (!charger.connected(&error)) { powerguard::clearOverrides(); return false; }
    seconds = std::max(5, seconds);
    run_furmark_start(which);

    gui::StressView v{};
    v.benchmarkMode = true;
    v.title = which == 0 ? "GPU Performance Benchmark" : "CPU Ray Trace Benchmark";
    v.subtitle = "Performance measurement in progress";
    v.detail1 = "Starting benchmark";
    v.detail2 = "Result is discarded immediately if the USB charger is removed";
    gui::presentStress(v);

    for (int n=0;n<15;++n) {
        if (!charger.connected(&error)) { run_furmark_stop(); powerguard::clearOverrides(); return false; }
        svcSleepThread(100'000'000LL);
        v.benchmarkProgress = std::min(0.08, double(n+1)/200.0);
        gui::presentStress(v);
    }
    if (!run_furmark_running()) return false;

    double sum = 0.0;
    int samples = 0;
    const int loops = seconds * 2;
    for (int i = 0; i < loops && run_furmark_running(); ++i) {
        for (int sub=0;sub<5;++sub) {
            if (!charger.connected(&error)) { run_furmark_stop(); powerguard::clearOverrides(); return false; }
            v.benchmarkProgress = std::clamp((double(i) + double(sub)/5.0) / double(std::max(1,loops)), 0.0, 0.99);
            v.detail1 = which == 0 ? "Measuring GPU FPS" : "Measuring CPU Ray Trace FPS";
            gui::presentStress(v);
            svcSleepThread(100'000'000LL);
        }
        const float f = run_furmark_fps();
        sample(telemetry);
        if (i >= 2 && f > 0.0f && std::isfinite(f)) {
            sum += f;
            ++samples;
        }
    }
    run_furmark_stop();
    if (!charger.connected(&error)) { powerguard::clearOverrides(); return false; }
    sample(telemetry);
    fps = samples ? sum / samples : 0.0;
    return samples > 0 && fps > 0.0;
}'''
b=replace_function(b,'bool runFpsScene(int which, int seconds, double& fps, Telemetry& telemetry)',new_fps)

new_ram=r'''RamResult runRam(const std::string& displayContext) {
    RamResult r;
    powerguard::Session charger;
    if (!charger.connected(&r.error)) { powerguard::clearOverrides(); return r; }

    struct WorkerState {
        std::atomic<bool> done{false};
        std::atomic<bool> cancel{false};
        std::atomic<bool> initFailed{false};
        std::atomic<int> progressPermille{0};
        std::atomic<const char*> label{"Starting memory benchmark"};
        bench_results_t out{};
    } w;

    std::thread worker([&](){
        bench_ctx* ctx = bench_begin();
        if (!ctx) {
            w.initFailed.store(true, std::memory_order_release);
            w.done.store(true, std::memory_order_release);
            return;
        }
        const char* label = nullptr;
        float frac = 0.0f;
        while (!w.cancel.load(std::memory_order_acquire)) {
            const bool more = bench_step(ctx, &w.out, &label, &frac);
            if (label) w.label.store(label, std::memory_order_release);
            int p = int(std::clamp(frac,0.0f,1.0f)*1000.0f + 0.5f);
            w.progressPermille.store(p, std::memory_order_release);
            if (!more) break;
        }
        bench_end(ctx);
        w.done.store(true, std::memory_order_release);
    });

    bool powerLost = false;
    std::string powerError;
    while (!w.done.load(std::memory_order_acquire)) {
        if (!charger.connected(&powerError)) {
            powerLost = true;
            w.cancel.store(true, std::memory_order_release);
            powerguard::clearOverrides();
        }
        gui::StressView v{};
        v.benchmarkMode = true;
        v.benchmarkProgress = std::clamp(double(w.progressPermille.load(std::memory_order_relaxed))/1000.0,0.0,1.0);
        v.title = "RAM Memory Benchmark";
        v.subtitle = displayContext.empty() ? "Measuring RAM performance" : displayContext;
        const char* label = w.label.load(std::memory_order_acquire);
        v.detail1 = label ? label : "Memory benchmark";
        v.detail2 = powerLost ? "USB charger disconnected - stopping and discarding this result" : "Measuring bandwidth and latency for the RAM efficiency graph";
        gui::presentStress(v);
        svcSleepThread(100'000'000LL);
    }
    if (worker.joinable()) worker.join();

    if (powerLost) {
        r.error = powerError.empty() ? powerguard::kDisconnected : powerError;
        return r;
    }
    if (!charger.connected(&r.error)) { powerguard::clearOverrides(); return r; }
    if (w.initFailed.load(std::memory_order_acquire)) {
        r.error = "Memory benchmark could not initialize.";
        return r;
    }

    sample(r.telemetry);
    r.cpuCopy = w.out.cpu_copy;
    r.cpuRead = w.out.cpu_read;
    r.cpuWrite = w.out.cpu_write;
    r.gpuCopy = w.out.gpu_copy;
    r.gpuRead = w.out.gpu_read;
    r.gpuWrite = w.out.gpu_write;
    r.l2Ns = w.out.l2_ns;
    r.ramNs = w.out.ram_ns;
    r.score = oc::ramPerformanceScore(r.cpuCopy, r.cpuRead, r.cpuWrite,
                                      r.gpuCopy, r.gpuRead, r.gpuWrite, r.ramNs);
    r.ok = std::isfinite(r.score) && r.score > 0.0 && r.ramNs > 0.0;
    if (!r.ok) r.error = "Memory benchmark returned incomplete data.";
    return r;
}'''
b=replace_function(b,'RamResult runRam(const std::string& displayContext)',new_ram)

new_gpu=r'''GpuResult runGpu(int seconds) {
    GpuResult r;
    r.ok = runFpsScene(0, seconds, r.fps, r.telemetry, r.error);
    if (!r.ok && r.error.empty()) r.error = "GPU benchmark returned no FPS.";
    return r;
}'''
b=replace_function(b,'GpuResult runGpu(int seconds)',new_gpu)
new_cpu=r'''CpuResult runCpu(int seconds) {
    CpuResult r;
    r.ok = runFpsScene(4, seconds, r.fps, r.telemetry, r.error);
    if (!r.ok && r.error.empty()) r.error = "CPU Ray Trace benchmark returned no FPS.";
    return r;
}'''
b=replace_function(b,'CpuResult runCpu(int seconds)',new_cpu)
p.write_text(b)

# Main stress wrapper: charger loss is not a stability FAIL. Stop/discard, show a blocking
# reconnect notice, then restore the temporary clock overrides and restart the same test from 0.
p=Path('source/main_oc.cpp'); m=p.read_text()
m=must_replace(m,'#include "updater.hpp"\n','#include "updater.hpp"\n#include "power_guard.hpp"\n','main power guard include')

helper=r'''bool waitForChargerRetry() {
    powerguard::Session charger;
    PadState pad; padInitializeDefault(&pad);
    while (appletMainLoop()) {
        std::string e;
        const bool connected = charger.connected(&e);
        gui::ModalView m;
        m.version=HOC_WIZARD_VERSION;
        m.eyebrow="USB POWER REQUIRED";
        m.title="USB charger disconnected";
        m.body={"The running test was stopped immediately and its result was discarded.",
                connected ? "Charger detected. Press A to restart this test from the beginning." : "Please reconnect the USB charger to continue."};
        if(connected) m.primaryAction="Retry test";
        m.tone=gui::ModalTone::Amber;
        gui::presentModal(m);
        padUpdate(&pad);
        const u64 k=padGetButtonsDown(&pad);
        if(connected && (k&HidNpadButton_A)) return true;
        svcSleepThread(100'000'000LL);
    }
    return false;
}

'''
marker='''bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx){'''
pos=m.find(marker)
if pos<0: raise SystemExit('beta19 runStress marker missing')
m=m[:pos]+helper+m[pos:]
new_run_stress=r'''bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx){
    HocMonClocks before{}; hocmonGetTelemetry(&before);
    const u32 cpuOverride=before.overrideHz[0], gpuOverride=before.overrideHz[1], ramOverride=before.overrideHz[2];
    for(;;){
        g.testRunning=1;g.testStage=int(g.stage);saveState();
        auto r=stress::run(k,seconds,title,ctx);
        g.testRunning=0;g.testStage=-1;saveState();
        if(r.outcome==stress::Outcome::PowerLost){
            clearOverrides();
            if(!waitForChargerRetry()) return false;
            hocmonSetOverride(HocMonModule_CPU,cpuOverride);
            hocmonSetOverride(HocMonModule_GPU,gpuOverride);
            hocmonSetOverride(HocMonModule_MEM,ramOverride);
            svcSleepThread(500'000'000LL);
            continue;
        }
        return r.outcome==stress::Outcome::Pass;
    }
}'''
m=replace_function(m,'bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx)',new_run_stress)

# A charger-aborted CPU performance benchmark must not be interpreted as the CPU clock limit.
m=m.replace(
'''auto b=ocbench::runCpu(7);if(!b.ok||std::abs(b.telemetry.realCpuMHz-f)>5.0){finishCpuCapability();return;}''',
'''auto b=ocbench::runCpu(7);if(!b.ok){modalError(b.error);return;}if(std::abs(b.telemetry.realCpuMHz-f)>5.0){finishCpuCapability();return;}''')
p.write_text(m)

# Audit final generated source.
main=Path('source/main_oc.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text(); sth=Path('source/stress_tests.hpp').read_text(); bench=Path('source/oc_bench.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); pg=Path('source/power_guard.hpp').read_text()
checks={
 'beta19 version':'0.1.0-beta.19' in Path('Makefile').read_text(),
 'physical charger detection':'psmGetChargerType' in pg and 'PsmChargerType_Unconnected' in pg,
 'stress blocks without charger':'Outcome::PowerLost' in stress and 'charger.connected(&chargerError)' in stress,
 'stress clears overrides':'powerguard::clearOverrides()' in stress,
 'stress reconnect retry':'waitForChargerRetry' in main and 'continue;' in main[main.find('bool runStress'):main.find('bool requestReboot')],
 'RAM benchmark worker heartbeat':'std::thread worker' in bench and 'svcSleepThread(100\'000\'000LL)' in bench,
 'RAM benchmark charger abort':'USB charger disconnected - stopping and discarding this result' in bench,
 'GPU CPU charger checks':'runFpsScene' in bench and 'charger.connected(&error)' in bench,
 'independent spinner':'Independent activity heartbeat' in gui and 'RUNNING' in gui,
 'benchmark header':'s.benchmarkMode ? "Benchmark" : "Stability Test"' in gui,
 'CPU benchmark abort not limit':'if(!b.ok){modalError(b.error);return;}if(std::abs(b.telemetry.realCpuMHz-f)>5.0)' in main,
 '60s RAM retained':'runStress(stress::Kind::Ram,60,' in main,
 'DVB8 retained':'g.dvbGood=8;g.dvbCandidate=7' in main,
 'GPU flow retained':'GPU + RAM Integration' in main,
 'CPU flow retained':'CPU + RAM Final Validation' in main,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta19 source audit failed: '+', '.join(bad))
