from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta20 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile'); s=p.read_text(); s=must_replace(s,'APP_VERSION := 0.1.0-beta.19','APP_VERSION := 0.1.0-beta.20','version'); p.write_text(s)

# Audible attention notifier. Generates a short two-part rising "whoop-whoop" in PCM at runtime,
# so there is no external audio asset. WorkScope cancels any pending reminder when automatic work
# starts and arms one when it finishes. The main UI loop only plays it if the Wizard remains idle
# waiting for user input, then repeats every five minutes.
Path('source/attention_sound.hpp').write_text(r'''#pragma once

namespace attention {

void workStarted();
void workFinished();
void tick(bool userInput);
void alertNow();

class WorkScope {
public:
    WorkScope() { workStarted(); }
    ~WorkScope() { workFinished(); }
    WorkScope(const WorkScope&) = delete;
    WorkScope& operator=(const WorkScope&) = delete;
};

} // namespace attention
''')

Path('source/attention_sound.cpp').write_text(r'''#include "attention_sound.hpp"

#include <switch.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace attention {
namespace {

using Clock = std::chrono::steady_clock;
bool g_armed = false;
Clock::time_point g_due{};
constexpr auto kInitialDelay = std::chrono::milliseconds(900);
constexpr auto kRepeatDelay = std::chrono::minutes(5);
constexpr double kPi = 3.14159265358979323846;

bool playWhoop() {
    Result rc = audoutInitialize();
    if (R_FAILED(rc)) return false;

    constexpr int sampleRate = 48000;
    constexpr int channels = 2;
    constexpr int bytesPerSample = 2;
    constexpr int firstMs = 180;
    constexpr int gapMs = 70;
    constexpr int secondMs = 210;
    constexpr int tailMs = 70;
    constexpr int totalMs = firstMs + gapMs + secondMs + tailMs;
    const int frames = sampleRate * totalMs / 1000;
    const std::size_t dataBytes = std::size_t(frames) * channels * bytesPerSample;
    const std::size_t allocBytes = (dataBytes + 0xFFFu) & ~std::size_t(0xFFFu);

    void* raw = nullptr;
    if (posix_memalign(&raw, 0x1000, allocBytes) != 0 || !raw) {
        audoutExit();
        return false;
    }
    std::memset(raw, 0, allocBytes);
    auto* pcm = static_cast<std::int16_t*>(raw);

    double phase = 0.0;
    auto writeTone = [&](int startMs, int lengthMs, double f0, double f1, double amp) {
        const int start = sampleRate * startMs / 1000;
        const int count = sampleRate * lengthMs / 1000;
        const int fade = std::max(1, sampleRate * 12 / 1000);
        for (int i = 0; i < count && start + i < frames; ++i) {
            const double t = count > 1 ? double(i) / double(count - 1) : 0.0;
            const double freq = f0 + (f1 - f0) * t;
            phase += 2.0 * kPi * freq / double(sampleRate);
            double env = 1.0;
            if (i < fade) env *= double(i) / double(fade);
            if (count - i - 1 < fade) env *= double(count - i - 1) / double(fade);
            env = std::clamp(env, 0.0, 1.0);
            const std::int16_t v = std::int16_t(std::sin(phase) * amp * env);
            const int frame = start + i;
            pcm[frame * 2 + 0] = v;
            pcm[frame * 2 + 1] = v;
        }
    };

    writeTone(0, firstMs, 620.0, 1030.0, 13500.0);
    writeTone(firstMs + gapMs, secondMs, 760.0, 1320.0, 15000.0);

    AudioOutBuffer buffer{};
    buffer.buffer = raw;
    buffer.buffer_size = allocBytes;
    buffer.data_size = dataBytes;
    buffer.data_offset = 0;

    AudioOutState state = AudioOutState_Stopped;
    audoutGetAudioOutState(&state);
    if (state != AudioOutState_Started) rc = audoutStartAudioOut();
    AudioOutBuffer* released = nullptr;
    if (R_SUCCEEDED(rc)) rc = audoutPlayBuffer(&buffer, &released);
    audoutStopAudioOut();
    audoutExit();
    std::free(raw);
    return R_SUCCEEDED(rc);
}

} // namespace

void workStarted() {
    g_armed = false;
}

void workFinished() {
    g_armed = true;
    g_due = Clock::now() + kInitialDelay;
}

void tick(bool userInput) {
    if (userInput) {
        g_armed = false;
        return;
    }
    if (!g_armed) return;
    const auto now = Clock::now();
    if (now < g_due) return;
    playWhoop();
    g_due = Clock::now() + kRepeatDelay;
}

void alertNow() {
    playWhoop();
    g_armed = true;
    g_due = Clock::now() + kRepeatDelay;
}

} // namespace attention
''')

# Benchmarks are work scopes too. If another benchmark/test starts immediately, its constructor
# cancels the pending tone before the main UI loop gets a chance to play it.
p=Path('source/oc_bench.cpp'); b=p.read_text()
b=must_replace(b,'#include "power_guard.hpp"\n','#include "power_guard.hpp"\n#include "attention_sound.hpp"\n','bench attention include')
b=must_replace(b,'RamResult runRam(const std::string& displayContext) {\n    RamResult r;','RamResult runRam(const std::string& displayContext) {\n    attention::WorkScope attentionWork;\n    RamResult r;','RAM benchmark scope')
b=must_replace(b,'GpuResult runGpu(int seconds) {\n    GpuResult r;','GpuResult runGpu(int seconds) {\n    attention::WorkScope attentionWork;\n    GpuResult r;','GPU benchmark scope')
b=must_replace(b,'CpuResult runCpu(int seconds) {\n    CpuResult r;','CpuResult runCpu(int seconds) {\n    attention::WorkScope attentionWork;\n    CpuResult r;','CPU benchmark scope')
p.write_text(b)

# Stability tests use the same scope. The charger reconnect popup gets an immediate audible alert.
p=Path('source/main_oc.cpp'); m=p.read_text()
m=must_replace(m,'#include "power_guard.hpp"\n','#include "power_guard.hpp"\n#include "attention_sound.hpp"\n','main attention include')
m=must_replace(m,'bool waitForChargerRetry() {\n    powerguard::Session charger;','bool waitForChargerRetry() {\n    attention::alertNow();\n    powerguard::Session charger;','charger audible alert')
m=must_replace(m,
'''bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx){\n    HocMonClocks before{};''',
'''bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx){\n    attention::WorkScope attentionWork;\n    HocMonClocks before{};''',
'stress attention scope')

# Main waiting loop: no input -> service due reminder. Any user input cancels the reminder.
old='''        padUpdate(&pad);u64 k=padGetButtonsDown(&pad);if(!k){svcSleepThread(20'000'000);continue;}'''
new='''        padUpdate(&pad);u64 k=padGetButtonsDown(&pad);\n        if(!k){attention::tick(false);svcSleepThread(20'000'000);continue;}\n        attention::tick(true);'''
m=must_replace(m,old,new,'main idle reminder loop')
p.write_text(m)

# Audit generated source.
make=Path('Makefile').read_text(); main=Path('source/main_oc.cpp').read_text(); bench=Path('source/oc_bench.cpp').read_text();
audio=Path('source/attention_sound.cpp').read_text(); hdr=Path('source/attention_sound.hpp').read_text()
checks={
 'beta20 version':'0.1.0-beta.20' in make,
 'audout PCM generator':'audoutInitialize()' in audio and 'audoutPlayBuffer' in audio and 'writeTone' in audio,
 'two whoops':'writeTone(0, firstMs' in audio and 'writeTone(firstMs + gapMs' in audio,
 'five minute reminder':'std::chrono::minutes(5)' in audio,
 'idle tick':'attention::tick(false)' in main and 'attention::tick(true)' in main,
 'stress work scope':'attention::WorkScope attentionWork;' in main[main.find('bool runStress'):main.find('bool requestReboot')],
 'charger audible alert':'attention::alertNow();' in main[main.find('bool waitForChargerRetry'):main.find('bool runStress')],
 'RAM benchmark scope':'RamResult runRam' in bench and 'attention::WorkScope attentionWork;' in bench[bench.find('RamResult runRam'):bench.find('GpuResult runGpu')],
 'GPU benchmark scope':'attention::WorkScope attentionWork;' in bench[bench.find('GpuResult runGpu'):bench.find('CpuResult runCpu')],
 'CPU benchmark scope':'attention::WorkScope attentionWork;' in bench[bench.find('CpuResult runCpu'):],
 'beta19 charger retained':'powerguard::Session' in bench and 'waitForChargerRetry' in main,
 'beta19 heartbeat retained':'benchmarkProgress' in bench,
 '60s RAM retained':'runStress(stress::Kind::Ram,60,' in main,
 'DVB8 retained':'g.dvbGood=8;g.dvbCandidate=7' in main,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta20 source audit failed: '+', '.join(bad))
