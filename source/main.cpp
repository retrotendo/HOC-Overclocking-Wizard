#include <switch.h>

#include "stress_tests.hpp"
#include "hoc_monitor.h"
#include "updater.hpp"
#include "gui_console.hpp"

#include <algorithm>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr const char* APP_DIR   = "sdmc:/switch/HOC-Undervolting-Wizard";
constexpr const char* STATE     = "sdmc:/switch/HOC-Undervolting-Wizard/state.ini";
constexpr const char* STATE_TMP = "sdmc:/switch/HOC-Undervolting-Wizard/state.tmp";
constexpr const char* RESULTS   = "sdmc:/switch/HOC-Undervolting-Wizard/results.txt";
constexpr const char* DISCLAIMER_ACK = "sdmc:/switch/HOC-Undervolting-Wizard/disclaimer.accepted";
constexpr const char* LEGACY_STATE = "sdmc:/switch/HOC-Battery-Wizard/state.ini";
constexpr const char* HOC_CONFIG_INI = "sdmc:/config/horizon-oc/config.ini";
constexpr const char* HOC_CONFIG_TMP = "sdmc:/config/horizon-oc/config.ini.wizard.tmp";
constexpr const char* HOC_CONFIG_BACKUP = "sdmc:/config/horizon-oc/config.ini.wizard.bak";

constexpr int STOCK_LOW_UV = 0;
constexpr int STOCK_HIGH_UV = 0;
constexpr int STOCK_LOW_VMIN_MV = 620;
constexpr int STOCK_HIGH_VMIN_MV = 750;
constexpr int STOCK_VDDQ_MV = 600;
constexpr int STOCK_VDD2_UV = 1175000;

// Horizon OC temporary-override targets used by the Battery guide.
constexpr u32 CLOCK_CPU_NORMAL_HZ   = 1020000000U;
constexpr u32 CLOCK_CPU_VMIN_510_HZ = 510000000U;
constexpr u32 CLOCK_CPU_LOW_HZ      = 612000000U;
constexpr u32 CLOCK_CPU_VMIN_714_HZ = 714000000U;
constexpr u32 CLOCK_CPU_VMIN_MID_HZ = 816000000U;
constexpr u32 CLOCK_CPU_VMIN_918_HZ = 918000000U;
constexpr u32 CLOCK_CPU_BOOST_HZ    = 1785000000U;
constexpr u32 CLOCK_GPU_NORMAL_HZ = 384000000U;
constexpr u32 CLOCK_GPU_BOOST_HZ  = 76800000U;
constexpr u32 CLOCK_RAM_NORMAL_HZ = 1331200000U;
constexpr u32 CLOCK_RAM_BOOST_HZ  = 1600000000U;

constexpr int LOW_UV_MAX = 8;
constexpr int HIGH_UV_MAX = 13;
constexpr int LOW_VMIN_MIN_MV = 570;
constexpr int VDDQ_MIN_MV = 400;
constexpr int VDD2_MIN_UV = 912500;
constexpr int LOW_VMIN_STEP_MV = 10;
constexpr int VDDQ_STEP_MV = 10;
constexpr u32 VMIN_FLOOR_TOLERANCE_UV = 5000U;
constexpr int VDD2_STEP_UV = 12500;
constexpr int UI_COL = 3; // legacy direct-print compatibility

enum class Stage : int {
    Preparation = 0,
    LowUvQuick,
    LowUvLong,
    LowVminQuick,
    LowVminLong,
    VddqQuick,
    VddqLong,
    Vdd2Quick,
    Vdd2Long,
    Ram1331Validate,
    HighUvQuick,
    HighUvLong,
    BoostCpuRamValidate,
    NormalMatrixValidate,
    NormalMemValidate,
    NormalGpuValidate,
    BoostMatrixValidate,
    BoostMemValidate,
    BoostCpuMemValidate,
    RealWorldValidate,
    Complete,
    // Appended to preserve all existing beta.2 stage numbers in state.ini.
    LowVminValidate816,
    LowVminValidate1020,
    // beta.4 additions are appended to preserve older state.ini stage numbers.
    LowVminSweep612,
    LowVminSweep714,
    LowVminSweep918,
    LowVminFinalLong,
    RamBoostValidate,
    // beta.16: appended to keep every previous persisted stage number valid.
    HardwareDetection,
    LowVminPlateauValidate,
    // beta.25: LowUvQuick is boot-limit discovery; validation is separate.
    LowUvValidateQuick
};

struct WizardState {
    Stage stage = Stage::HardwareDetection;
    int lowUvGood = STOCK_LOW_UV;
    int lowUvTest = 1;
    int lowVminGood = STOCK_LOW_VMIN_MV;
    int lowVminTest = STOCK_LOW_VMIN_MV - LOW_VMIN_STEP_MV;
    int vddqGood = STOCK_VDDQ_MV;
    int vddqTest = STOCK_VDDQ_MV - VDDQ_STEP_MV;
    int vdd2GoodUv = STOCK_VDD2_UV;
    int vdd2TestUv = STOCK_VDD2_UV - VDD2_STEP_UV;
    int highUvGood = STOCK_HIGH_UV;
    int highUvTest = 1;
    u32 vminFloorHz = 0;
    int vminFloorObservedMv = 0;
    int ramPairRetryMode = 0;
    bool recoveryNeeded = false;
    bool warningBelow590Seen = false;
    bool limitNoticePending = false;

    // Hardware-guided VDDQ baseline.
    int dramId = -1;
    int consoleType = -1;
    int vddqStartMv = STOCK_VDDQ_MV;
    bool ramDetected = false;

    // Persistent-setting / reboot handoff.
    bool stageReadyAfterBoot = false;
    bool rebootPending = false;
    u32 pendingConfigMask = 0;

    // VMIN sweep observations and voltage-plateau representatives.
    int vminObsMv[6] = {};
    u32 vminObsMask = 0;
    int vminValidateCount = 0;
    int vminValidateIndex = 0;
    u32 vminValidateHz[6] = {};
    int vminValidateMv[6] = {};
    u32 lastProbeHz = 0;
    int lastProbeMv = 0;

    // Persisted before every built-in test. If this remains true after a reboot,
    // the wizard knows the previous test did not finish normally.
    bool testRunning = false;
    int testKind = 0;
    int testDurationSec = 0;
    int testStage = 0;
};

WizardState g;
bool g_resetConfirm = false;
bool g_interruptedPrompt = false;
bool g_resultScreen = false;
stress::Result g_lastResult;
stress::Kind g_lastKind = stress::Kind::Cpu;
std::string g_resultAction;
bool g_manualPass = false;
bool g_lastVminAtFloor = false;
bool g_guiPulse = false;
bool g_realWorldHelpPage = false;

void uiPresent();

struct OverrideExpectation {
    u32 cpuHz = 0;
    u32 gpuHz = 0;
    u32 ramHz = 0;
};

struct OverrideCheckState {
    bool readOk = false;
    Result rc = 0;
    OverrideExpectation expected;
    HocMonClocks current{};
    bool cpuOk = false;
    bool gpuOk = false;
    bool ramOk = false;
    bool cpuAppliedOk = true;
    bool voltageSamplesOk = true;
};

enum class PendingOverrideAction { StartTest, VminProbe };
bool g_overridePrompt = false;
PendingOverrideAction g_overrideAction = PendingOverrideAction::StartTest;
OverrideCheckState g_overrideCheck;

enum ConfigMask : u32 {
    Config_None    = 0,
    Config_LowUv   = 1u << 0,
    Config_LowVmin = 1u << 1,
    Config_Vddq    = 1u << 2,
    Config_Vdd2    = 1u << 3,
    Config_HighUv  = 1u << 4,
    Config_Prepare = 1u << 5,
};

struct ConfigCheckState {
    bool readOk = false;
    Result rc = 0;
    u32 mask = Config_None;
    HocMonConfig current{};
};

bool g_configPrompt = false;
bool g_configPromptSafetyOnly = false;
bool g_configDebugScreen = false;
int g_configDebugPage = 0;
HocMonConfigDebug g_configDebug{};
Result g_configDebugRc = 0;
bool g_rebootConfirm = false;
bool g_autoPrepConfirm = false;
u32 g_autoSetMask = Config_Prepare;
std::string g_autoPrepError;
bool g_bootPrompt = false;
int g_bootRecoveryCandidate = -1;
bool g_scanForLowUv = false;
ConfigCheckState g_configCheck;
Result g_rebootError = 0;
Result g_hardwareReadRc = 0;
HocMonHardware g_hardware{};
Result g_hardwareDebugRc = 0;
HocMonHardwareDebug g_hardwareDebug{};

bool g_vminScanScreen = false;
bool g_vminScanSuccess = false;
bool g_vminScanRestoreOk = true;
Result g_vminScanErrorRc = 0;
std::string g_vminScanErrorText;

std::string formatVdd2(int uv) {
    const int whole = uv / 1000;
    const int rem = uv % 1000;
    std::ostringstream os;
    os << whole;
    if (rem == 500) os << ".5";
    os << " mV";
    return os.str();
}

const char* stageName(Stage s) {
    switch (s) {
        case Stage::HardwareDetection: return "Hardware Detection";
        case Stage::Preparation: return "Preparation";
        case Stage::LowUvQuick: return "CPU Low UV - Boot Search";
        case Stage::LowUvValidateQuick: return "CPU Low UV - Validation Test";
        case Stage::LowUvLong: return "CPU Low UV - Voltage Scan";
        case Stage::LowVminQuick: return "CPU Low VMIN - Boot Search";
        case Stage::LowVminLong: return "CPU Low VMIN - Voltage Floor Scan";
        case Stage::LowVminSweep612: return "CPU Low VMIN - Voltage Floor Scan";
        case Stage::LowVminSweep714: return "CPU Low VMIN - Voltage Floor Scan";
        case Stage::LowVminValidate816: return "CPU Low VMIN - Voltage Floor Scan";
        case Stage::LowVminSweep918: return "CPU Low VMIN - Voltage Floor Scan";
        case Stage::LowVminValidate1020: return "CPU Low VMIN - Voltage Floor Scan";
        case Stage::LowVminFinalLong: return "CPU Low VMIN - Dynamic 1 Hour Validation";
        case Stage::LowVminPlateauValidate: return "CPU Low VMIN - Validation Test";
        case Stage::VddqQuick: return "VDDQ - Quick Search";
        case Stage::VddqLong: return "VDDQ - 30 Minute Validation";
        case Stage::Vdd2Quick: return "VDD2 - Quick Search";
        case Stage::Vdd2Long: return "RAM Rails - Final Pair Validation";
        case Stage::RamBoostValidate: return "RAM Rails - Boost Combined Validation";
        case Stage::Ram1331Validate: return "RAM - Normal Handheld Validation";
        case Stage::HighUvQuick: return "CPU High UV - Quick Search";
        case Stage::HighUvLong: return "CPU High UV - 1 Hour Validation";
        case Stage::BoostCpuRamValidate: return "High UV - CPU Memtester";
        case Stage::NormalMatrixValidate: return "Handheld CPU + RAM Validation";
        case Stage::NormalMemValidate: return "Final Normal - RAM";
        case Stage::NormalGpuValidate: return "Final Normal - GPU";
        case Stage::BoostMatrixValidate: return "Final Boost - CPU";
        case Stage::BoostMemValidate: return "Final Boost - RAM";
        case Stage::BoostCpuMemValidate: return "High UV + RAM Combined";
        case Stage::RealWorldValidate: return "Real-World Stability Check";
        case Stage::Complete: return "Complete";
    }
    return "Unknown";
}

bool testPlan(Stage s, stress::Kind& kind, int& seconds) {
    switch (s) {
        case Stage::HighUvQuick:
            kind = stress::Kind::Cpu; seconds = 60; return true;
        case Stage::LowVminFinalLong:
        case Stage::HighUvLong:
        case Stage::BoostMatrixValidate:
            kind = stress::Kind::Cpu; seconds = 3600; return true;
        case Stage::VddqQuick:
        case Stage::Vdd2Quick:
            kind = stress::Kind::Ram; seconds = 60; return true;
        case Stage::VddqLong:
            kind = stress::Kind::Ram; seconds = 1800; return true;
        case Stage::Vdd2Long:
        case Stage::RamBoostValidate:
        case Stage::Ram1331Validate:
        case Stage::NormalMatrixValidate:
        case Stage::NormalMemValidate:
        case Stage::BoostCpuRamValidate:
        case Stage::BoostMemValidate:
            kind = stress::Kind::Ram; seconds = 3600; return true;
        case Stage::BoostCpuMemValidate:
            kind = stress::Kind::Combined; seconds = 3600; return true;
        case Stage::NormalGpuValidate:
            kind = stress::Kind::Gpu; seconds = 3600; return true;
        default:
            return false;
    }
}

bool overridePlan(Stage s, OverrideExpectation& e) {
    switch (s) {
        case Stage::LowUvQuick:
        case Stage::LowUvValidateQuick:
        case Stage::LowUvLong:
        case Stage::Ram1331Validate:
        case Stage::NormalMatrixValidate:
        case Stage::NormalMemValidate:
        case Stage::NormalGpuValidate:
            e = {CLOCK_CPU_NORMAL_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;

        case Stage::LowVminQuick:
        case Stage::LowVminLong:
            e = {CLOCK_CPU_VMIN_510_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminSweep612:
            e = {CLOCK_CPU_LOW_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminSweep714:
            e = {CLOCK_CPU_VMIN_714_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminValidate816:
            e = {CLOCK_CPU_VMIN_MID_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminSweep918:
            e = {CLOCK_CPU_VMIN_918_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminValidate1020:
            e = {CLOCK_CPU_NORMAL_HZ, CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminFinalLong:
            e = {g.vminFloorHz ? g.vminFloorHz : CLOCK_CPU_VMIN_510_HZ,
                 CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;
        case Stage::LowVminPlateauValidate:
            e = {(g.vminValidateIndex >= 0 && g.vminValidateIndex < g.vminValidateCount)
                    ? g.vminValidateHz[g.vminValidateIndex] : CLOCK_CPU_NORMAL_HZ,
                 CLOCK_GPU_NORMAL_HZ, CLOCK_RAM_NORMAL_HZ};
            return true;

        case Stage::VddqQuick:
        case Stage::VddqLong:
        case Stage::Vdd2Quick:
        case Stage::Vdd2Long:
        case Stage::RamBoostValidate:
        case Stage::HighUvQuick:
        case Stage::HighUvLong:
        case Stage::BoostCpuRamValidate:
        case Stage::BoostMatrixValidate:
        case Stage::BoostMemValidate:
        case Stage::BoostCpuMemValidate:
            e = {CLOCK_CPU_BOOST_HZ, CLOCK_GPU_BOOST_HZ, CLOCK_RAM_BOOST_HZ};
            return true;

        default:
            return false;
    }
}

bool clockMatches(u32 current, u32 expected) {
    if (current == 0 || expected == 0) return false;
    const u32 tolerance = 2000000U; // tolerate display/list rounding such as 1331 vs 1331.2 MHz
    return current > expected ? (current - expected <= tolerance) : (expected - current <= tolerance);
}

std::string formatClock(u32 hz) {
    if (hz == 0) return "NOT SET";
    char buf[32];
    if (hz % 1000000U == 0)
        std::snprintf(buf, sizeof(buf), "%u MHz", hz / 1000000U);
    else
        std::snprintf(buf, sizeof(buf), "%.1f MHz", (double)hz / 1000000.0);
    return std::string(buf);
}

bool checkAllOverrides(Stage s) {
    g_overrideCheck = OverrideCheckState{};
    if (!overridePlan(s, g_overrideCheck.expected)) return true;

    g_overrideCheck.rc = hocmonGetClocks(&g_overrideCheck.current);
    if (R_FAILED(g_overrideCheck.rc)) {
        g_overrideCheck.readOk = false;
        return false;
    }

    g_overrideCheck.readOk = true;
    g_overrideCheck.cpuOk = clockMatches(g_overrideCheck.current.overrideHz[0], g_overrideCheck.expected.cpuHz);
    g_overrideCheck.gpuOk = clockMatches(g_overrideCheck.current.overrideHz[1], g_overrideCheck.expected.gpuHz);
    g_overrideCheck.ramOk = clockMatches(g_overrideCheck.current.overrideHz[2], g_overrideCheck.expected.ramHz);
    return g_overrideCheck.cpuOk && g_overrideCheck.gpuOk && g_overrideCheck.ramOk;
}

// VMIN floor probing is measurement-only. Read several HOC context samples so a
// stale single poll cannot decide the floor crossover. The median CPU rail
// voltage from matching override samples is used.
void renderVoltageScanModal(u32 cpuHz, int index, int total, const std::string& phase) {
    gui::ModalView m{};
    m.version = HOC_WIZARD_VERSION;
    m.eyebrow = "AUTOMATIC CPU VOLTAGE SCAN";
    m.title = "Finding the CPU voltage floor";
    std::string context = "CPU " + formatClock(cpuHz);
    if (index >= 0 && total > 0)
        context += "  |  Frequency " + std::to_string(index + 1) + " of " + std::to_string(total);
    m.body = {
        context,
        "GPU 384 MHz  |  RAM 1331.2 MHz",
        phase,
        "The Wizard is measuring automatically. No input is required."
    };
    m.tone = gui::ModalTone::Cyan;
    gui::presentModal(m);
}

bool sampleVminVoltage(Stage s, int sweepIndex = -1, int sweepTotal = 0) {
    if (!checkAllOverrides(s)) return false;

    constexpr int kSettleReads = 2;
    constexpr int kSamples = 9;
    constexpr int kAttempts = 2;
    constexpr u32 kMaxSpreadUv = 20000U;
    HocMonClocks latest = g_overrideCheck.current;

    for (int attempt = 0; attempt < kAttempts; ++attempt) {
        for (int settle = 0; settle < kSettleReads; ++settle) {
            renderVoltageScanModal(g_overrideCheck.expected.cpuHz, sweepIndex, sweepTotal,
                "Settling measurement " + std::to_string(settle + 1) + " of " + std::to_string(kSettleReads));
            svcSleepThread(700'000'000);
            HocMonClocks ignored{};
            if (R_SUCCEEDED(hocmonGetClocks(&ignored))) latest = ignored;
        }

        std::vector<u32> samples;
        samples.reserve(kSamples);
        for (int i = 0; i < kSamples; ++i) {
            std::string scanPhase = "Reading voltage sample " + std::to_string(i + 1) + " of " + std::to_string(kSamples);
            if (attempt > 0) scanPhase += "  |  retrying noisy measurement";
            renderVoltageScanModal(g_overrideCheck.expected.cpuHz, sweepIndex, sweepTotal, scanPhase);
            svcSleepThread(700'000'000);

            HocMonClocks cur{};
            Result rc = hocmonGetClocks(&cur);
            if (R_SUCCEEDED(rc) &&
                clockMatches(cur.overrideHz[0], g_overrideCheck.expected.cpuHz) &&
                clockMatches(cur.overrideHz[1], g_overrideCheck.expected.gpuHz) &&
                clockMatches(cur.overrideHz[2], g_overrideCheck.expected.ramHz) &&
                clockMatches(cur.targetHz[0], g_overrideCheck.expected.cpuHz) &&
                cur.cpuVoltageUv != 0) {
                samples.push_back(cur.cpuVoltageUv);
                latest = cur;
            }
        }

        if ((int)samples.size() != kSamples) {
            if (attempt + 1 < kAttempts) continue;
            break;
        }

        std::sort(samples.begin(), samples.end());
        const u32 spread = samples.back() - samples.front();
        if (spread > kMaxSpreadUv && attempt + 1 < kAttempts) continue;

        latest.cpuVoltageUv = samples[kSamples / 2];
        g_overrideCheck.current = latest;
        g_overrideCheck.readOk = true;
        g_overrideCheck.cpuOk = g_overrideCheck.gpuOk = g_overrideCheck.ramOk = true;
        g_overrideCheck.cpuAppliedOk = true;
        g_overrideCheck.voltageSamplesOk = true;
        return true;
    }

    g_overrideCheck.current = latest;
    g_overrideCheck.readOk = true;
    g_overrideCheck.cpuOk = clockMatches(latest.overrideHz[0], g_overrideCheck.expected.cpuHz);
    g_overrideCheck.gpuOk = clockMatches(latest.overrideHz[1], g_overrideCheck.expected.gpuHz);
    g_overrideCheck.ramOk = clockMatches(latest.overrideHz[2], g_overrideCheck.expected.ramHz);
    g_overrideCheck.cpuAppliedOk = clockMatches(latest.targetHz[0], g_overrideCheck.expected.cpuHz);
    g_overrideCheck.voltageSamplesOk = false;
    return false;
}



void ensureDir() {
    mkdir("sdmc:/switch", 0777);
    mkdir(APP_DIR, 0777);
}

bool copyFile(const char* from, const char* to) {
    std::ifstream src(from, std::ios::binary);
    if (!src) return false;
    std::ofstream dst(to, std::ios::binary | std::ios::trunc);
    if (!dst) return false;
    dst << src.rdbuf();
    return bool(dst);
}

void migrateLegacyState() {
    ensureDir();
    if (access(STATE, F_OK) != 0 && access(LEGACY_STATE, F_OK) == 0)
        copyFile(LEGACY_STATE, STATE);
}

bool saveState() {
    ensureDir();
    std::ofstream f(STATE_TMP, std::ios::trunc);
    if (!f) return false;
    f << "stage=" << static_cast<int>(g.stage) << "\n";
    f << "lowUvGood=" << g.lowUvGood << "\n";
    f << "lowUvTest=" << g.lowUvTest << "\n";
    f << "lowVminGood=" << g.lowVminGood << "\n";
    f << "lowVminTest=" << g.lowVminTest << "\n";
    f << "vddqGood=" << g.vddqGood << "\n";
    f << "vddqTest=" << g.vddqTest << "\n";
    f << "vdd2GoodUv=" << g.vdd2GoodUv << "\n";
    f << "vdd2TestUv=" << g.vdd2TestUv << "\n";
    f << "highUvGood=" << g.highUvGood << "\n";
    f << "highUvTest=" << g.highUvTest << "\n";
    f << "vminFloorHz=" << g.vminFloorHz << "\n";
    f << "vminFloorObservedMv=" << g.vminFloorObservedMv << "\n";
    f << "ramPairRetryMode=" << g.ramPairRetryMode << "\n";
    f << "recoveryNeeded=" << (g.recoveryNeeded ? 1 : 0) << "\n";
    f << "warningBelow590Seen=" << (g.warningBelow590Seen ? 1 : 0) << "\n";
    f << "limitNoticePending=" << (g.limitNoticePending ? 1 : 0) << "\n";
    f << "dramId=" << g.dramId << "\n";
    f << "consoleType=" << g.consoleType << "\n";
    f << "vddqStartMv=" << g.vddqStartMv << "\n";
    f << "ramDetected=" << (g.ramDetected ? 1 : 0) << "\n";
    f << "stageReadyAfterBoot=" << (g.stageReadyAfterBoot ? 1 : 0) << "\n";
    f << "rebootPending=" << (g.rebootPending ? 1 : 0) << "\n";
    f << "pendingConfigMask=" << g.pendingConfigMask << "\n";
    f << "vminObsMask=" << g.vminObsMask << "\n";
    f << "vminValidateCount=" << g.vminValidateCount << "\n";
    f << "vminValidateIndex=" << g.vminValidateIndex << "\n";
    f << "lastProbeHz=" << g.lastProbeHz << "\n";
    f << "lastProbeMv=" << g.lastProbeMv << "\n";
    for (int i = 0; i < 6; ++i) {
        f << "vminObsMv" << i << "=" << g.vminObsMv[i] << "\n";
        f << "vminValidateHz" << i << "=" << g.vminValidateHz[i] << "\n";
        f << "vminValidateMv" << i << "=" << g.vminValidateMv[i] << "\n";
    }
    f << "testRunning=" << (g.testRunning ? 1 : 0) << "\n";
    f << "testKind=" << g.testKind << "\n";
    f << "testDurationSec=" << g.testDurationSec << "\n";
    f << "testStage=" << g.testStage << "\n";
    f.flush();
    f.close();
    if (access(STATE, F_OK) == 0) remove(STATE);
    return rename(STATE_TMP, STATE) == 0;
}

void assignKV(const std::string& key, const std::string& value) {
    const int v = std::atoi(value.c_str());
    if (key == "stage") g.stage = static_cast<Stage>(v);
    else if (key == "lowUvGood") g.lowUvGood = v;
    else if (key == "lowUvTest") g.lowUvTest = v;
    else if (key == "lowVminGood") g.lowVminGood = v;
    else if (key == "lowVminTest") g.lowVminTest = v;
    else if (key == "vddqGood") g.vddqGood = v;
    else if (key == "vddqTest") g.vddqTest = v;
    else if (key == "vdd2GoodUv") g.vdd2GoodUv = v;
    else if (key == "vdd2TestUv") g.vdd2TestUv = v;
    else if (key == "highUvGood") g.highUvGood = v;
    else if (key == "highUvTest") g.highUvTest = v;
    else if (key == "vminFloorHz") g.vminFloorHz = (u32)v;
    else if (key == "vminFloorObservedMv") g.vminFloorObservedMv = v;
    else if (key == "ramPairRetryMode") g.ramPairRetryMode = v;
    else if (key == "recoveryNeeded") g.recoveryNeeded = (v != 0);
    else if (key == "warningBelow590Seen") g.warningBelow590Seen = (v != 0);
    else if (key == "limitNoticePending") g.limitNoticePending = (v != 0);
    else if (key == "dramId") g.dramId = v;
    else if (key == "consoleType") g.consoleType = v;
    else if (key == "vddqStartMv") g.vddqStartMv = v;
    else if (key == "ramDetected") g.ramDetected = (v != 0);
    else if (key == "stageReadyAfterBoot") g.stageReadyAfterBoot = (v != 0);
    else if (key == "rebootPending") g.rebootPending = (v != 0);
    else if (key == "pendingConfigMask") g.pendingConfigMask = (u32)std::strtoul(value.c_str(), nullptr, 10);
    else if (key == "vminObsMask") g.vminObsMask = (u32)std::strtoul(value.c_str(), nullptr, 10);
    else if (key == "vminValidateCount") g.vminValidateCount = v;
    else if (key == "vminValidateIndex") g.vminValidateIndex = v;
    else if (key == "lastProbeHz") g.lastProbeHz = (u32)std::strtoul(value.c_str(), nullptr, 10);
    else if (key == "lastProbeMv") g.lastProbeMv = v;
    else if (key.rfind("vminObsMv", 0) == 0) { int i = std::atoi(key.c_str() + 9); if (i >= 0 && i < 6) g.vminObsMv[i] = v; }
    else if (key.rfind("vminValidateHz", 0) == 0) { int i = std::atoi(key.c_str() + 14); if (i >= 0 && i < 6) g.vminValidateHz[i] = (u32)std::strtoul(value.c_str(), nullptr, 10); }
    else if (key.rfind("vminValidateMv", 0) == 0) { int i = std::atoi(key.c_str() + 14); if (i >= 0 && i < 6) g.vminValidateMv[i] = v; }
    else if (key == "testRunning") g.testRunning = (v != 0);
    else if (key == "testKind") g.testKind = v;
    else if (key == "testDurationSec") g.testDurationSec = v;
    else if (key == "testStage") g.testStage = v;
}

bool loadState() {
    std::ifstream f(STATE);
    if (!f) return false;
    std::string line;
    while (std::getline(f, line)) {
        const auto p = line.find('=');
        if (p != std::string::npos) assignKV(line.substr(0, p), line.substr(p + 1));
    }
    if (g.lowVminGood < LOW_VMIN_MIN_MV) g.lowVminGood = LOW_VMIN_MIN_MV;
    if (g.lowVminTest < LOW_VMIN_MIN_MV) g.lowVminTest = LOW_VMIN_MIN_MV;
    if (!g.ramDetected && g.stage == Stage::Preparation) g.stage = Stage::HardwareDetection;

    // States written by beta.15 used a manual 510->1020 MHz sweep. If an old
    // state is resumed in the middle/end of that flow, restart at beta.16+'s
    // automatic scan instead of entering plateau validation with empty data.
    const bool legacyVminState =
        g.stage == Stage::LowVminSweep612 || g.stage == Stage::LowVminSweep714 ||
        g.stage == Stage::LowVminValidate816 || g.stage == Stage::LowVminSweep918 ||
        g.stage == Stage::LowVminValidate1020 ||
        (g.stage == Stage::LowVminFinalLong && g.vminValidateCount == 0);
    if (legacyVminState) {
        g.stage = Stage::LowVminLong;
        g.stageReadyAfterBoot = true;
        g.pendingConfigMask = Config_None;
        g.vminObsMask = 0;
        g.vminValidateCount = 0;
        g.vminValidateIndex = 0;
        g.lastProbeHz = 0;
        g.lastProbeMv = 0;
        for (int i = 0; i < 6; ++i) {
            g.vminObsMv[i] = 0;
            g.vminValidateHz[i] = 0;
            g.vminValidateMv[i] = 0;
        }
    }

    if (g.stage == Stage::RamBoostValidate || g.stage == Stage::Ram1331Validate) {
        g.stage = Stage::NormalMatrixValidate;
        g.stageReadyAfterBoot = true;
        g.pendingConfigMask = Config_None;
    } else if (g.stage == Stage::HighUvLong) {
        g.stage = Stage::BoostCpuRamValidate;
        g.stageReadyAfterBoot = true;
        g.pendingConfigMask = Config_None;
    }

    const bool removedFinalValidationStage =
        g.stage == Stage::NormalMemValidate || g.stage == Stage::NormalGpuValidate ||
        g.stage == Stage::BoostMatrixValidate || g.stage == Stage::BoostMemValidate ||
        g.stage == Stage::BoostCpuMemValidate;
    if (removedFinalValidationStage) {
        g.stage = Stage::RealWorldValidate;
        g.stageReadyAfterBoot = true;
        g.pendingConfigMask = Config_None;
    }
    return true;
}

void resetState() {
    g = WizardState{};
    saveState();
}


struct RamProfile {
    const char* name;
    int vddqStartMv;
    const char* ocRange;
    bool known;
};

RamProfile ramProfileForId(int id) {
    switch (id) {
        case 3: case 5: case 6: return {"NEE 4GB", 640, "3100-3300 MHz", true};
        case 8: case 12: return {"AM-MGCJ 4GB", 640, "2633-2933 MHz", true};
        case 9: case 13: return {"AM-MGCJ 8GB", 640, "2633-2933 MHz", true};
        case 10: case 14: return {"NME 4GB", 640, "2300-2766 MHz", true};
        case 11: case 15: return {"WT:E 4GB", 600, "2500?-3033 MHz", true};
        case 17: case 19: case 24: return {"AA-MGCL 4GB", 640, "2766-3100 MHz", true};
        case 18: case 23: case 28: return {"AA-MGCL 8GB", 640, "2766-3100 MHz", true};
        case 20: case 21: case 22: return {"AB-MGCL 4GB", 640, "2500-2766 MHz", true};
        case 25: case 26: case 27: return {"WT:F 4GB", 600, "2633-2800 MHz", true};
        case 29: case 30: case 31: return {"x267 4GB", 640, "3100-3300 MHz", true};
        case 32: case 33: case 34: return {"WT:B 4GB", 600, "3066-3200 MHz", true};
        default: return {"Unknown", STOCK_VDDQ_MV, "Unknown", false};
    }
}

bool ramTuningAlreadyStarted(Stage st) {
    switch (st) {
        case Stage::VddqQuick:
        case Stage::VddqLong:
        case Stage::Vdd2Quick:
        case Stage::Vdd2Long:
        case Stage::RamBoostValidate:
        case Stage::Ram1331Validate:
        case Stage::HighUvQuick:
        case Stage::HighUvLong:
        case Stage::BoostCpuRamValidate:
        case Stage::NormalMatrixValidate:
        case Stage::NormalMemValidate:
        case Stage::NormalGpuValidate:
        case Stage::BoostMatrixValidate:
        case Stage::BoostMemValidate:
        case Stage::BoostCpuMemValidate:
        case Stage::RealWorldValidate:
        case Stage::Complete:
            return true;
        default:
            return false;
    }
}

bool detectRamHardware() {
    g_hardware = HocMonHardware{};
    g_hardwareDebug = HocMonHardwareDebug{};
    g_hardwareReadRc = hocmonGetHardware(&g_hardware);
    g_hardwareDebugRc = hocmonGetHardwareDebug(&g_hardwareDebug);
    if (R_FAILED(g_hardwareReadRc)) return false;
    const RamProfile p = ramProfileForId(g_hardware.dramId);
    // Icosa = Erista/V1, outside this Mariko Battery guide.
    if (!p.known || g_hardware.consoleType == 0) return false;
    const bool keepExistingRamTune = ramTuningAlreadyStarted(g.stage);
    g.dramId = g_hardware.dramId;
    g.consoleType = (int)g_hardware.consoleType;
    g.vddqStartMv = p.vddqStartMv;
    g.ramDetected = true;
    if (!keepExistingRamTune) {
        g.vddqGood = g.vddqStartMv;
        g.vddqTest = g.vddqStartMv - VDDQ_STEP_MV;
    }
    saveState();
    return true;
}

u32 defaultConfigMaskForStage(Stage st) {
    switch (st) {
        case Stage::Preparation: return Config_Prepare;
        case Stage::LowUvQuick:
        case Stage::LowUvLong: return Config_LowUv;
        case Stage::LowVminQuick:
        case Stage::LowVminLong: return Config_LowVmin;
        case Stage::VddqQuick:
        case Stage::VddqLong: return Config_Vddq;
        case Stage::Vdd2Quick:
        case Stage::Vdd2Long: return Config_Vdd2;
        case Stage::HighUvQuick:
        case Stage::HighUvLong: return Config_HighUv;
        default: return Config_None;
    }
}

u32 activeConfigMask() {
    if (g.stageReadyAfterBoot) return Config_None;
    if (g.pendingConfigMask) return g.pendingConfigMask;
    return defaultConfigMaskForStage(g.stage);
}

int targetLowUv() {
    // LowUvQuick is the boot-limit search. Validation uses the last value
    // that actually booted.
    return g.stage == Stage::LowUvQuick ? g.lowUvTest : g.lowUvGood;
}
int targetLowVmin() {
    return g.stage == Stage::LowVminQuick ? g.lowVminTest : g.lowVminGood;
}
int targetVddqMv() {
    return g.stage == Stage::VddqQuick ? g.vddqTest : g.vddqGood;
}
int targetVdd2Uv() {
    return g.stage == Stage::Vdd2Quick ? g.vdd2TestUv : g.vdd2GoodUv;
}
int targetHighUv() {
    return g.stage == Stage::HighUvQuick ? g.highUvTest : g.highUvGood;
}

std::string trimIni(const std::string& in) {
    const size_t first = in.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const size_t last = in.find_last_not_of(" \t\r\n");
    return in.substr(first, last - first + 1);
}

bool readHocConfigIni(HocMonConfig& out) {
    out = HocMonConfig{};
    std::ifstream f(HOC_CONFIG_INI);
    if (!f) return false;

    bool inValues = false;
    bool sawValuesSection = false;
    std::string line;
    while (std::getline(f, line)) {
        line = trimIni(line);
        if (line.empty() || line[0] == ';' || line[0] == '#') continue;

        if (line.front() == '[' && line.back() == ']') {
            inValues = (line == "[values]");
            if (inValues) sawValuesSection = true;
            continue;
        }
        if (!inValues) continue;

        const size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = trimIni(line.substr(0, eq));
        const std::string valueText = trimIni(line.substr(eq + 1));
        if (key.empty() || valueText.empty()) continue;

        char* end = nullptr;
        const unsigned long long value = std::strtoull(valueText.c_str(), &end, 0);
        if (end == valueText.c_str()) continue;

        if (key == "uncapped_clocks") out.uncappedClocks = (value != 0);
        else if (key == "kip_hp_mode") out.hpMode = (value != 0);
        else if (key == "mariko_emc_max_clock") out.ramMaxKHz = (u32)value;
        else if (key == "common_emc_mem_volt") out.vdd2Uv = (u32)value;
        else if (key == "mariko_emc_vddq_volt") out.vddqUv = (u32)value;
        else if (key == "mariko_cpu_uv_low") out.lowUv = (int)value;
        else if (key == "mariko_cpu_uv_high") out.highUv = (int)value;
        else if (key == "kip_table_conf") out.tableConf = (int)value;
        else if (key == "mariko_cpu_low_vmin") out.lowVminMv = (int)value;
        else if (key == "mariko_cpu_high_vmin") out.highVminMv = (int)value;
        else if (key == "mariko_cpu_max_clock") out.cpuMaxKHz = (u32)value;
        else if (key == "mariko_cpu_boost_clock") out.cpuBoostKHz = (u32)value;
    }

    return sawValuesSection;
}

bool verifyPersistentSettings(u32 mask);

bool writeAutomaticPreparationConfig(std::string& errorText) {
    errorText.clear();

    std::ifstream src(HOC_CONFIG_INI);
    if (!src) {
        errorText = "Could not open Horizon OC config.ini.";
        return false;
    }

    std::vector<std::string> lines;
    std::string line;
    while (std::getline(src, line)) lines.push_back(line);
    src.close();

    struct PrepValue { const char* key; std::string value; };
    const PrepValue values[] = {
        {"uncapped_clocks", "0"},
        {"kip_hp_mode", "0"},
        {"mariko_emc_max_clock", "1600000"},
        {"common_emc_mem_volt", std::to_string(STOCK_VDD2_UV)},
        {"mariko_emc_vddq_volt", std::to_string(g.vddqStartMv * 1000)},
        {"mariko_cpu_max_clock", "1963500"},
        {"mariko_cpu_low_vmin", std::to_string(STOCK_LOW_VMIN_MV)},
        {"mariko_cpu_high_vmin", std::to_string(STOCK_HIGH_VMIN_MV)},
        {"kip_table_conf", "3"},
        {"mariko_cpu_uv_low", std::to_string(STOCK_LOW_UV)},
        {"mariko_cpu_uv_high", std::to_string(STOCK_HIGH_UV)},
        {"mariko_cpu_boost_clock", "1785000"},
    };
    constexpr size_t valueCount = sizeof(values) / sizeof(values[0]);
    bool written[valueCount] = {};

    std::vector<std::string> out;
    out.reserve(lines.size() + valueCount + 3);
    bool inValues = false;
    bool sawValues = false;

    auto appendMissing = [&]() {
        for (size_t i = 0; i < valueCount; ++i) {
            if (!written[i]) {
                out.push_back(std::string(values[i].key) + "=" + values[i].value);
                written[i] = true;
            }
        }
    };

    for (const std::string& raw : lines) {
        const std::string trimmed = trimIni(raw);
        if (!trimmed.empty() && trimmed.front() == '[' && trimmed.back() == ']') {
            if (inValues) appendMissing();
            inValues = (trimmed == "[values]");
            if (inValues) sawValues = true;
            out.push_back(raw);
            continue;
        }

        if (inValues) {
            const size_t eq = trimmed.find('=');
            if (eq != std::string::npos) {
                const std::string key = trimIni(trimmed.substr(0, eq));
                bool replaced = false;
                for (size_t i = 0; i < valueCount; ++i) {
                    if (key == values[i].key) {
                        out.push_back(std::string(values[i].key) + "=" + values[i].value);
                        written[i] = true;
                        replaced = true;
                        break;
                    }
                }
                if (replaced) continue;
            }
        }
        out.push_back(raw);
    }

    if (inValues) appendMissing();
    if (!sawValues) {
        if (!out.empty() && !out.back().empty()) out.push_back("");
        out.push_back("[values]");
        appendMissing();
    }

    if (!copyFile(HOC_CONFIG_INI, HOC_CONFIG_BACKUP)) {
        errorText = "Could not create config.ini backup.";
        return false;
    }

    std::ofstream dst(HOC_CONFIG_TMP, std::ios::trunc);
    if (!dst) {
        errorText = "Could not create temporary config.ini.";
        return false;
    }
    for (const std::string& outLine : out) dst << outLine << "\n";
    dst.flush();
    const bool writeOk = bool(dst);
    dst.close();
    if (!writeOk) {
        remove(HOC_CONFIG_TMP);
        errorText = "Writing temporary config.ini failed.";
        return false;
    }

    remove(HOC_CONFIG_INI);
    if (rename(HOC_CONFIG_TMP, HOC_CONFIG_INI) != 0) {
        copyFile(HOC_CONFIG_BACKUP, HOC_CONFIG_INI);
        remove(HOC_CONFIG_TMP);
        errorText = "Replacing config.ini failed; backup restored.";
        return false;
    }

    fsdevCommitDevice("sdmc");
    return true;
}

void resetPreparationBaselineState() {
    g.lowUvGood = STOCK_LOW_UV;
    g.lowUvTest = STOCK_LOW_UV + 1;
    g.lowVminGood = STOCK_LOW_VMIN_MV;
    g.lowVminTest = STOCK_LOW_VMIN_MV - LOW_VMIN_STEP_MV;
    g.vddqGood = g.vddqStartMv;
    g.vddqTest = g.vddqStartMv - VDDQ_STEP_MV;
    g.vdd2GoodUv = STOCK_VDD2_UV;
    g.vdd2TestUv = STOCK_VDD2_UV - VDD2_STEP_UV;
    g.highUvGood = STOCK_HIGH_UV;
    g.highUvTest = STOCK_HIGH_UV + 1;
    g.recoveryNeeded = false;
    g.stageReadyAfterBoot = false;
    g.limitNoticePending = false;
    g.pendingConfigMask = Config_None;
}

bool applyAutomaticPreparation() {
    HocMonConfig desired{};
    desired.uncappedClocks = false;
    desired.hpMode = false;
    desired.ramMaxKHz = 1600000U;
    desired.vdd2Uv = (u32)STOCK_VDD2_UV;
    desired.vddqUv = (u32)g.vddqStartMv * 1000U;
    desired.lowUv = STOCK_LOW_UV;
    desired.highUv = STOCK_HIGH_UV;
    desired.tableConf = 3;
    desired.lowVminMv = STOCK_LOW_VMIN_MV;
    desired.highVminMv = STOCK_HIGH_VMIN_MV;
    desired.cpuMaxKHz = 1963500U;
    desired.cpuBoostKHz = 1785000U;

    const Result rc = hocmonApplyPreparation251(&desired);
    if (R_FAILED(rc)) {
        if (rc == 4)
            g_autoPrepError = "Automatic setup currently supports Horizon OC 2.5.1 only.";
        else {
            char msg[96];
            std::snprintf(msg, sizeof(msg), "Horizon OC Save KIP failed: 0x%08X", rc);
            g_autoPrepError = msg;
        }
        return false;
    }

    // HOC's SetConfigValues updates config.ini and live config; SetKipData persists
    // the KIP. Read the named INI keys back before allowing a reboot.
    svcSleepThread(150'000'000);
    if (!verifyPersistentSettings(Config_Prepare)) {
        g_autoPrepError = "Horizon OC readback did not match the requested Preparation values.";
        return false;
    }

    resetPreparationBaselineState();
    g.pendingConfigMask = Config_Prepare;
    g.rebootPending = false;
    saveState();
    return true;
}

bool applyAutomaticCurrentSetting(u32 mask) {
    g_autoPrepError.clear();
    if (mask & Config_Prepare)
        return applyAutomaticPreparation();

    u32 hocMask = 0;
    if (mask & Config_LowUv) hocMask |= 1U;
    if (mask & Config_LowVmin) hocMask |= 2U;
    if (!hocMask) {
        g_autoPrepError = "Automatic setting is not available for this step yet.";
        return false;
    }

    const Result rc = hocmonApplyCpuLow251(targetLowUv(), targetLowVmin(), hocMask);
    if (R_FAILED(rc)) {
        if (rc == 4)
            g_autoPrepError = "Automatic setting currently supports Horizon OC 2.5.1 only.";
        else {
            char msg[96];
            std::snprintf(msg, sizeof(msg), "Horizon OC Save KIP failed: 0x%08X", rc);
            g_autoPrepError = msg;
        }
        return false;
    }

    svcSleepThread(150'000'000);
    if (!verifyPersistentSettings(mask)) {
        g_autoPrepError = "Readback did not match the requested value.";
        return false;
    }
    g.pendingConfigMask = mask;
    saveState();
    return true;
}

bool preparationFixedSettingsMatch(const HocMonConfig& c) {
    return !c.uncappedClocks && !c.hpMode &&
           c.ramMaxKHz == 1600000U &&
           c.cpuMaxKHz == 1963500U &&
           c.tableConf == 3 &&
           c.cpuBoostKHz == 1785000U &&
           c.vdd2Uv != 0 && c.vddqUv != 0 &&
           c.lowVminMv != 0 && c.highVminMv != 0;
}

bool captureCurrentSettingsBaseline() {
    g_configCheck = ConfigCheckState{};
    g_configCheck.mask = Config_Prepare;
    g_configCheck.readOk = readHocConfigIni(g_configCheck.current);
    g_configCheck.rc = g_configCheck.readOk ? 0 : 0xF024;
    if (!g_configCheck.readOk || !preparationFixedSettingsMatch(g_configCheck.current))
        return false;

    const HocMonConfig& c = g_configCheck.current;
    g.lowUvGood = std::max(0, c.lowUv);
    g.lowUvTest = (g.lowUvGood < LOW_UV_MAX) ? g.lowUvGood + 1 : g.lowUvGood;
    g.lowVminGood = c.lowVminMv;
    g.lowVminTest = (g.lowVminGood > LOW_VMIN_MIN_MV) ? g.lowVminGood - LOW_VMIN_STEP_MV : g.lowVminGood;
    g.vddqGood = (int)(c.vddqUv / 1000U);
    g.vddqTest = (g.vddqGood > VDDQ_MIN_MV) ? g.vddqGood - VDDQ_STEP_MV : g.vddqGood;
    g.vdd2GoodUv = (int)c.vdd2Uv;
    g.vdd2TestUv = (g.vdd2GoodUv > VDD2_MIN_UV) ? g.vdd2GoodUv - VDD2_STEP_UV : g.vdd2GoodUv;
    g.highUvGood = std::max(0, c.highUv);
    g.highUvTest = (g.highUvGood < HIGH_UV_MAX) ? g.highUvGood + 1 : g.highUvGood;
    g.stageReadyAfterBoot = false;
    g.pendingConfigMask = Config_None;
    saveState();
    return true;
}

void continueFromPreparationBaseline() {
    // Nothing was changed: these values are already the user's active baseline.
    // Do not perform a fake Preparation reboot. Move directly to the first new
    // Low UV candidate, which will get its own normal set -> reboot -> 1 min test.
    g.rebootPending = false;
    g.pendingConfigMask = Config_None;
    g.limitNoticePending = false;
    if (g.lowUvGood >= LOW_UV_MAX) {
        g.stage = Stage::LowUvQuick;
        g.lowUvTest = g.lowUvGood;
        g.stageReadyAfterBoot = true;
        g.limitNoticePending = true;
    } else {
        g.stage = Stage::LowUvQuick;
        g.lowUvTest = g.lowUvGood + 1;
        g.stageReadyAfterBoot = false;
    }
    saveState();
}


bool configMatchesCurrent(u32 mask, const HocMonConfig& c) {
    if (mask & Config_Prepare) {
        return !c.uncappedClocks && !c.hpMode && c.ramMaxKHz == 1600000U &&
               c.vdd2Uv == (u32)STOCK_VDD2_UV && c.vddqUv == (u32)g.vddqStartMv * 1000U &&
               c.cpuMaxKHz == 1963500U && c.lowVminMv == STOCK_LOW_VMIN_MV &&
               c.highVminMv == STOCK_HIGH_VMIN_MV && c.tableConf == 3 &&
               c.lowUv == STOCK_LOW_UV && c.highUv == STOCK_HIGH_UV &&
               c.cpuBoostKHz == 1785000U;
    }
    if ((mask & Config_LowUv) && c.lowUv != targetLowUv()) return false;
    if ((mask & Config_LowVmin) && c.lowVminMv != targetLowVmin()) return false;
    if ((mask & Config_Vddq) && c.vddqUv != (u32)targetVddqMv() * 1000U) return false;
    if ((mask & Config_Vdd2) && c.vdd2Uv != (u32)targetVdd2Uv()) return false;
    if ((mask & Config_HighUv) && c.highUv != targetHighUv()) return false;
    return true;
}

bool verifyPersistentSettings(u32 mask) {
    g_configCheck = ConfigCheckState{};
    g_configCheck.mask = mask;
    g_configCheck.readOk = readHocConfigIni(g_configCheck.current);
    g_configCheck.rc = g_configCheck.readOk ? 0 : 0xF024;
    return g_configCheck.readOk && configMatchesCurrent(mask, g_configCheck.current);
}


u32 wizardTunableMismatchMask(const HocMonConfig& c) {
    u32 mask = Config_None;
    if (c.lowUv != targetLowUv()) mask |= Config_LowUv;
    if (c.lowVminMv != targetLowVmin()) mask |= Config_LowVmin;
    if (c.vddqUv != (u32)targetVddqMv() * 1000U) mask |= Config_Vddq;
    if (c.vdd2Uv != (u32)targetVdd2Uv()) mask |= Config_Vdd2;
    if (c.highUv != targetHighUv()) mask |= Config_HighUv;
    return mask;
}

bool guardWizardTunableState() {
    // During the active guide, all five tunable values must match the exact
    // state the Wizard expects. The one setting currently being changed is
    // already represented by target*(); every other setting remains at its
    // last known-good (or imported baseline) value.
    HocMonConfig current{};
    bool readOk = R_SUCCEEDED(hocmonGetConfig251(&current));
    if (!readOk) readOk = readHocConfigIni(current);

    if (!readOk) {
        g_configCheck = ConfigCheckState{};
        g_configCheck.readOk = false;
        g_configCheck.rc = 0xF024;
        g_configCheck.mask = Config_None;
        g_configPromptSafetyOnly = true;
        g_configPrompt = true;
        return false;
    }

    const u32 mismatch = wizardTunableMismatchMask(current);
    if (mismatch == Config_None) return true;

    g_configCheck = ConfigCheckState{};
    g_configCheck.readOk = true;
    g_configCheck.current = current;
    g_configCheck.mask = mismatch;
    g_configPromptSafetyOnly = true;
    g_configPrompt = true;
    return false;
}

void clearVminSweepData() {
    g.vminObsMask = 0;
    g.vminValidateCount = 0;
    g.vminValidateIndex = 0;
    g.lastProbeHz = 0;
    g.lastProbeMv = 0;
    g.vminFloorHz = 0;
    g.vminFloorObservedMv = 0;
    for (int i = 0; i < 6; ++i) {
        g.vminObsMv[i] = 0;
        g.vminValidateHz[i] = 0;
        g.vminValidateMv[i] = 0;
    }
}

int vminSweepIndex(Stage st) {
    switch (st) {
        case Stage::LowVminLong: return 0;
        case Stage::LowVminSweep612: return 1;
        case Stage::LowVminSweep714: return 2;
        case Stage::LowVminValidate816: return 3;
        case Stage::LowVminSweep918: return 4;
        case Stage::LowVminValidate1020: return 5;
        default: return -1;
    }
}

void buildVminPlateaus() {
    static const u32 clocks[6] = {
        CLOCK_CPU_VMIN_510_HZ, CLOCK_CPU_LOW_HZ, CLOCK_CPU_VMIN_714_HZ,
        CLOCK_CPU_VMIN_MID_HZ, CLOCK_CPU_VMIN_918_HZ, CLOCK_CPU_NORMAL_HZ
    };
    g.vminValidateCount = 0;
    g.vminValidateIndex = 0;
    g.vminFloorHz = 0;
    g.vminFloorObservedMv = 0;

    for (int i = 0; i < 6; ++i) {
        if (!(g.vminObsMask & (1u << i)) || g.vminObsMv[i] <= 0) continue;
        const int mv = g.vminObsMv[i];
        if (g.vminValidateCount == 0 || g.vminValidateMv[g.vminValidateCount - 1] != mv) {
            const int n = g.vminValidateCount++;
            g.vminValidateMv[n] = mv;
            g.vminValidateHz[n] = clocks[i];
        } else {
            // Same voltage region: only its highest frequency needs the long test.
            g.vminValidateHz[g.vminValidateCount - 1] = clocks[i];
        }
    }

    for (int i = 0; i < g.vminValidateCount; ++i) {
        if (std::abs(g.vminValidateMv[i] - g.lowVminGood) <= 5) {
            g.vminFloorHz = g.vminValidateHz[i];
            g.vminFloorObservedMv = g.vminValidateMv[i];
            break;
        }
    }
    if (!g.vminFloorHz && g.vminValidateCount > 0) {
        g.vminFloorHz = g.vminValidateHz[0];
        g.vminFloorObservedMv = g.vminValidateMv[0];
    }
    saveState();
}

void writeResults() {
    ensureDir();
    std::ofstream f(RESULTS, std::ios::trunc);
    if (!f) return;
    f << "HOC Undervolting Wizard - Final Results\n\n";
    if (g.ramDetected) {
        const RamProfile rp = ramProfileForId(g.dramId);
        f << "Detected RAM: " << rp.name << " (ID " << g.dramId << ")\n";
        f << "VDDQ starting point: " << g.vddqStartMv << " mV\n";
    }
    f << "CPU UV Table: 1683 MHz Tbreak\n";
    f << "CPU Low UV: " << g.lowUvGood << "\n";
    f << "CPU Low VMIN: " << g.lowVminGood << " mV\n";
    f << "RAM VDDQ: " << g.vddqGood << " mV\n";
    f << "RAM VDD2: " << formatVdd2(g.vdd2GoodUv) << "\n";
    f << "CPU High UV: " << g.highUvGood << "\n";
    if (g.vminFloorHz)
        f << "Detected highest Low VMIN floor clock: " << (g.vminFloorHz / 1000000U) << " MHz (~" << g.vminFloorObservedMv << " mV)\n";
    if (g.vminValidateCount > 0) {
        f << "CPU voltage regions validated:\n";
        for (int i = 0; i < g.vminValidateCount; ++i)
            f << "  " << (g.vminValidateHz[i] / 1000000U) << " MHz @ ~" << g.vminValidateMv[i] << " mV\n";
    }
    f << "\n";
    f << "Part-1-style critical CPU/RAM validation completed.\n";
    f << "Normal handheld target: 1020 / 384 / 1331.\n";
    f << "Nintendo Boost target: 1785 / 76.8 / 1600.\n";
}

int guiProgressStep(Stage s) {
    switch (s) {
        case Stage::HardwareDetection:
        case Stage::Preparation:
            return 1;
        case Stage::LowUvQuick:
        case Stage::LowUvValidateQuick:
        case Stage::LowUvLong:
            return 2;
        case Stage::LowVminQuick:
        case Stage::LowVminLong:
        case Stage::LowVminSweep612:
        case Stage::LowVminSweep714:
        case Stage::LowVminValidate816:
        case Stage::LowVminSweep918:
        case Stage::LowVminValidate1020:
        case Stage::LowVminFinalLong:
        case Stage::LowVminPlateauValidate:
            return 3;
        case Stage::VddqQuick:
        case Stage::VddqLong:
            return 4;
        case Stage::Vdd2Quick:
        case Stage::Vdd2Long:
        case Stage::RamBoostValidate:
        case Stage::Ram1331Validate:
        case Stage::NormalMatrixValidate:
            return 5;
        case Stage::HighUvQuick:
        case Stage::HighUvLong:
        case Stage::BoostCpuRamValidate:
        case Stage::BoostMatrixValidate:
        case Stage::BoostMemValidate:
        case Stage::BoostCpuMemValidate:
            return 6;
        case Stage::NormalMemValidate:
        case Stage::NormalGpuValidate:
        case Stage::RealWorldValidate:
        case Stage::Complete:
            return 7;
    }
    return 1;
}

u32 guiInstructionMask() {
    if (g_configPrompt) return g_configCheck.mask;
    if (g_autoPrepConfirm) return g_autoSetMask;
    if (g_rebootConfirm) return g_configCheck.mask;
    if (g_bootPrompt && g.pendingConfigMask) return g.pendingConfigMask;
    if (g.pendingConfigMask) return g.pendingConfigMask;
    return activeConfigMask();
}

std::string guiVdd2Value(int uv) {
    return formatVdd2(uv);
}

std::string guiDurationForStage(Stage st) {
    stress::Kind kind;
    int seconds = 0;
    if (!testPlan(st, kind, seconds)) return "";
    if (seconds == 60) return "1 minute";
    if (seconds == 1800) return "30 minutes";
    return "1 hour";
}

gui::View buildGuiView() {
    gui::View v{};
    v.version = HOC_WIZARD_VERSION;
    v.stageTitle = stageName(g.stage);
    if (g.stage == Stage::RealWorldValidate && g_realWorldHelpPage)
        v.stageTitle = "If Instability Occurs";
    v.activeStep = guiProgressStep(g.stage);
    v.pulse = g_guiPulse;
    v.preparationLayout = (g.stage == Stage::Preparation && !g_autoPrepConfirm && !g_rebootConfirm);
    v.hideValuesCard = (g.stage == Stage::HardwareDetection);
    v.fullWidthLayout = g_resultScreen || g.stage == Stage::RealWorldValidate || g.stage == Stage::Complete;
    if (v.preparationLayout && g_configPrompt && (g_configCheck.mask & Config_Prepare))
        v.stageTitle = "Preparation - Setting not ready";

    const u32 mask = guiInstructionMask();
    if (g_configPromptSafetyOnly) {
        v.instructionTitle = "Unexpected setting change";
        v.instructionLine1 = "Restore the red values";
        v.instructionLine2 = "A : Check again";
    } else if (mask & Config_Prepare) {
        v.instructionTitle = "Set the Preparation values";
        v.instructionLine1 = "Horizon OC + HOC Toolkit";
        v.instructionLine2 = "Match the SET values below";
    } else if (mask != Config_None) {
        const bool ram = (mask & (Config_Vddq | Config_Vdd2)) != 0;
        v.instructionTitle = (mask & (mask - 1U)) ? "Set values @ Horizon OC" : "Set value @ Horizon OC";
        v.instructionLine1 = ram ? "RAM Settings" : "CPU Settings";
        if ((mask & Config_LowUv) != 0)
            v.instructionLine2 = "Low UV  " + std::to_string(targetLowUv());
        else if ((mask & Config_LowVmin) != 0)
            v.instructionLine2 = "Low VMIN  " + std::to_string(targetLowVmin()) + " mV";
        else if ((mask & Config_Vddq) && (mask & Config_Vdd2))
            v.instructionLine2 = "VDDQ + VDD2 pair";
        else if ((mask & Config_Vddq) != 0)
            v.instructionLine2 = "VDDQ  " + std::to_string(targetVddqMv()) + " mV";
        else if ((mask & Config_Vdd2) != 0)
            v.instructionLine2 = "VDD2  " + guiVdd2Value(targetVdd2Uv());
        else if ((mask & Config_HighUv) != 0)
            v.instructionLine2 = "High UV  " + std::to_string(targetHighUv());
    } else if (g.limitNoticePending) {
        v.instructionTitle = "Wizard limit reached";
        v.instructionLine1 = stageName(g.stage);
        v.instructionLine2 = "Confirm to continue";
    } else if (g_bootPrompt) {
        v.instructionTitle = "Boot check";
        v.instructionLine1 = stageName(g.stage);
        v.instructionLine2 = "Confirm boot stability";
    } else if (g_vminScanScreen) {
        if (g_vminScanSuccess) {
            v.instructionTitle = "Start the validation test";
            v.instructionLine1 = std::to_string(g.vminValidateCount) +
                (g.vminValidateCount == 1 ? " voltage region found" : " voltage regions found");
            v.instructionLine2 = "A : Start test";
        } else {
            v.instructionTitle = "Retry the voltage scan";
            v.instructionLine1 = "The automatic scan stopped";
            v.instructionLine2 = "A : Retry scan";
        }
    } else if (g_configPrompt) {
        v.instructionTitle = "Setting not ready";
        v.instructionLine1 = "Fix WRONG values";
        v.instructionLine2 = "Then check again";
    } else if (g_rebootConfirm) {
        v.instructionTitle = "Reboot required";
        v.instructionLine1 = "Setting verified";
        v.instructionLine2 = "Apply with reboot";
    } else if (g_resultScreen) {
        v.instructionTitle = "Test result";
        v.instructionLine1 = stageName(g.stage);
        v.instructionLine2 = "Review and continue";
    } else if (g.stage == Stage::LowUvLong || g.stage == Stage::LowVminLong) {
        v.instructionTitle = "Scan voltage regions";
        v.instructionLine1 = stageName(g.stage);
        v.instructionLine2 = "A : Start scan";
    } else if (g.stage == Stage::LowUvValidateQuick || g.stage == Stage::LowVminPlateauValidate) {
        v.instructionTitle = "Start the validation test";
        v.instructionLine1 = std::to_string(g.vminValidateCount) +
            (g.vminValidateCount == 1 ? " voltage region to test" : " voltage regions to test");
        v.instructionLine2 = "A : Start test";
    } else if (g.stage == Stage::RealWorldValidate) {
        v.instructionTitle = "Final stability recommendation";
        v.instructionLine1 = "Optional real-world confirmation";
        v.instructionLine2 = "A : Continue to results";
    } else if (g.stage == Stage::Complete) {
        v.instructionTitle = "Undervolting complete";
        v.instructionLine1 = "Final values saved";
        v.instructionLine2 = "B : Exit";
    } else if (g.stage == Stage::HardwareDetection) {
        v.instructionTitle = g.ramDetected ? "Continue to Preparation" : "Retry hardware detection";
        v.instructionLine1 = g.ramDetected ? "Memory profile detected successfully" : "The memory profile could not be identified";
        v.instructionLine2 = g.ramDetected ? "A : Continue" : "A : Retry";
    } else {
        const std::string d = guiDurationForStage(g.stage);
        if (!d.empty()) {
            const bool candidateTest = g.stage == Stage::VddqQuick ||
                                       g.stage == Stage::Vdd2Quick ||
                                       g.stage == Stage::HighUvQuick;
            v.instructionTitle = candidateTest ? "Start the stability test" : "Start the validation test";
            v.instructionLine1 = candidateTest ? "Test the current candidate" : "Validate the current tuned settings";
            v.instructionLine2 = "A : Start test";
        } else {
            v.instructionTitle = stageName(g.stage);
            v.instructionLine1 = "Follow the guide";
            v.instructionLine2 = "Choose an action";
        }
    }

    HocMonConfig c{};
    bool have = R_SUCCEEDED(hocmonGetConfig251(&c));
    if (!have) have = readHocConfigIni(c);
    v.haveActiveValues = have;
    v.havePreparationActiveValues = have;

    if (v.preparationLayout) {
        auto addPrep = [&](const char* group, const char* label, const std::string& setValue,
                           const std::string& activeValue, bool mismatch) {
            gui::PreparationRow r{};
            r.group = group;
            r.label = label;
            r.setValue = setValue;
            r.activeValue = have ? activeValue : "unavailable";
            r.mismatch = have && mismatch;
            v.preparationRows.push_back(r);
        };

        addPrep("@ HORIZON OC", "General · Uncapped Clocks", "OFF", have ? (c.uncappedClocks ? "ON" : "OFF") : "", have && c.uncappedClocks);
        addPrep("@ HORIZON OC", "RAM · HP Mode", "OFF", have ? (c.hpMode ? "ON" : "OFF") : "", have && c.hpMode);
        addPrep("@ HORIZON OC", "RAM · RAM Max", "1600 MHz", have ? std::to_string(c.ramMaxKHz / 1000U) + " MHz" : "", have && c.ramMaxKHz != 1600000U);
        addPrep("@ HORIZON OC", "RAM · VDD2", formatVdd2(STOCK_VDD2_UV), have ? formatVdd2((int)c.vdd2Uv) : "", have && c.vdd2Uv != (u32)STOCK_VDD2_UV);
        addPrep("@ HORIZON OC", "RAM · VDDQ", std::to_string(g.vddqStartMv) + " mV", have ? std::to_string((int)(c.vddqUv / 1000U)) + " mV" : "", have && c.vddqUv != (u32)g.vddqStartMv * 1000U);
        addPrep("@ HORIZON OC", "CPU · CPU Max", "1963 MHz", have ? std::to_string(c.cpuMaxKHz / 1000U) + " MHz" : "", have && c.cpuMaxKHz != 1963500U);
        addPrep("@ HORIZON OC", "CPU · Low VMIN", std::to_string(STOCK_LOW_VMIN_MV) + " mV", have ? std::to_string(c.lowVminMv) + " mV" : "", have && c.lowVminMv != STOCK_LOW_VMIN_MV);
        addPrep("@ HORIZON OC", "CPU · High VMIN", std::to_string(STOCK_HIGH_VMIN_MV) + " mV", have ? std::to_string(c.highVminMv) + " mV" : "", have && c.highVminMv != STOCK_HIGH_VMIN_MV);
        const std::string activeTable = !have ? "" :
            (c.tableConf == 1 ? "Default" : c.tableConf == 2 ? "1581 Tbreak" :
             c.tableConf == 3 ? "1683 Tbreak" : c.tableConf == 4 ? "Extreme UV" : "Unknown");
        addPrep("@ HORIZON OC", "CPU · UV Table", "1683 Tbreak", activeTable, have && c.tableConf != 3);
        addPrep("@ HORIZON OC", "CPU · Low UV", "0", have ? std::to_string(c.lowUv) : "", have && c.lowUv != STOCK_LOW_UV);
        addPrep("@ HORIZON OC", "CPU · High UV", "0", have ? std::to_string(c.highUv) : "", have && c.highUv != STOCK_HIGH_UV);
        addPrep("@ HOC TOOLKIT", "CPU Boost", "1785 MHz", have ? std::to_string(c.cpuBoostKHz / 1000U) + " MHz" : "", have && c.cpuBoostKHz != 1785000U);
    }

    v.values[0].label = "CPU Low UV";
    v.values[1].label = "CPU Low VMIN";
    v.values[2].label = "VDDQ";
    v.values[3].label = "VDD2";
    v.values[4].label = "CPU High UV";

    if (have) {
        v.values[0].value = std::to_string(c.lowUv);
        v.values[1].value = std::to_string(c.lowVminMv) + " mV";
        v.values[2].value = std::to_string((int)(c.vddqUv / 1000U)) + " mV";
        v.values[3].value = guiVdd2Value((int)c.vdd2Uv);
        v.values[4].value = std::to_string(c.highUv);

        if (mask & Config_Prepare) {
            v.values[0].mismatch = c.lowUv != STOCK_LOW_UV;
            v.values[1].mismatch = c.lowVminMv != STOCK_LOW_VMIN_MV;
            v.values[2].mismatch = (int)(c.vddqUv / 1000U) != g.vddqStartMv;
            v.values[3].mismatch = (int)c.vdd2Uv != STOCK_VDD2_UV;
            v.values[4].mismatch = c.highUv != STOCK_HIGH_UV;
        } else {
            // Always compare every tunable value against the current Wizard
            // state, not just the setting being changed on this page. This
            // immediately exposes accidental changes in another domain.
            v.values[0].mismatch = c.lowUv != targetLowUv();
            v.values[1].mismatch = c.lowVminMv != targetLowVmin();
            v.values[2].mismatch = c.vddqUv != (u32)targetVddqMv() * 1000U;
            v.values[3].mismatch = c.vdd2Uv != (u32)targetVdd2Uv();
            v.values[4].mismatch = c.highUv != targetHighUv();
        }
    }
    return v;
}

void guiPageClear() {
    gui::begin(buildGuiView());
}

void uiPresent() {
    if (gui::isInitialized()) gui::present();
    else consoleUpdate(nullptr);
}

void uiPrintf(int row, const char* fmt, ...) {
    char buffer[1024];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    gui::printLeft(row, buffer);
}

const char* compactStepName(Stage s) {
    switch (s) {
        case Stage::HardwareDetection: return "Hardware Detection";
        case Stage::Preparation: return "Preparation";
        case Stage::LowUvQuick: return "CPU Low UV - Boot Search";
        case Stage::LowUvValidateQuick: return "CPU Low UV - Validation Test";
        case Stage::LowUvLong: return "CPU Low UV - Voltage Scan";
        case Stage::LowVminQuick: return "CPU Low VMIN - Boot Search";
        case Stage::LowVminLong: return "CPU Low VMIN - Clock Check";
        case Stage::LowVminSweep612: return "CPU Low VMIN - Clock Check";
        case Stage::LowVminSweep714: return "CPU Low VMIN - Clock Check";
        case Stage::LowVminValidate816: return "CPU Low VMIN - Clock Check";
        case Stage::LowVminSweep918: return "CPU Low VMIN - Clock Check";
        case Stage::LowVminValidate1020: return "CPU Low VMIN - Clock Check";
        case Stage::LowVminFinalLong: return "CPU Low VMIN - Validate";
        case Stage::LowVminPlateauValidate: return "CPU Low VMIN - Validation Test";
        case Stage::VddqQuick: return "RAM VDDQ";
        case Stage::VddqLong: return "RAM VDDQ - 30 min Validate";
        case Stage::Vdd2Quick: return "RAM VDD2";
        case Stage::Vdd2Long: return "RAM Rails - Final Pair";
        case Stage::RamBoostValidate: return "RAM Rails - Boost";
        case Stage::Ram1331Validate: return "RAM Rails - Handheld";
        case Stage::HighUvQuick: return "CPU High UV";
        case Stage::HighUvLong: return "CPU High UV - Validate";
        case Stage::BoostCpuRamValidate: return "High UV - CPU Memtester";
        case Stage::NormalMatrixValidate: return "Handheld CPU + RAM";
        case Stage::NormalMemValidate: return "Final Handheld - RAM";
        case Stage::NormalGpuValidate: return "Final Handheld - GPU";
        case Stage::BoostMatrixValidate: return "Final Boost - CPU";
        case Stage::BoostMemValidate: return "Final Boost - RAM";
        case Stage::BoostCpuMemValidate: return "High UV + RAM Combined";
        case Stage::RealWorldValidate: return "Real World";
        case Stage::Complete: return "Complete";
    }
    return "Unknown";
}

void title() {
    uiPrintf(1, "\x1b[1;96mStep : %s\x1b[0m", compactStepName(g.stage));
    uiPrintf(2, "------------------------------------------------");
}

void printResetHint(int lastOptionRow) {
    // Keep three empty lines between the final action and Reset.
    uiPrintf(lastOptionRow + 4, "- : Reset");
}

const char* compactTestName(stress::Kind kind) {
    switch (kind) {
        case stress::Kind::Cpu: return "Matrix + Hanoi";
        case stress::Kind::Ram: return "CPU memtester";
        case stress::Kind::Combined: return "CPU + RAM";
        case stress::Kind::Gpu: return "GPU compute/memory";
    }
    return "Built-in test";
}

void printOverrides(int row, const OverrideExpectation& e) {
    uiPrintf(row,     "Temporary Overrides:");
    uiPrintf(row + 1, " - CPU : %s", formatClock(e.cpuHz).c_str());
    uiPrintf(row + 2, " - GPU : %s", formatClock(e.gpuHz).c_str());
    uiPrintf(row + 3, " - RAM : %s", formatClock(e.ramHz).c_str());
}

void footerTest(int row) {
    const bool candidateTest = g.stage == Stage::VddqQuick ||
                               g.stage == Stage::Vdd2Quick ||
                               g.stage == Stage::HighUvQuick;
    if (candidateTest) {
        uiPrintf(row,     "A : Start 1-minute stability test");
        uiPrintf(row + 1, "+ : Known stable / Skip stability test");
    } else {
        uiPrintf(row,     "A : Start validation test");
        uiPrintf(row + 1, "+ : Known PASS / Skip validation test");
    }
    uiPrintf(row + 2, "B : Exit");
    printResetHint(row + 2);
}



bool restoreTemporaryOverrides(const HocMonClocks& before) {
    bool ok = true;
    // Restore GPU/RAM first, CPU last so a previous high CPU override is not
    // reintroduced while the scan's RAM/GPU clocks are still active.
    const u32 modules[3] = {HocMonModule_GPU, HocMonModule_MEM, HocMonModule_CPU};
    for (u32 module : modules) {
        Result rc = hocmonSetOverride(module, before.overrideHz[module]);
        if (R_FAILED(rc)) ok = false;
    }
    svcSleepThread(300'000'000);
    return ok;
}

bool setupAutomaticTestOverrides(Stage st, HocMonClocks& before) {
    g_overrideCheck = OverrideCheckState{};
    if (!overridePlan(st, g_overrideCheck.expected)) return true;

    g_overrideCheck.rc = hocmonGetClocks(&before);
    if (R_FAILED(g_overrideCheck.rc)) {
        g_overrideCheck.readOk = false;
        return false;
    }

    // Set the supporting clocks first and CPU last. The user does not need to
    // manage these Temporary Overrides manually.
    Result rc = hocmonSetOverride(HocMonModule_GPU, g_overrideCheck.expected.gpuHz);
    if (R_SUCCEEDED(rc)) rc = hocmonSetOverride(HocMonModule_MEM, g_overrideCheck.expected.ramHz);
    if (R_SUCCEEDED(rc)) rc = hocmonSetOverride(HocMonModule_CPU, g_overrideCheck.expected.cpuHz);
    if (R_FAILED(rc)) {
        g_overrideCheck.rc = rc;
        restoreTemporaryOverrides(before);
        return false;
    }

    svcSleepThread(400'000'000);
    g_overrideCheck.rc = hocmonGetClocks(&g_overrideCheck.current);
    if (R_FAILED(g_overrideCheck.rc)) {
        g_overrideCheck.readOk = false;
        restoreTemporaryOverrides(before);
        return false;
    }

    g_overrideCheck.readOk = true;
    g_overrideCheck.cpuOk = clockMatches(g_overrideCheck.current.overrideHz[0], g_overrideCheck.expected.cpuHz);
    g_overrideCheck.gpuOk = clockMatches(g_overrideCheck.current.overrideHz[1], g_overrideCheck.expected.gpuHz);
    g_overrideCheck.ramOk = clockMatches(g_overrideCheck.current.overrideHz[2], g_overrideCheck.expected.ramHz);
    if (!(g_overrideCheck.cpuOk && g_overrideCheck.gpuOk && g_overrideCheck.ramOk)) {
        restoreTemporaryOverrides(before);
        return false;
    }
    return true;
}

void renderVminScanScreen() {
    guiPageClear();
    if (!g_vminScanSuccess) {
        uiPrintf(5, "Automatic voltage scan stopped.");
        if (!g_vminScanErrorText.empty()) uiPrintf(7, "%s", g_vminScanErrorText.c_str());
        if (g_vminScanErrorRc) uiPrintf(8, "Result : 0x%08X", g_vminScanErrorRc);
        uiPrintf(13, "A : Retry voltage scan");
        uiPrintf(14, "B : Back");
        uiPresent();
        return;
    }
    uiPrintf(5, "Automatic scan complete.");
    uiPrintf(7, "The Wizard found %d voltage region%s to validate.",
             g.vminValidateCount, g.vminValidateCount == 1 ? "" : "s");
    int row = 9;
    for (int i = 0; i < g.vminValidateCount && i < 6; ++i)
        uiPrintf(row++, "%d. %s @ ~%d mV", i + 1,
                 formatClock(g.vminValidateHz[i]).c_str(), g.vminValidateMv[i]);
    row++;
    uiPrintf(row++, "Each region will be tested for 1 minute.");
    row++;
    uiPrintf(row++, "A : Start validation test");
    uiPrintf(row++, "+ : Known PASS / Skip validation test");
    uiPrintf(row++, "B : Exit");
    printResetHint(row - 1);
    uiPresent();
}

void renderHardwareDetection() {
    title();
    if (g.ramDetected) {
        const RamProfile rp = ramProfileForId(g.dramId);
        uiPrintf(6, "The Wizard detected the memory profile used for RAM tuning.");
        uiPrintf(9, "Memory Module : %s", rp.name);
        uiPrintf(10, "VDDQ Start : %d mV", g.vddqStartMv);
        uiPrintf(11, "Expected OC Range : %s", rp.ocRange);
        uiPrintf(13, "The OC range is only a guide estimate; silicon quality varies.");
        uiPrintf(16, "A : Continue to Preparation");
        uiPrintf(17, "B : Exit");
        printResetHint(17);
        return;
    }

    uiPrintf(5, "\x1b[31mRAM detection failed\x1b[0m");
    uiPrintf(6, "hoc:clk result : 0x%08X", g_hardwareReadRc);

    if (R_SUCCEEDED(g_hardwareDebugRc)) {
        uiPrintf(8,  "DEBUG - please photograph this screen");
        uiPrintf(9,  "HOC API : %u", g_hardwareDebug.apiVersion);
        uiPrintf(10, "Raw 400-405: %02X %02X %02X %02X %02X %02X",
                 g_hardwareDebug.raw400_411[0], g_hardwareDebug.raw400_411[1],
                 g_hardwareDebug.raw400_411[2], g_hardwareDebug.raw400_411[3],
                 g_hardwareDebug.raw400_411[4], g_hardwareDebug.raw400_411[5]);
        uiPrintf(11, "Raw 406-411: %02X %02X %02X %02X %02X %02X",
                 g_hardwareDebug.raw400_411[6], g_hardwareDebug.raw400_411[7],
                 g_hardwareDebug.raw400_411[8], g_hardwareDebug.raw400_411[9],
                 g_hardwareDebug.raw400_411[10], g_hardwareDebug.raw400_411[11]);
        uiPrintf(13, "console@408 : %d", g_hardwareDebug.consoleTypeAt408);
        uiPrintf(14, "ID@403:%u  8GB@404:%u  known:%s",
                 g_hardwareDebug.idAt403, g_hardwareDebug.is8At404,
                 g_hardwareDebug.id403Known ? "YES" : "NO");
        uiPrintf(15, "ID@404:%u  8GB@405:%u  known:%s",
                 g_hardwareDebug.idAt404, g_hardwareDebug.is8At405,
                 g_hardwareDebug.id404Known ? "YES" : "NO");
    } else {
        uiPrintf(8, "Debug read failed: 0x%08X", g_hardwareDebugRc);
    }

    uiPrintf(18, "A : Retry detection");
    uiPrintf(19, "B : Exit");
    printResetHint(19);
}


enum class BootInference { Unknown, RequestedActive, SaferActive };

BootInference inferBootState(int* activeValue = nullptr) {
    HocMonConfig c{};
    // After reboot, inspect the RUNNING Horizon OC config, not only config.ini.
    // If hoc:clk is unavailable (for example CFW No OC), the boot cannot be
    // counted as a successful normal-HOC boot.
    if (R_FAILED(hocmonGetConfig251(&c))) return BootInference::Unknown;

    if (g.stage == Stage::Preparation)
        return configMatchesCurrent(Config_Prepare, c) ? BootInference::RequestedActive : BootInference::Unknown;

    if (g.stage == Stage::LowUvQuick) {
        if (activeValue) *activeValue = c.lowUv;
        if (c.lowUv == g.lowUvTest) return BootInference::RequestedActive;
        if (c.lowUv < g.lowUvTest && c.lowUv <= g.lowUvGood) return BootInference::SaferActive;
        return BootInference::Unknown;
    }
    if (g.stage == Stage::LowVminQuick) {
        if (activeValue) *activeValue = c.lowVminMv;
        if (c.lowVminMv == g.lowVminTest) return BootInference::RequestedActive;
        if (c.lowVminMv > g.lowVminTest && c.lowVminMv >= g.lowVminGood) return BootInference::SaferActive;
        return BootInference::Unknown;
    }

    const u32 mask = g.pendingConfigMask ? g.pendingConfigMask : defaultConfigMaskForStage(g.stage);
    return mask != Config_None && configMatchesCurrent(mask, c)
        ? BootInference::RequestedActive : BootInference::Unknown;
}

void renderBootPrompt() {
    int active = 0;
    const BootInference state = inferBootState(&active);

    gui::ModalView m{};
    m.version = HOC_WIZARD_VERSION;
    m.eyebrow = "BOOT CHECK";

    if (state == BootInference::RequestedActive) {
        if (g.stage == Stage::LowUvQuick)
            m.title = "Did Low UV " + std::to_string(g.lowUvTest) + " boot normally?";
        else if (g.stage == Stage::LowVminQuick)
            m.title = "Did Low VMIN " + std::to_string(g.lowVminTest) + " mV boot normally?";
        else
            m.title = "Did normal CFW boot successfully?";

        m.body = {
            "Choose Yes only if normal CFW started successfully.",
            "No freeze.",
            "No crash.",
            "No unexpected reboot or system failure."
        };
        m.primaryAction = "Yes - boot was stable";
        m.tertiaryAction = "No - boot was unstable";
        m.secondaryAction = "Exit and decide later";
        m.tone = gui::ModalTone::Cyan;
    } else if (state == BootInference::SaferActive) {
        if (g_bootRecoveryCandidate < 0) g_bootRecoveryCandidate = active;

        if (g.stage == Stage::LowUvQuick) {
            m.title = "Low UV " + std::to_string(g.lowUvTest) + " did not boot";
            m.body = {
                "The console is currently running a safer value.",
                "Last known good value: Low UV " + std::to_string(g_bootRecoveryCandidate) + ".",
                "Use the last good value, or choose one safer value."
            };
        } else if (g.stage == Stage::LowVminQuick) {
            m.title = "Low VMIN " + std::to_string(g.lowVminTest) + " mV did not boot";
            m.body = {
                "The console is currently running a safer value.",
                "Last known good value: Low VMIN " + std::to_string(g_bootRecoveryCandidate) + " mV.",
                "Use the last good value, or choose one safer value."
            };
        } else {
            m.title = "The requested setting did not boot";
            m.body = {"The console is currently running a safer value."};
        }
        m.primaryAction = "Use last good value";
        m.tertiaryAction = "Try one safer value";
        m.secondaryAction = "Exit and decide later";
        m.tone = gui::ModalTone::Amber;
    } else {
        m.title = "Active value could not be confirmed";
        m.body = {
            "The Wizard could not verify the requested value in the running Horizon OC configuration.",
            "Check Horizon OC or the recovery state, then try again.",
            "If the boot was not stable, choose No to recover to the safer value."
        };
        m.primaryAction = "Check again";
        m.tertiaryAction = "No - treat as unstable";
        m.secondaryAction = "Exit and decide later";
        m.tone = gui::ModalTone::Red;
    }

    gui::presentModal(m);
}

void printSingleConfigCheck(int row, const char* label, const std::string& required,
                            const std::string& current, bool ok) {
    uiPrintf(row, "%s", label);
    uiPrintf(row + 1, "  Required : %s", required.c_str());
    uiPrintf(row + 2, "  Current  : %s", current.c_str());
    uiPrintf(row + 3, "  Status   : %s", ok ? "\x1b[32mOK\x1b[0m" : "\x1b[31mWRONG\x1b[0m");
}

std::string formatMv(int mv) { return std::to_string(mv) + " mV"; }

const char* cpuTableLabel(int table) {
    switch (table) {
        case 1: return "Default";
        case 2: return "1581 Tbreak";
        case 3: return "1683 Tbreak";
        case 4: return "Extreme UV";
        default: return "Unknown";
    }
}

void printCompactWrong(int& row, const char* label, const std::string& required, const std::string& current) {
    uiPrintf(row++, "%s", label);
    uiPrintf(row++, " Req:%s  Cur:%s  \x1b[31mWRONG\x1b[0m", required.c_str(), current.c_str());
}

void openConfigDebug() {
    g_configDebug = HocMonConfigDebug{};
    g_configDebugRc = hocmonGetConfigDebug(&g_configDebug);
    g_configDebugPage = 0;
    g_configDebugScreen = true;
}

void renderConfigDebug() {
    guiPageClear();
    uiPrintf(1, "\x1b[36mBattery Wizard - CONFIG DEBUG\x1b[0m");
    uiPrintf(2, "HOC : %s", g_configDebug.version[0] ? g_configDebug.version : "<unknown>");
    uiPrintf(3, "API : %u", g_configDebug.apiVersion);
    uiPrintf(4, "----------------------------------------");

    if (R_FAILED(g_configDebugRc)) {
        uiPrintf(7, "\x1b[31mRaw config read failed\x1b[0m");
        uiPrintf(8, "Result : 0x%08X", g_configDebugRc);
        uiPrintf(11, "B : Back");
        uiPresent();
        return;
    }

    constexpr int perPage = 24;
    constexpr int rows = 12;
    constexpr int pages = 4; // indexes 0..95 cover every Battery Wizard field
    const int base = g_configDebugPage * perPage;
    uiPrintf(5, "Raw GetConfigValues  Page %d / %d", g_configDebugPage + 1, pages);
    uiPrintf(6, " index:value               index:value");
    for (int r = 0; r < rows; ++r) {
        const int a = base + r;
        const int b = base + rows + r;
        uiPrintf(7 + r, " %3d:%-12llu       %3d:%llu",
                 a, (unsigned long long)g_configDebug.values[a],
                 b, (unsigned long long)g_configDebug.values[b]);
    }
    uiPrintf(21, "A : Next page    X : Previous page");
    uiPrintf(22, "B : Back to Preparation check");
    uiPresent();
}

void renderConfigPrompt() {
    guiPageClear();
    uiPrintf(1, "\x1b[31mBattery Wizard - SETTING NOT READY\x1b[0m");
    uiPrintf(2, "Step : %s", compactStepName(g.stage));
    uiPrintf(3, "----------------------------------------");
    if (!g_configCheck.readOk) {
        const int r = 5;
        uiPrintf(r, "Could not read Horizon OC config.ini");
        uiPrintf(r + 1, "Result : 0x%08X", g_configCheck.rc);
        uiPrintf(r + 4, "A : Check again");
        uiPrintf(r + 5, "B : Back");
        uiPresent();
        return;
    }

    if (g_configPromptSafetyOnly) {
        uiPrintf(5, "One or more active values no longer match the Wizard state.");
        uiPrintf(7, "Restore the red values shown on the right.");
        uiPrintf(9, "Only change the setting the Wizard currently asks you to change.");
        uiPrintf(12, "A : Check again");
        uiPrintf(13, "B : Back");
        uiPresent();
        return;
    }

    const u32 m = g_configCheck.mask;
    int row = 5;
    if (m & Config_Prepare) {
        uiPrintf(row++, "Fix these Preparation values:");
        row++;
        if (g_configCheck.current.uncappedClocks)
            printCompactWrong(row, "General - Uncapped Clocks", "OFF", "ON");
        if (g_configCheck.current.hpMode)
            printCompactWrong(row, "RAM - HP Mode", "OFF", "ON");
        if (g_configCheck.current.ramMaxKHz != 1600000U)
            printCompactWrong(row, "RAM - Max", "1600MHz", std::to_string(g_configCheck.current.ramMaxKHz / 1000U) + "MHz");
        if (g_configCheck.current.vdd2Uv != (u32)STOCK_VDD2_UV)
            printCompactWrong(row, "RAM - VDD2", formatVdd2(STOCK_VDD2_UV), formatVdd2((int)g_configCheck.current.vdd2Uv));
        if (g_configCheck.current.vddqUv != (u32)g.vddqStartMv * 1000U)
            printCompactWrong(row, "RAM - VDDQ", formatMv(g.vddqStartMv), formatMv((int)(g_configCheck.current.vddqUv / 1000U)));
        if (g_configCheck.current.cpuMaxKHz != 1963500U)
            printCompactWrong(row, "CPU - Max", "1963MHz", std::to_string(g_configCheck.current.cpuMaxKHz / 1000U) + "MHz");
        if (g_configCheck.current.lowVminMv != STOCK_LOW_VMIN_MV)
            printCompactWrong(row, "CPU - Low VMIN", formatMv(STOCK_LOW_VMIN_MV), formatMv(g_configCheck.current.lowVminMv));
        if (g_configCheck.current.highVminMv != STOCK_HIGH_VMIN_MV)
            printCompactWrong(row, "CPU - High VMIN", formatMv(STOCK_HIGH_VMIN_MV), formatMv(g_configCheck.current.highVminMv));
        if (g_configCheck.current.tableConf != 3)
            printCompactWrong(row, "CPU - UV Table", "1683 Tbreak", cpuTableLabel(g_configCheck.current.tableConf));
        if (g_configCheck.current.lowUv != STOCK_LOW_UV)
            printCompactWrong(row, "CPU - Low UV", "0", std::to_string(g_configCheck.current.lowUv));
        if (g_configCheck.current.highUv != STOCK_HIGH_UV)
            printCompactWrong(row, "CPU - High UV", "0", std::to_string(g_configCheck.current.highUv));
        if (g_configCheck.current.cpuBoostKHz != 1785000U)
            printCompactWrong(row, "HOC Toolkit - CPU Boost", "1785MHz", std::to_string(g_configCheck.current.cpuBoostKHz / 1000U) + "MHz");
    } else if (m & Config_LowUv) {
        printSingleConfigCheck(row, "CPU Low UV", std::to_string(targetLowUv()), std::to_string(g_configCheck.current.lowUv), g_configCheck.current.lowUv == targetLowUv());
        row += 5;
    } else if (m & Config_LowVmin) {
        printSingleConfigCheck(row, "CPU Low VMIN", formatMv(targetLowVmin()), formatMv(g_configCheck.current.lowVminMv), g_configCheck.current.lowVminMv == targetLowVmin());
        row += 5;
    } else if ((m & Config_Vddq) && (m & Config_Vdd2)) {
        printSingleConfigCheck(row, "RAM VDDQ", formatMv(targetVddqMv()), formatMv((int)(g_configCheck.current.vddqUv / 1000U)), g_configCheck.current.vddqUv == (u32)targetVddqMv() * 1000U);
        row += 5;
        printSingleConfigCheck(row, "RAM VDD2", formatVdd2(targetVdd2Uv()), formatVdd2((int)g_configCheck.current.vdd2Uv), g_configCheck.current.vdd2Uv == (u32)targetVdd2Uv());
        row += 5;
    } else if (m & Config_Vddq) {
        printSingleConfigCheck(row, "RAM VDDQ", formatMv(targetVddqMv()), formatMv((int)(g_configCheck.current.vddqUv / 1000U)), g_configCheck.current.vddqUv == (u32)targetVddqMv() * 1000U);
        row += 5;
    } else if (m & Config_Vdd2) {
        printSingleConfigCheck(row, "RAM VDD2", formatVdd2(targetVdd2Uv()), formatVdd2((int)g_configCheck.current.vdd2Uv), g_configCheck.current.vdd2Uv == (u32)targetVdd2Uv());
        row += 5;
    } else if (m & Config_HighUv) {
        printSingleConfigCheck(row, "CPU High UV", std::to_string(targetHighUv()), std::to_string(g_configCheck.current.highUv), g_configCheck.current.highUv == targetHighUv());
        row += 5;
    }
    uiPrintf(row + 1, "Fix \x1b[31mWRONG\x1b[0m values in Horizon OC.");
    uiPrintf(row + 3, "A : Check again");
    if (m & Config_Prepare)
        uiPrintf(row + 4, "Y : Set required values automatically");
    else if (m & (Config_LowUv | Config_LowVmin))
        uiPrintf(row + 4, "Y : Set required value automatically");
    if (g.stage == Stage::Preparation) {
        uiPrintf(row + 5, "X : Use my current settings as baseline");
        uiPrintf(row + 6, "B : Back");
    } else {
        uiPrintf(row + 5, "B : Back");
    }
    uiPresent();
}

void renderAutoPrepConfirm() {
    guiPageClear();
    uiPrintf(1, "\x1b[36mBattery Wizard\x1b[0m");
    uiPrintf(2, "Step : Automatic Setting");
    uiPrintf(3, "----------------------------------------");
    if (g_autoSetMask & Config_Prepare)
        uiPrintf(5, "Set all required Preparation values?");
    else if (g_autoSetMask & Config_LowUv)
        uiPrintf(5, "Set CPU Low UV %d automatically?", targetLowUv());
    else if (g_autoSetMask & Config_LowVmin)
        uiPrintf(5, "Set CPU Low VMIN %d mV automatically?", targetLowVmin());
    uiPrintf(7, "Other Horizon OC values stay unchanged.");
    uiPrintf(9, "Horizon OC 2.5.1 is required.");
    if (!g_autoPrepError.empty())
        uiPrintf(12, "\x1b[31m%s\x1b[0m", g_autoPrepError.c_str());
    if (g_autoSetMask & Config_Prepare)
        uiPrintf(16, "A : Confirm - set values");
    else
        uiPrintf(16, "A : Confirm - set value");
    uiPrintf(17, "B : Cancel");
    uiPresent();
}

void renderRebootConfirm() {
    guiPageClear();
    uiPrintf(1, "\x1b[36mBattery Wizard\x1b[0m");
    uiPrintf(2, "Step : %s", compactStepName(g.stage));
    uiPrintf(3, "----------------------------------------");
    const u32 m = g_configCheck.mask;
    if (m & Config_Prepare)
        uiPrintf(5, "\x1b[32mPreparation values saved and verified.\x1b[0m");
    else if (m & Config_LowUv)
        uiPrintf(5, "\x1b[32mLow UV %d saved and verified.\x1b[0m", targetLowUv());
    else if (m & Config_LowVmin)
        uiPrintf(5, "\x1b[32mLow VMIN %d mV saved and verified.\x1b[0m", targetLowVmin());
    else
        uiPrintf(5, "\x1b[32mRequested setting saved and verified.\x1b[0m");

    uiPrintf(7, "Reboot is required to apply settings.");
    uiPrintf(8, "After normal CFW boots, open Wizard again.");
    uiPrintf(10, "\x1b[31mIf normal CFW does not boot,\x1b[0m");
    uiPrintf(11, "\x1b[31mfreezes or crashes:\x1b[0m");
    uiPrintf(13, "1. Boot Hekate.");
    uiPrintf(14, "2. Start CFW No OC.");
    uiPrintf(15, "3. Restore the previous safe value.");
    uiPrintf(16, "4. Reboot normal CFW.");
    uiPrintf(17, "5. Open this Wizard again.");
    uiPrintf(20, "A : Reboot now");
    uiPrintf(21, "B : Back");
    uiPresent();
}

void renderPreparation() {
    title();
    uiPrintf(5, "Before tuning starts, the Wizard needs a known baseline.");
    uiPrintf(7, "You can set the recommended values manually, use your current settings as the baseline, or let the Wizard apply the recommended values automatically.");

    uiPrintf(18, "A : Check settings");
    uiPrintf(19, "X : Use my current settings as baseline");
    uiPrintf(20, "Y : Set recommended values automatically + reboot");
    uiPrintf(21, "B : Exit");
    printResetHint(21);
}




bool isVminSweepStage(Stage st);

void renderValidationObjective(int& row) {
    switch (g.stage) {
        case Stage::VddqQuick:
            uiPrintf(row++, "This 1-minute test checks the current VDDQ candidate.");
            uiPrintf(row++, "Candidate : %d mV", g.vddqTest); break;
        case Stage::VddqLong:
            uiPrintf(row++, "This test validates the final VDDQ value.");
            uiPrintf(row++, "VDDQ : %d mV", g.vddqGood); break;
        case Stage::Vdd2Quick:
            uiPrintf(row++, "This 1-minute test checks the current VDD2 candidate.");
            uiPrintf(row++, "Candidate : %s", formatVdd2(g.vdd2TestUv).c_str()); break;
        case Stage::Vdd2Long:
            uiPrintf(row++, "This test validates the final RAM voltage pair.");
            uiPrintf(row++, "VDDQ : %d mV", g.vddqGood);
            uiPrintf(row++, "VDD2 : %s", formatVdd2(g.vdd2GoodUv).c_str()); break;
        case Stage::RamBoostValidate:
            uiPrintf(row++, "This test validates tuned RAM at Nintendo Boost clocks.");
            uiPrintf(row++, "VDDQ : %d mV", g.vddqGood);
            uiPrintf(row++, "VDD2 : %s", formatVdd2(g.vdd2GoodUv).c_str()); break;
        case Stage::Ram1331Validate:
            uiPrintf(row++, "This test validates tuned RAM at handheld clocks.");
            uiPrintf(row++, "VDDQ : %d mV", g.vddqGood);
            uiPrintf(row++, "VDD2 : %s", formatVdd2(g.vdd2GoodUv).c_str()); break;
        case Stage::HighUvQuick:
            uiPrintf(row++, "This 1-minute test checks the current High UV candidate.");
            uiPrintf(row++, "Candidate : %d", g.highUvTest); break;
        case Stage::HighUvLong:
            uiPrintf(row++, "This test validates the final High UV value.");
            uiPrintf(row++, "High UV : %d", g.highUvGood); break;
        case Stage::BoostCpuRamValidate:
            uiPrintf(row++, "This test validates High UV at Nintendo Boost clocks.");
            uiPrintf(row++, "CPU / GPU / RAM : 1785 / 76.8 / 1600 MHz"); break;
        case Stage::NormalMatrixValidate:
            uiPrintf(row++, "This test validates CPU + RAM at handheld clocks.");
            uiPrintf(row++, "CPU / GPU / RAM : 1020 / 384 / 1331 MHz"); break;
        case Stage::BoostCpuMemValidate:
            uiPrintf(row++, "This test validates High UV together with tuned RAM.");
            uiPrintf(row++, "CPU / GPU / RAM : 1785 / 76.8 / 1600 MHz"); break;
        case Stage::NormalMemValidate: uiPrintf(row++, "This test validates RAM at handheld clocks."); break;
        case Stage::NormalGpuValidate: uiPrintf(row++, "This test validates GPU stability at handheld clocks."); break;
        case Stage::BoostMatrixValidate: uiPrintf(row++, "This test validates CPU stability at Boost clocks."); break;
        case Stage::BoostMemValidate: uiPrintf(row++, "This test validates RAM stability at Boost clocks."); break;
        case Stage::LowVminFinalLong:
            uiPrintf(row++, "This test validates the final Low VMIN value.");
            uiPrintf(row++, "Low VMIN : %d mV", g.lowVminGood); break;
        default: uiPrintf(row++, "This test validates the current tuned settings."); break;
    }
    row++;
}

void renderTestStage() {
    title();

    if (g.limitNoticePending) {
        uiPrintf(5, "\x1b[33mWizard search limit reached.\x1b[0m");
        switch (g.stage) {
            case Stage::LowUvQuick:
                uiPrintf(7, "Current Low UV : %d", g.lowUvGood);
                uiPrintf(8, "Wizard maximum : %d", LOW_UV_MAX);
                uiPrintf(10, "No higher Low UV level will be tested.");
                uiPrintf(13, "A : Confirm Low UV %d and continue", g.lowUvGood);
                break;
            case Stage::LowVminQuick:
                uiPrintf(7, "Current Low VMIN : %d mV", g.lowVminGood);
                uiPrintf(8, "Wizard minimum   : %d mV", LOW_VMIN_MIN_MV);
                uiPrintf(10, "Going lower is not recommended.");
                uiPrintf(11, "Very low VMIN values may cause");
                uiPrintf(12, "Sleep / Standby / Wake problems.");
                uiPrintf(14, "No lower value will be tested.");
                uiPrintf(17, "A : Confirm %d mV and continue", g.lowVminGood);
                break;
            case Stage::VddqQuick:
                uiPrintf(7, "Current VDDQ    : %d mV", g.vddqGood);
                uiPrintf(8, "Wizard minimum  : %d mV", VDDQ_MIN_MV);
                uiPrintf(10, "The Wizard will not search below");
                uiPrintf(11, "%d mV VDDQ.", VDDQ_MIN_MV);
                uiPrintf(13, "No lower value will be tested.");
                uiPrintf(16, "A : Confirm %d mV and continue", g.vddqGood);
                break;
            case Stage::Vdd2Quick:
                uiPrintf(7, "Current VDD2   : %s", formatVdd2(g.vdd2GoodUv).c_str());
                uiPrintf(8, "Wizard minimum : %s", formatVdd2(VDD2_MIN_UV).c_str());
                uiPrintf(10, "The Wizard will not search below");
                uiPrintf(11, "%s VDD2.", formatVdd2(VDD2_MIN_UV).c_str());
                uiPrintf(13, "No lower value will be tested.");
                uiPrintf(16, "A : Confirm %s and continue", formatVdd2(g.vdd2GoodUv).c_str());
                break;
            case Stage::HighUvQuick:
                uiPrintf(7, "Current High UV : %d", g.highUvGood);
                uiPrintf(8, "Wizard maximum  : %d", HIGH_UV_MAX);
                uiPrintf(10, "No higher High UV level will be tested.");
                uiPrintf(13, "A : Confirm High UV %d and continue", g.highUvGood);
                break;
            default:
                uiPrintf(7, "The configured Wizard limit was reached.");
                uiPrintf(10, "A : Confirm and continue");
                break;
        }
        uiPrintf(19, "B : Exit");
        printResetHint(19);
        return;
    }

    const u32 configMask = activeConfigMask();
    if (configMask != Config_None) {
        int row = 5;
        uiPrintf(row++, "Objective:");
        if (g.stage == Stage::LowUvQuick) {
            uiPrintf(row++, "Find the highest Low UV that can");
            uiPrintf(row++, "boot normally.");
        } else if (g.stage == Stage::LowVminQuick) {
            uiPrintf(row++, "Find the lowest Low VMIN that can");
            uiPrintf(row++, "boot normally.");
        } else if (g.stage == Stage::VddqQuick) {
            uiPrintf(row++, "Find the lowest VDDQ that remains");
            uiPrintf(row++, "stable.");
        } else if (g.stage == Stage::Vdd2Quick) {
            uiPrintf(row++, "Find the lowest VDD2 that remains");
            uiPrintf(row++, "stable.");
        } else if (g.stage == Stage::HighUvQuick) {
            uiPrintf(row++, "Find the highest High UV that remains");
            uiPrintf(row++, "stable.");
        } else {
            uiPrintf(row++, "Apply the required value before");
            uiPrintf(row++, "continuing.");
        }
        // The requested value is shown once in the right-side Current Instruction box.
        row += 2;
        uiPrintf(row++, "A : Check setting");
        if (configMask & (Config_LowUv | Config_LowVmin))
            uiPrintf(row++, "Y : Set value automatically");
        const bool stepDownSearch = g.stage == Stage::LowVminQuick || g.stage == Stage::VddqQuick || g.stage == Stage::Vdd2Quick;
        if (stepDownSearch) {
            uiPrintf(row++, "+ : Known stable / Lower to next value");
            uiPrintf(row++, "X : Known unstable / Raise to last good value");
        } else {
            uiPrintf(row++, "+ : Known stable / Continue to next value");
            uiPrintf(row++, "X : Known unstable / Lower to last good value");
        }
        uiPrintf(row++, "B : Exit");
        printResetHint(row - 1);
        return;
    }

    int row = 5;
    if (g.recoveryNeeded) g.recoveryNeeded = false;

    if (g.stage == Stage::LowUvLong || g.stage == Stage::LowVminLong) {
        const bool lowUv = g.stage == Stage::LowUvLong;
        uiPrintf(row++, "\x1b[32mBoot-limit candidate found.\x1b[0m");
        uiPrintf(row++, lowUv ? "CPU Low UV   : %d" : "CPU Low VMIN : %d mV",
                 lowUv ? g.lowUvGood : g.lowVminGood);
        row++;
        uiPrintf(row++, "Next, Wizard maps CPU voltage at:");
        uiPrintf(row++, "510 / 612 / 714 / 816 / 918 / 1020 MHz");
        uiPrintf(row++, "It keeps highest frequency from each");
        uiPrintf(row++, "different voltage region for testing.");
        row += 2;
        uiPrintf(row++, "A : Scan voltage regions automatically");
        uiPrintf(row++, "B : Exit");
        printResetHint(row - 1);
        return;
    }

    if (g.stage == Stage::LowUvValidateQuick || g.stage == Stage::LowVminPlateauValidate) {
        uiPrintf(row++, "Voltage regions to validate : %d", g.vminValidateCount);
        row++;
        for (int i = 0; i < g.vminValidateCount && i < 6; ++i)
            uiPrintf(row++, "%d. %s @ ~%d mV", i + 1,
                     formatClock(g.vminValidateHz[i]).c_str(), g.vminValidateMv[i]);
        row++;
        uiPrintf(row++, "Each region will be tested for 1 minute.");
        row++;
        uiPrintf(row++, "A : Start validation test");
        uiPrintf(row++, "+ : Known PASS / Skip validation test");
        uiPrintf(row++, "B : Exit");
        printResetHint(row - 1);
        return;
    }

    stress::Kind kind;
    int seconds = 0;
    const bool hasTest = testPlan(g.stage, kind, seconds);
    if (hasTest) {
        renderValidationObjective(row);
        const bool candidateTest = g.stage == Stage::VddqQuick ||
                                   g.stage == Stage::Vdd2Quick ||
                                   g.stage == Stage::HighUvQuick;
        uiPrintf(row++, candidateTest ? "Stability test : %s" : "Validation test : %s",
                 seconds == 60 ? "1 minute" : (seconds == 1800 ? "30 minutes" : "1 hour"));
        uiPrintf(row++, "Test type : %s", compactTestName(kind));
        footerTest(row + 1);
    }
}


void renderRealWorld() {
    title();
    if (!g_realWorldHelpPage) {
        uiPrintf(5, "For final confirmation, play The Legend of Zelda: Tears of the Kingdom.");
        uiPrintf(7, "Play for at least 1 hour.");
        uiPrintf(9, "During the check:");
        uiPrintf(10, "• Normal gameplay");
        uiPrintf(11, "• Battles and fast travel");
        uiPrintf(12, "• Loading screens");
        uiPrintf(13, "• Sleep / Wake");
        uiPrintf(15, "Watch for crashes, freezes or unexpected reboots.");
        uiPrintf(19, "A : If instability occurs");
        uiPrintf(20, "+ : Stable / Continue to results");
        uiPrintf(21, "B : Exit");
        printResetHint(21);
        return;
    }

    uiPrintf(5, "Change only ONE setting at a time. Change it by one step, then play again.");
    uiPrintf(7, "Recommended order:");
    uiPrintf(9, "1. Low VMIN - raise voltage one step");
    uiPrintf(10, "2. VDDQ - raise voltage one step");
    uiPrintf(11, "3. VDD2 - raise voltage one step");
    uiPrintf(12, "4. CPU High UV - one step less aggressive");
    uiPrintf(13, "5. CPU Low UV - one step less aggressive");
    uiPrintf(15, "If it still fails, restore that setting to its previous value before trying the next one.");
    uiPrintf(17, "Never change multiple settings at the same time.");
    uiPrintf(20, "A : Continue to results");
    uiPrintf(21, "B : Back");
    printResetHint(21);
}

void renderComplete() {
    title();
    uiPrintf(5, "\x1b[32mUNDERVOLTING COMPLETE\x1b[0m");
    uiPrintf(7, "Final values:");
    uiPrintf(8, "CPU Low UV : %d", g.lowUvGood);
    uiPrintf(9, "CPU Low VMIN : %d mV", g.lowVminGood);
    uiPrintf(10, "RAM VDDQ : %d mV", g.vddqGood);
    uiPrintf(11, "RAM VDD2 : %s", formatVdd2(g.vdd2GoodUv).c_str());
    uiPrintf(12, "CPU High UV : %d", g.highUvGood);
    uiPrintf(14, "Saved to Performance Modes · Battery Mode");
    uiPrintf(17, "B : Exit");
    printResetHint(17);
}

void renderInterruptedPrompt() {
    guiPageClear();
    uiPrintf(1, "\x1b[1;33mInterrupted Test\x1b[0m");
    uiPrintf(2, "------------------------------------------------");
    uiPrintf(4, "The previous built-in test was marked RUNNING");
    uiPrintf(5, "but never finished.");
    uiPrintf(7, "Stage: %s", stageName(static_cast<Stage>(g.testStage)));
    uiPrintf(8, "Test : %s", stress::kindName(static_cast<stress::Kind>(g.testKind)));
    uiPrintf(9, "Time : %s", g.testDurationSec == 60 ? "1 minute" : (g.testDurationSec == 1800 ? "30 minutes" : "1 hour"));
    uiPrintf(11, "Did the console freeze, crash or reboot?");
    uiPrintf(14, "A : YES - count as FAIL");
    uiPrintf(15, "X : NO - interrupted manually; run again");
    uiPrintf(16, "B : Exit and decide later");
    uiPresent();
}

void renderOverridePrompt() {
    guiPageClear();
    uiPrintf(1, "\x1b[31mBattery Wizard - TEST SETUP FAILED\x1b[0m");
    uiPrintf(2, "Step : %s", compactStepName(g.stage));
    uiPrintf(3, "----------------------------------------");

    uiPrintf(5, "Could not automatically set or verify");
    uiPrintf(6, "the required test clocks.");

    if (!g_overrideCheck.readOk) {
        uiPrintf(8, "Horizon OC clock read failed.");
        if (g_overrideCheck.rc)
            uiPrintf(9, "Result : 0x%08X", g_overrideCheck.rc);
    } else {
        uiPrintf(8, "Required test clocks:");
        uiPrintf(9,  " CPU : %s", formatClock(g_overrideCheck.expected.cpuHz).c_str());
        uiPrintf(10, " GPU : %s", formatClock(g_overrideCheck.expected.gpuHz).c_str());
        uiPrintf(11, " RAM : %s", formatClock(g_overrideCheck.expected.ramHz).c_str());
        uiPrintf(13, "Current Temporary Overrides:");
        uiPrintf(14, " CPU : %s", formatClock(g_overrideCheck.current.overrideHz[0]).c_str());
        uiPrintf(15, " GPU : %s", formatClock(g_overrideCheck.current.overrideHz[1]).c_str());
        uiPrintf(16, " RAM : %s", formatClock(g_overrideCheck.current.overrideHz[2]).c_str());
    }

    uiPrintf(19, "A : Try automatic setup again");
    uiPrintf(20, "B : Back");
    uiPresent();
}

void renderResultScreen() {
    guiPageClear();
    uiPrintf(1, "\x1b[1;96mBuilt-in %s\x1b[0m", stress::kindName(g_lastKind));
    uiPrintf(2, "------------------------------------------------");
    if (g_lastResult.outcome == stress::Outcome::Pass)
        uiPrintf(4, "\x1b[32mPASS\x1b[0m");
    else if (g_lastResult.outcome == stress::Outcome::Fail)
        uiPrintf(4, "\x1b[31mFAIL\x1b[0m");
    else if (g_lastResult.outcome == stress::Outcome::Cancelled)
        uiPrintf(4, "\x1b[33mCANCELLED\x1b[0m");
    else
        uiPrintf(4, "\x1b[31mTEST ENGINE ERROR\x1b[0m");
    uiPrintf(6, "Elapsed    : %llu ms", (unsigned long long)g_lastResult.elapsedMs);
    uiPrintf(7, "Iterations : %llu", (unsigned long long)g_lastResult.iterations);
    uiPrintf(8, "Errors     : %llu", (unsigned long long)g_lastResult.errors);
    uiPrintf(9, "Mismatches : %llu", (unsigned long long)g_lastResult.mismatches);
    if (!g_lastResult.detail.empty()) uiPrintf(11, "%s", g_lastResult.detail.c_str());
    if (!g_resultAction.empty()) uiPrintf(13, "%s", g_resultAction.c_str());
    uiPrintf(17, "A : Continue");
    uiPresent();
}

std::string rebootSavedValueText() {
    const u32 mask = g_configCheck.mask;
    if (mask & Config_Prepare) return "Preparation values were saved successfully.";
    if (mask & Config_LowUv) return "Low UV " + std::to_string(targetLowUv()) + " was saved successfully.";
    if (mask & Config_LowVmin) return "Low VMIN " + std::to_string(targetLowVmin()) + " mV was saved successfully.";
    if ((mask & Config_Vddq) && (mask & Config_Vdd2)) return "VDDQ and VDD2 were saved successfully.";
    if (mask & Config_Vddq) return "VDDQ " + std::to_string(targetVddqMv()) + " mV was saved successfully.";
    if (mask & Config_Vdd2) return "VDD2 " + formatVdd2(targetVdd2Uv()) + " was saved successfully.";
    if (mask & Config_HighUv) return "High UV " + std::to_string(targetHighUv()) + " was saved successfully.";
    return "The requested value was saved successfully.";
}

void renderRebootModal() {
    gui::ModalView m{};
    m.version = HOC_WIZARD_VERSION;
    m.eyebrow = "REBOOT REQUIRED";
    m.title = "Apply the new setting";
    m.body = {
        rebootSavedValueText(),
        "A reboot is required to apply this setting.",
        "After normal CFW has booted, open HOC Undervolting Wizard again to continue.",
        "If normal CFW does not boot, freezes or crashes:",
        "Boot CFW No OC, restore the previous known-good value, reboot normal CFW and open the Wizard again."
    };
    m.primaryAction = "Reboot now";
    m.secondaryAction = "Back";
    m.tone = gui::ModalTone::Amber;
    gui::presentModal(m);
}

void render() {
    guiPageClear();
    if (g_bootPrompt) { renderBootPrompt(); return; }
    if (g_vminScanScreen) { renderVminScanScreen(); return; }
    if (g_interruptedPrompt) { renderInterruptedPrompt(); return; }
    if (g_configDebugScreen) { renderConfigDebug(); return; }
    if (g_configPrompt) { renderConfigPrompt(); return; }
    if (g_autoPrepConfirm) { renderAutoPrepConfirm(); return; }
    if (g_rebootConfirm) { renderRebootModal(); return; }
    if (g_overridePrompt) { renderOverridePrompt(); return; }
    if (g_resultScreen) { renderResultScreen(); return; }
    if (g_resetConfirm) {
        uiPrintf(1, "\x1b[1;31mReset ALL wizard progress?\x1b[0m");
        uiPrintf(4, "A : Yes, reset");
        uiPrintf(5, "B : Cancel");
        uiPresent();
        return;
    }

    if (g.stage == Stage::HardwareDetection) renderHardwareDetection();
    else if (g.stage == Stage::Preparation) renderPreparation();
    else if (g.stage == Stage::RealWorldValidate) renderRealWorld();
    else if (g.stage == Stage::Complete) renderComplete();
    else renderTestStage();
    uiPresent();
}


bool isVminSweepStage(Stage st) {
    return st == Stage::LowVminLong || st == Stage::LowVminSweep612 ||
           st == Stage::LowVminSweep714 || st == Stage::LowVminValidate816 ||
           st == Stage::LowVminSweep918 || st == Stage::LowVminValidate1020;
}

u32 vminSweepClock(Stage st) {
    switch (st) {
        case Stage::LowVminLong: return CLOCK_CPU_VMIN_510_HZ;
        case Stage::LowVminSweep612: return CLOCK_CPU_LOW_HZ;
        case Stage::LowVminSweep714: return CLOCK_CPU_VMIN_714_HZ;
        case Stage::LowVminValidate816: return CLOCK_CPU_VMIN_MID_HZ;
        case Stage::LowVminSweep918: return CLOCK_CPU_VMIN_918_HZ;
        case Stage::LowVminValidate1020: return CLOCK_CPU_NORMAL_HZ;
        default: return 0;
    }
}

void recordVminObservation(Stage st) {
    if (!isVminSweepStage(st) || !g_overrideCheck.readOk) return;
    const int idx = vminSweepIndex(st);
    const u32 hz = vminSweepClock(st);
    const u32 uv = g_overrideCheck.current.cpuVoltageUv;
    if (idx < 0 || !hz || !uv) return;

    // HOC/PMIC steps are 5 mV: group readings into the actual voltage regions.
    const int mv = (int)(((uv + 2500U) / 5000U) * 5U);
    g.vminObsMv[idx] = mv;
    g.vminObsMask |= (1u << idx);
    g.lastProbeHz = hz;
    g.lastProbeMv = mv;

    const int delta = std::abs(mv - g.lowVminGood);
    if (delta <= 5) {
        g.vminFloorHz = hz;
        g.vminFloorObservedMv = mv;
    }
    saveState();
}


void restartVminSweep(bool recovery) {
    const u32 keepMask = g.pendingConfigMask;
    g.stage = Stage::LowVminLong;
    g.recoveryNeeded = recovery;
    clearVminSweepData();
    g.pendingConfigMask = keepMask;
    saveState();
}

void enterLowVminSearchOrMinimumNotice() {
    clearVminSweepData();
    g.pendingConfigMask = Config_None;
    g.limitNoticePending = false;
    if (g.lowVminGood <= LOW_VMIN_MIN_MV) {
        g.stage = Stage::LowVminQuick;
        g.lowVminTest = g.lowVminGood;
        g.stageReadyAfterBoot = true;
        g.limitNoticePending = true;
    } else {
        g.stage = Stage::LowVminQuick;
        g.lowVminTest = std::max(LOW_VMIN_MIN_MV, g.lowVminGood - LOW_VMIN_STEP_MV);
        g.stageReadyAfterBoot = false;
    }
}

void enterVddqSearchOrMinimumNotice() {
    g.pendingConfigMask = Config_None;
    g.limitNoticePending = false;
    g.stage = Stage::VddqQuick;
    if (g.vddqGood <= VDDQ_MIN_MV) {
        g.vddqTest = g.vddqGood;
        g.stageReadyAfterBoot = true;
        g.limitNoticePending = true;
    } else {
        g.vddqTest = g.vddqGood - VDDQ_STEP_MV;
        g.stageReadyAfterBoot = false;
    }
}

void enterVdd2SearchOrMinimumNotice() {
    g.pendingConfigMask = Config_None;
    g.limitNoticePending = false;
    g.stage = Stage::Vdd2Quick;
    if (g.vdd2GoodUv <= VDD2_MIN_UV) {
        g.vdd2TestUv = g.vdd2GoodUv;
        g.stageReadyAfterBoot = true;
        g.limitNoticePending = true;
    } else {
        g.vdd2TestUv = g.vdd2GoodUv - VDD2_STEP_UV;
        g.stageReadyAfterBoot = false;
    }
}

void enterHighUvSearchOrMaximumNotice() {
    g.pendingConfigMask = Config_None;
    g.limitNoticePending = false;
    g.stage = Stage::HighUvQuick;
    if (g.highUvGood >= HIGH_UV_MAX) {
        g.highUvTest = g.highUvGood;
        g.stageReadyAfterBoot = true;
        g.limitNoticePending = true;
    } else {
        g.highUvTest = g.highUvGood + 1;
        g.stageReadyAfterBoot = false;
    }
}

void confirmWizardLimitAndContinue() {
    g.limitNoticePending = false;
    g.pendingConfigMask = Config_None;
    switch (g.stage) {
        case Stage::LowUvQuick:
            g.stage = Stage::LowUvLong;
            g.stageReadyAfterBoot = true;
            break;
        case Stage::LowVminQuick:
            restartVminSweep(false);
            g.stageReadyAfterBoot = true;
            g.pendingConfigMask = Config_None;
            break;
        case Stage::VddqQuick:
            g.stage = Stage::VddqLong;
            g.stageReadyAfterBoot = true;
            break;
        case Stage::Vdd2Quick:
            g.ramPairRetryMode = 0;
            g.stage = Stage::Vdd2Long;
            g.stageReadyAfterBoot = true;
            break;
        case Stage::HighUvQuick:
            g.stage = Stage::BoostCpuRamValidate;
            g.stageReadyAfterBoot = true;
            break;
        default:
            break;
    }
    saveState();
}


void handlePass() {
    switch (g.stage) {
        case Stage::HardwareDetection:
            g.stage = Stage::Preparation;
            g.stageReadyAfterBoot = false;
            break;
        case Stage::Preparation:
            g.stage = Stage::LowUvQuick;
            g.stageReadyAfterBoot = false;
            break;
        case Stage::LowUvQuick:
            // Boot-stable candidate confirmed by the post-reboot check.
            g.lowUvGood = g.lowUvTest;
            if (g.lowUvTest >= LOW_UV_MAX) {
                g.stageReadyAfterBoot = true;
                g.limitNoticePending = true;
            } else {
                ++g.lowUvTest;
                g.stageReadyAfterBoot = false;
                g.limitNoticePending = false;
            }
            break;
        case Stage::LowUvValidateQuick:
            g.stage = Stage::LowUvLong;
            g.stageReadyAfterBoot = true;
            break;
        case Stage::LowUvLong:
            g.recoveryNeeded = false;
            enterLowVminSearchOrMinimumNotice();
            break;
        case Stage::LowVminQuick:
            g.lowVminGood = g.lowVminTest;
            if (g.lowVminTest <= LOW_VMIN_MIN_MV) {
                g.stageReadyAfterBoot = true;
                g.limitNoticePending = true;
            } else {
                g.lowVminTest -= LOW_VMIN_STEP_MV;
                g.stageReadyAfterBoot = false;
                g.limitNoticePending = false;
            }
            break;
        case Stage::LowVminLong: g.stage = Stage::LowVminSweep612; break;
        case Stage::LowVminSweep612: g.stage = Stage::LowVminSweep714; break;
        case Stage::LowVminSweep714: g.stage = Stage::LowVminValidate816; break;
        case Stage::LowVminValidate816: g.stage = Stage::LowVminSweep918; break;
        case Stage::LowVminSweep918: g.stage = Stage::LowVminValidate1020; break;
        case Stage::LowVminValidate1020:
            buildVminPlateaus();
            g.stage = Stage::LowVminPlateauValidate;
            g.stageReadyAfterBoot = true;
            break;
        case Stage::LowVminFinalLong:
            // Legacy state compatibility: move into the new plateau workflow.
            buildVminPlateaus();
            g.stage = Stage::LowVminPlateauValidate;
            g.stageReadyAfterBoot = true;
            break;
        case Stage::LowVminPlateauValidate:
            ++g.vminValidateIndex;
            if (g.vminValidateIndex >= g.vminValidateCount) {
                enterVddqSearchOrMinimumNotice();
            }
            break;
        case Stage::VddqQuick:
            g.vddqGood = g.vddqTest;
            if (g.vddqTest <= VDDQ_MIN_MV) {
                g.stageReadyAfterBoot = true;
                g.limitNoticePending = true;
            } else {
                g.vddqTest -= VDDQ_STEP_MV;
                g.stageReadyAfterBoot = false;
                g.limitNoticePending = false;
            }
            break;
        case Stage::VddqLong:
            g.recoveryNeeded = false;
            enterVdd2SearchOrMinimumNotice();
            break;
        case Stage::Vdd2Quick:
            g.vdd2GoodUv = g.vdd2TestUv;
            if (g.vdd2TestUv <= VDD2_MIN_UV) {
                g.stageReadyAfterBoot = true;
                g.limitNoticePending = true;
            } else {
                g.vdd2TestUv -= VDD2_STEP_UV;
                g.stageReadyAfterBoot = false;
                g.limitNoticePending = false;
            }
            break;
        case Stage::Vdd2Long:
            g.recoveryNeeded = false;
            g.ramPairRetryMode = 0;
            g.stage = Stage::NormalMatrixValidate;
            break;
        case Stage::RamBoostValidate:
        case Stage::Ram1331Validate:
            // Legacy beta states now continue with the Part-1 critical low anchor.
            g.ramPairRetryMode = 0;
            g.stage = Stage::NormalMatrixValidate;
            break;
        case Stage::HighUvQuick:
            g.highUvGood = g.highUvTest;
            if (g.highUvTest >= HIGH_UV_MAX) {
                g.stageReadyAfterBoot = true;
                g.limitNoticePending = true;
            } else {
                ++g.highUvTest;
                g.stageReadyAfterBoot = false;
                g.limitNoticePending = false;
            }
            break;
        case Stage::HighUvLong:
            // Legacy beta state: the Boost CPU-memtester now replaces this
            // standalone High UV one-hour CPU test.
            g.recoveryNeeded = false;
            g.stage = Stage::BoostCpuRamValidate;
            break;
        case Stage::NormalMatrixValidate:
            enterHighUvSearchOrMaximumNotice();
            break;
        case Stage::BoostCpuRamValidate: g.stage = Stage::BoostCpuMemValidate; break;
        case Stage::NormalMemValidate:
        case Stage::NormalGpuValidate:
        case Stage::BoostMatrixValidate:
        case Stage::BoostMemValidate:
        case Stage::BoostCpuMemValidate:
            // Legacy beta states: these tests are redundant in beta39+.
            g.stage = Stage::RealWorldValidate;
            break;
        case Stage::RealWorldValidate:
            g_realWorldHelpPage = false;
            g.stage = Stage::Complete;
            writeResults();
            break;
        case Stage::Complete: break;
    }
    g.pendingConfigMask = Config_None;
    saveState();
}


void handleFail(bool didNotBoot) {
    g.stageReadyAfterBoot = false;
    g.limitNoticePending = false;
    switch (g.stage) {
        case Stage::Preparation:
            g.recoveryNeeded = didNotBoot;
            break;
        case Stage::LowUvQuick:
            // Candidate failed either to boot or to pass its 1-minute test.
            // Restore the previous last-known-good value, reboot, then run
            // the 1-hour validation on that recovered value.
            g.stage = Stage::LowUvLong;
            g.recoveryNeeded = didNotBoot;
            g.pendingConfigMask = Config_LowUv;
            break;
        case Stage::LowUvValidateQuick:
            if (g.lowUvGood > 0) --g.lowUvGood;
            g.stage = Stage::LowUvLong;
            g.recoveryNeeded = false;
            g.pendingConfigMask = Config_LowUv;
            break;
        case Stage::LowUvLong:
            if (g.lowUvGood > 0) --g.lowUvGood;
            g.pendingConfigMask = Config_LowUv;
            break;
        case Stage::LowVminQuick:
            // Restore the last passing VMIN before the full voltage scan.
            restartVminSweep(didNotBoot);
            g.pendingConfigMask = Config_LowVmin;
            return;
        case Stage::LowVminLong:
        case Stage::LowVminSweep612:
        case Stage::LowVminSweep714:
        case Stage::LowVminValidate816:
        case Stage::LowVminSweep918:
        case Stage::LowVminValidate1020:
            restartVminSweep(false);
            break;
        case Stage::LowVminFinalLong:
            restartVminSweep(false);
            break;
        case Stage::LowVminPlateauValidate:
            if (g.lowVminGood < STOCK_LOW_VMIN_MV)
                g.lowVminGood = std::min(STOCK_LOW_VMIN_MV, g.lowVminGood + LOW_VMIN_STEP_MV);
            g.stage = Stage::LowVminLong;
            g.pendingConfigMask = Config_LowVmin;
            clearVminSweepData();
            break;
        case Stage::VddqQuick:
            g.stage = Stage::VddqLong;
            g.recoveryNeeded = didNotBoot;
            g.pendingConfigMask = Config_Vddq;
            break;
        case Stage::VddqLong:
            g.vddqGood += VDDQ_STEP_MV;
            g.pendingConfigMask = Config_Vddq;
            break;
        case Stage::Vdd2Quick:
            g.stage = Stage::Vdd2Long;
            g.recoveryNeeded = didNotBoot;
            g.ramPairRetryMode = 0;
            g.pendingConfigMask = Config_Vdd2;
            break;
        case Stage::Vdd2Long:
        case Stage::RamBoostValidate:
            if (g.ramPairRetryMode == 0) {
                g.vddqGood += VDDQ_STEP_MV;
                g.ramPairRetryMode = 1;
                g.pendingConfigMask = Config_Vddq;
            } else if (g.ramPairRetryMode == 1) {
                g.vddqGood -= VDDQ_STEP_MV;
                g.vdd2GoodUv += VDD2_STEP_UV;
                g.ramPairRetryMode = 2;
                g.pendingConfigMask = Config_Vddq | Config_Vdd2;
            } else {
                g.vdd2GoodUv += VDD2_STEP_UV;
                g.pendingConfigMask = Config_Vdd2;
            }
            break;
        case Stage::Ram1331Validate:
            g.vddqGood += VDDQ_STEP_MV;
            g.pendingConfigMask = Config_Vddq;
            break;
        case Stage::HighUvQuick:
            g.stage = Stage::BoostCpuRamValidate;
            g.recoveryNeeded = didNotBoot;
            g.pendingConfigMask = Config_HighUv;
            break;
        case Stage::HighUvLong:
            if (g.highUvGood > 0) --g.highUvGood;
            g.pendingConfigMask = Config_HighUv;
            break;
        case Stage::BoostCpuRamValidate:
            if (g.highUvGood > 0) --g.highUvGood;
            g.pendingConfigMask = Config_HighUv;
            break;
        case Stage::NormalMatrixValidate:
            if (g.lowUvGood > 0) --g.lowUvGood;
            g.pendingConfigMask = Config_LowUv;
            break;
        case Stage::NormalMemValidate:
        case Stage::BoostMemValidate:
            g.vddqGood += VDDQ_STEP_MV;
            g.pendingConfigMask = Config_Vddq;
            break;
        case Stage::BoostMatrixValidate:
            if (g.highUvGood > 0) --g.highUvGood;
            g.pendingConfigMask = Config_HighUv;
            break;
        case Stage::BoostCpuMemValidate:
            if (g.highUvGood > 0) --g.highUvGood;
            g.stage = Stage::BoostCpuRamValidate;
            g.pendingConfigMask = Config_HighUv;
            break;
        case Stage::NormalGpuValidate:
        case Stage::RealWorldValidate:
        default:
            break;
    }
    saveState();
}


bool sampleCpuVoltageAt(u32 cpuHz, int index, int total, int& outMv) {
    constexpr int kSettleReads = 2;
    constexpr int kSamples = 9;
    constexpr int kAttempts = 2;
    constexpr u32 kMaxSpreadUv = 20000U;

    for (int attempt = 0; attempt < kAttempts; ++attempt) {
        for (int settle = 0; settle < kSettleReads; ++settle) {
            renderVoltageScanModal(cpuHz, index, total,
                "Settling measurement " + std::to_string(settle + 1) + " of " + std::to_string(kSettleReads));
            svcSleepThread(700'000'000);
            HocMonClocks ignored{};
            hocmonGetClocks(&ignored);
        }

        std::vector<u32> samples;
        samples.reserve(kSamples);
        for (int sample = 0; sample < kSamples; ++sample) {
            std::string scanPhase = "Reading voltage sample " + std::to_string(sample + 1) + " of " + std::to_string(kSamples);
            if (attempt > 0) scanPhase += "  |  retrying noisy measurement";
            renderVoltageScanModal(cpuHz, index, total, scanPhase);
            svcSleepThread(700'000'000);

            HocMonClocks cur{};
            if (R_SUCCEEDED(hocmonGetClocks(&cur)) &&
                clockMatches(cur.overrideHz[0], cpuHz) &&
                clockMatches(cur.overrideHz[1], CLOCK_GPU_NORMAL_HZ) &&
                clockMatches(cur.overrideHz[2], CLOCK_RAM_NORMAL_HZ) &&
                clockMatches(cur.targetHz[0], cpuHz) && cur.cpuVoltageUv != 0)
                samples.push_back(cur.cpuVoltageUv);
        }

        if ((int)samples.size() != kSamples) {
            if (attempt + 1 < kAttempts) continue;
            return false;
        }

        std::sort(samples.begin(), samples.end());
        const u32 spread = samples.back() - samples.front();
        if (spread > kMaxSpreadUv && attempt + 1 < kAttempts) continue;

        const u32 medianUv = samples[kSamples / 2];
        outMv = (int)(((medianUv + 2500U) / 5000U) * 5U);
        return true;
    }
    return false;
}

void runAutomaticVoltageScan(bool forLowUv) {
    if (!guardWizardTunableState()) return;
    static const u32 cpuHz[6] = {
        CLOCK_CPU_VMIN_510_HZ, CLOCK_CPU_LOW_HZ, CLOCK_CPU_VMIN_714_HZ,
        CLOCK_CPU_VMIN_MID_HZ, CLOCK_CPU_VMIN_918_HZ, CLOCK_CPU_NORMAL_HZ,
    };
    g_scanForLowUv = forLowUv;
    g_vminScanScreen = false;
    g_vminScanSuccess = false;
    g_vminScanRestoreOk = true;
    g_vminScanErrorRc = 0;
    g_vminScanErrorText.clear();

    HocMonClocks before{};
    Result rc = hocmonGetClocks(&before);
    if (R_FAILED(rc)) {
        g_vminScanErrorRc = rc;
        g_vminScanErrorText = "Could not read current HOC overrides.";
        g_vminScanScreen = true;
        return;
    }

    clearVminSweepData();
    rc = hocmonSetOverride(HocMonModule_GPU, CLOCK_GPU_NORMAL_HZ);
    if (R_SUCCEEDED(rc)) rc = hocmonSetOverride(HocMonModule_MEM, CLOCK_RAM_NORMAL_HZ);
    if (R_FAILED(rc)) {
        g_vminScanErrorRc = rc;
        g_vminScanErrorText = "HOC refused an automatic Temporary Override.";
        g_vminScanRestoreOk = restoreTemporaryOverrides(before);
        g_vminScanScreen = true;
        return;
    }

    for (int i = 0; i < 6; ++i) {
        rc = hocmonSetOverride(HocMonModule_CPU, cpuHz[i]);
        if (R_FAILED(rc)) {
            g_vminScanErrorRc = rc;
            g_vminScanErrorText = "Could not switch the CPU Temporary Override.";
            break;
        }
        svcSleepThread(500'000'000);
        int mv = 0;
        if (!sampleCpuVoltageAt(cpuHz[i], i, 6, mv)) {
            g_vminScanErrorText = "Could not obtain a stable nine-sample CPU voltage set.";
            break;
        }
        g.vminObsMv[i] = mv;
        g.vminObsMask |= (1u << i);
    }

    g_vminScanRestoreOk = restoreTemporaryOverrides(before);
    if (!g_vminScanErrorText.empty() || g.vminObsMask != 0x3FU) {
        saveState();
        g_vminScanScreen = true;
        return;
    }

    buildVminPlateaus();
    g.stage = forLowUv ? Stage::LowUvValidateQuick : Stage::LowVminPlateauValidate;
    g.stageReadyAfterBoot = true;
    g.pendingConfigMask = Config_None;
    saveState();
    g_vminScanSuccess = true;
    g_vminScanScreen = true;
}

void runAutomaticLowUvScan() {
    runAutomaticVoltageScan(true);
}

void skipAutomaticRegionValidation(bool forLowUv) {
    clearVminSweepData();
    if (forLowUv) {
        enterLowVminSearchOrMinimumNotice();
    } else {
        enterVddqSearchOrMinimumNotice();
    }
    g.pendingConfigMask = Config_None;
    saveState();
}

void runAutomaticRegionValidation(bool forLowUv) {
    if (!guardWizardTunableState()) return;
    if (g.vminValidateCount <= 0) {
        g_resultAction = "No voltage regions were available. Run the voltage scan again.";
        g_lastKind = stress::Kind::Cpu;
        g_lastResult = stress::Result{};
        g_resultScreen = true;
        return;
    }

    HocMonClocks before{};
    Result rc = hocmonGetClocks(&before);
    if (R_FAILED(rc)) {
        g_resultAction = "Could not read current HOC overrides.";
        g_lastKind = stress::Kind::Cpu;
        g_lastResult = stress::Result{};
        g_resultScreen = true;
        return;
    }

    bool failed = false;
    for (int i = 0; i < g.vminValidateCount; ++i) {
        const u32 hz = g.vminValidateHz[i];
        guiPageClear();
        uiPrintf(1, "\x1b[36mBattery Wizard - AUTO CPU VALIDATION\x1b[0m");
        uiPrintf(3, "----------------------------------------");
        uiPrintf(5, "Region %d / %d", i + 1, g.vminValidateCount);
        uiPrintf(7, "CPU : %s @ ~%d mV", formatClock(hz).c_str(), g.vminValidateMv[i]);
        uiPrintf(8, "GPU : 384 MHz");
        uiPrintf(9, "RAM : 1331.2 MHz");
        uiPrintf(11, "Running built-in CPU test for 1 minute...");
        uiPresent();

        rc = hocmonSetOverride(HocMonModule_CPU, hz);
        if (R_SUCCEEDED(rc)) rc = hocmonSetOverride(HocMonModule_GPU, CLOCK_GPU_NORMAL_HZ);
        if (R_SUCCEEDED(rc)) rc = hocmonSetOverride(HocMonModule_MEM, CLOCK_RAM_NORMAL_HZ);
        if (R_FAILED(rc)) {
            g_resultAction = "Automatic override setup failed. No candidate change was recorded.";
            failed = true;
            break;
        }
        svcSleepThread(500'000'000);

        HocMonClocks cur{};
        rc = hocmonGetClocks(&cur);
        if (R_FAILED(rc) || !clockMatches(cur.overrideHz[0], hz) ||
            !clockMatches(cur.overrideHz[1], CLOCK_GPU_NORMAL_HZ) ||
            !clockMatches(cur.overrideHz[2], CLOCK_RAM_NORMAL_HZ)) {
            g_resultAction = "Automatic override verification failed. No candidate change was recorded.";
            failed = true;
            break;
        }

        g.testRunning = true;
        g.testKind = static_cast<int>(stress::Kind::Cpu);
        g.testDurationSec = 60;
        g.testStage = static_cast<int>(g.stage);
        saveState();
        g_lastKind = stress::Kind::Cpu;
        const std::string regionTitle = forLowUv ? "CPU Low UV Stability" : "CPU Low VMIN Stability";
        const std::string regionContext =
            "CPU " + formatClock(hz) + "  |  Region " + std::to_string(i + 1) +
            " of " + std::to_string(g.vminValidateCount) +
            "  |  ~" + std::to_string(g.vminValidateMv[i]) + " mV";
        g_lastResult = stress::run(stress::Kind::Cpu, 60, regionTitle, regionContext);
        g.testRunning = false;
        g.testKind = g.testDurationSec = g.testStage = 0;
        saveState();

        if (g_lastResult.outcome != stress::Outcome::Pass) {
            failed = true;
            if (g_lastResult.outcome == stress::Outcome::Fail) {
                if (forLowUv) {
                    if (g.lowUvGood > 0) --g.lowUvGood;
                    g.stage = Stage::LowUvLong;
                    g.pendingConfigMask = Config_LowUv;
                    g_resultAction = "CPU validation failed. Low UV was reduced by one level; apply/reboot, then the Wizard will rescan.";
                } else {
                    if (g.lowVminGood < STOCK_LOW_VMIN_MV)
                        g.lowVminGood = std::min(STOCK_LOW_VMIN_MV, g.lowVminGood + LOW_VMIN_STEP_MV);
                    g.stage = Stage::LowVminLong;
                    g.pendingConfigMask = Config_LowVmin;
                    g_resultAction = "CPU validation failed. Low VMIN was raised by 10 mV; apply/reboot, then the Wizard will rescan.";
                }
                g.stageReadyAfterBoot = false;
                clearVminSweepData();
                saveState();
            } else {
                g_resultAction = "Validation was cancelled or the test engine stopped. The tuning candidate was not changed.";
            }
            break;
        }
    }

    const bool restored = restoreTemporaryOverrides(before);
    if (!failed) {
        g_lastResult.outcome = stress::Outcome::Pass;
        if (forLowUv) {
            enterLowVminSearchOrMinimumNotice();
            g_resultAction = "All CPU voltage regions passed. CPU Low UV is confirmed; continuing to Low VMIN boot search.";
        } else {
            clearVminSweepData();
            enterVddqSearchOrMinimumNotice();
            g_resultAction = "All CPU voltage regions passed. CPU Low VMIN is confirmed; continuing to RAM tuning.";
        }
        g.pendingConfigMask = Config_None;
        saveState();
    }
    if (!restored) g_resultAction += " WARNING: previous Temporary Overrides could not be fully restored.";
    g_resultScreen = true;
}

void runAutomaticVminScan() {
    runAutomaticVoltageScan(false);
}



void stressDisplayForStage(Stage st, const OverrideExpectation& expected,
                           std::string& title, std::string& context) {
    title = "Stability Test";
    context.clear();

    auto clockContext = [&]() {
        std::string out;
        if (expected.cpuHz) out += "CPU " + formatClock(expected.cpuHz);
        if (expected.ramHz) {
            if (!out.empty()) out += "  |  ";
            out += "RAM " + formatClock(expected.ramHz);
        }
        return out;
    };

    switch (st) {
        case Stage::VddqQuick:
            title = "VDDQ Stability";
            context = "VDDQ " + std::to_string(g.vddqTest) + " mV";
            break;
        case Stage::VddqLong:
            title = "VDDQ Final Stability";
            context = "VDDQ " + std::to_string(g.vddqGood) + " mV";
            break;
        case Stage::Vdd2Quick:
            title = "VDD2 Stability";
            context = "VDD2 " + formatVdd2(g.vdd2TestUv);
            break;
        case Stage::Vdd2Long:
            title = "VDDQ + VDD2 Pair Stability";
            context = "VDDQ " + std::to_string(g.vddqGood) + " mV  |  VDD2 " + formatVdd2(g.vdd2GoodUv);
            break;
        case Stage::NormalMatrixValidate:
            title = "CPU Low UV + RAM Stability";
            context = clockContext();
            break;
        case Stage::HighUvQuick:
            title = "CPU High UV Stability";
            context = "High UV " + std::to_string(g.highUvTest);
            if (!clockContext().empty()) context += "  |  " + clockContext();
            break;
        case Stage::HighUvLong:
            title = "CPU High UV Stability";
            context = "High UV " + std::to_string(g.highUvGood);
            if (!clockContext().empty()) context += "  |  " + clockContext();
            break;
        case Stage::BoostCpuRamValidate:
            title = "CPU High UV Stability";
            context = "High UV " + std::to_string(g.highUvGood) + "  |  " + clockContext();
            break;
        case Stage::BoostCpuMemValidate:
            title = "CPU High UV + RAM Stability";
            context = "High UV " + std::to_string(g.highUvGood) + "  |  " + clockContext();
            break;
        case Stage::RamBoostValidate:
            title = "RAM Stability";
            context = "Boost state  |  " + clockContext();
            break;
        case Stage::Ram1331Validate:
            title = "RAM Stability";
            context = "Handheld state  |  " + clockContext();
            break;
        case Stage::LowVminFinalLong:
            title = "CPU Low VMIN Stability";
            context = "Low VMIN " + std::to_string(g.lowVminGood) + " mV  |  " + clockContext();
            break;
        default:
            title = stageName(st);
            context = clockContext();
            break;
    }
}

void runCurrentTest() {
    if (!guardWizardTunableState()) return;
    stress::Kind kind;
    int seconds = 0;
    if (!testPlan(g.stage, kind, seconds)) return;

    OverrideExpectation expected{};
    const bool hasOverrides = overridePlan(g.stage, expected);
    HocMonClocks before{};
    g_overrideAction = PendingOverrideAction::StartTest;
    if (hasOverrides && !setupAutomaticTestOverrides(g.stage, before)) {
        g_overridePrompt = true;
        return;
    }
    g_overridePrompt = false;

    const Stage testedStage = g.stage;
    g_lastVminAtFloor = false;
    if (isVminSweepStage(testedStage))
        recordVminObservation(testedStage);
    g.testRunning = true;
    g.testKind = static_cast<int>(kind);
    g.testDurationSec = seconds;
    g.testStage = static_cast<int>(testedStage);
    saveState();

    std::string stressTitle;
    std::string stressContext;
    stressDisplayForStage(testedStage, expected, stressTitle, stressContext);
    g_lastKind = kind;
    g_lastResult = stress::run(kind, seconds, stressTitle, stressContext);

    g.testRunning = false;
    g.testKind = 0;
    g.testDurationSec = 0;
    g.testStage = 0;
    saveState();

    const bool restored = !hasOverrides || restoreTemporaryOverrides(before);

    g_resultAction.clear();
    if (g_lastResult.outcome == stress::Outcome::Pass) {
        handlePass();
        g_resultAction = "PASS recorded automatically. The wizard advanced to the next step.";
        if (isVminSweepStage(testedStage)) {
            const u32 uv = g_overrideCheck.current.cpuVoltageUv;
            g_resultAction += " CPU rail was about " + std::to_string((uv + 500U) / 1000U) + " mV.";
        }
    } else if (g_lastResult.outcome == stress::Outcome::Fail) {
        handleFail(false);
        g_resultAction = "FAIL recorded automatically. Follow the safer value shown on the next step.";
    } else if (g_lastResult.outcome == stress::Outcome::Cancelled) {
        g_resultAction = "No tuning result was recorded. You can run the same test again.";
    } else {
        g_resultAction = "The tuning value was NOT marked failed. Fix the test-engine problem and retry.";
    }
    if (!restored)
        g_resultAction += " WARNING: the previous test clocks could not be fully restored.";
    g_resultScreen = true;
}

} // namespace

int main(int argc, char** argv) {
    consoleInit(nullptr);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    const AppletType appletType = appletGetAppletType();
    const bool fullMemoryMode =
        appletType == AppletType_Application || appletType == AppletType_SystemApplication;

    if (!fullMemoryMode) {
        while (appletMainLoop()) {
            padUpdate(&pad);
            const u64 k = padGetButtonsDown(&pad);
            consoleClear();
            std::printf("\x1b[1;1H\x1b[31mHOC Undervolting Wizard - CANNOT START\x1b[0m\n");
            std::printf("------------------------------------------------------------\n\n");
            std::printf("\x1b[1mApplet Mode detected.\x1b[0m\n\n");
            std::printf("The Wizard's stability tests require Full Memory Mode.\n");
            std::printf("Applet Mode is therefore not supported.\n\n");
            std::printf("Start hbmenu correctly:\n");
            std::printf("  1. Return to the HOME Menu.\n");
            std::printf("  2. Highlight any installed game.\n");
            std::printf("  3. Hold [R] while starting the game.\n");
            std::printf("  4. Keep holding [R] until hbmenu opens.\n");
            std::printf("  5. Start HOC Undervolting Wizard again.\n\n");
            std::printf("Do NOT launch hbmenu from the Album for stability testing.\n\n");
            std::printf("[B] Exit\n");
            uiPresent();
            if (k & HidNpadButton_B) break;
            svcSleepThread(20'000'000);
        }
        consoleExit(nullptr);
        return 0;
    }

    // Full-memory mode can use the graphical backend for every startup screen.
    consoleExit(nullptr);
    if (!gui::init()) {
        consoleInit(nullptr);
        while (appletMainLoop()) {
            padUpdate(&pad);
            consoleClear();
            std::printf("\x1b[1;1H\x1b[31mHOC Undervolting Wizard - GUI ERROR\x1b[0m\n");
            std::printf("------------------------------------------------------------\n\n");
            std::printf("Could not initialize the graphical interface.\n");
            std::printf("The Switch shared font / framebuffer backend is unavailable.\n\n");
            std::printf("[B] Exit\n");
            consoleUpdate(nullptr);
            if (padGetButtonsDown(&pad) & HidNpadButton_B) break;
            svcSleepThread(20'000'000);
        }
        consoleExit(nullptr);
        return 0;
    }

    if (updater::startupCheckAndPrompt(pad, argc, argv)) {
        gui::shutdown();
        return 0;
    }

    ensureDir();

    // Load Wizard progress before deciding whether the safety notice is needed.
    // Existing tuning runs must never be interrupted by a newly introduced
    // disclaimer, but a deliberate Wizard reset starts a fresh run and clears
    // the acknowledgement below.
    migrateLegacyState();
    const bool hadStateBeforeLoad = access(STATE, F_OK) == 0;
    if (!loadState()) saveState();

    const bool tuningAlreadyStarted =
        g.stage != Stage::HardwareDetection && g.stage != Stage::Preparation;
    bool riskAccepted = access(DISCLAIMER_ACK, F_OK) == 0;

    // Upgrade compatibility: an older installation already beyond Baseline has
    // necessarily been using the Wizard. Mark it accepted silently so a reboot
    // during tuning never inserts the disclaimer into the active workflow.
    if (!riskAccepted && hadStateBeforeLoad && tuningAlreadyStarted) {
        std::ofstream ack(DISCLAIMER_ACK, std::ios::trunc);
        if (ack) {
            ack << "accepted=1\n";
            ack.flush();
            ack.close();
            fsdevCommitDevice("sdmc");
            riskAccepted = true;
        }
    }

    while (appletMainLoop() && !riskAccepted) {
        padUpdate(&pad);
        const u64 k = padGetButtonsDown(&pad);

        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "SAFETY NOTICE";
        m.title = "Use at your own risk";
        m.body = {
            "This Wizard changes CPU and RAM voltage settings and runs stability tests.",
            "Unstable settings can cause crashes, boot failures, save/data corruption or data loss.",
            "In extreme cases, hardware damage may also be possible.",
            "The author and contributors provide no warranty and accept no liability for resulting software, data or hardware damage.",
            "By continuing, you accept all risk and responsibility."
        };
        m.primaryAction = "I understand - continue";
        m.secondaryAction = "Exit";
        m.tone = gui::ModalTone::Amber;
        gui::presentModal(m);

        if (k & HidNpadButton_A) {
            std::ofstream ack(DISCLAIMER_ACK, std::ios::trunc);
            if (ack) {
                ack << "accepted=1\n";
                ack.flush();
                ack.close();
                fsdevCommitDevice("sdmc");
                riskAccepted = true;
            }
        } else if (k & HidNpadButton_B) {
            gui::shutdown();
            return 0;
        }
        svcSleepThread(20'000'000);
    }

    if (!riskAccepted) {
        gui::shutdown();
        return 0;
    }

    // Identify Mariko DRAM on every upgraded state that does not have it yet.
    // New users remain on the dedicated Hardware Detection page; progressed
    // users are enriched silently without losing already-tuned RAM values.
    if (!g.ramDetected)
        detectRamHardware();

    g_interruptedPrompt = g.testRunning;
    g_bootPrompt = g.rebootPending;

    bool redraw = true;
    int guiPulseTicks = 0;
    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 k = padGetButtonsDown(&pad);
        if (++guiPulseTicks >= 60) {
            guiPulseTicks = 0;
            g_guiPulse = !g_guiPulse;
            redraw = true;
        }

        if (redraw) {
            render();
            redraw = false;
        }

        if (g_bootPrompt) {
            int active = 0;
            const BootInference state = inferBootState(&active);
            if (k & HidNpadButton_A) {
                if (state == BootInference::RequestedActive) {
                    g_bootRecoveryCandidate = -1;
                    g.rebootPending = false;
                    g_bootPrompt = false;
                    g.pendingConfigMask = Config_None;
                    if (g.stage == Stage::Preparation) {
                        g.stage = Stage::LowUvQuick;
                        g.lowUvTest = std::min(LOW_UV_MAX, g.lowUvGood + 1);
                        g.stageReadyAfterBoot = false;
                    } else if (g.stage == Stage::LowUvQuick || g.stage == Stage::LowVminQuick) {
                        handlePass();
                    } else {
                        g.stageReadyAfterBoot = true;
                        saveState();
                    }
                } else if (state == BootInference::SaferActive) {
                    const int confirmed = g_bootRecoveryCandidate >= 0 ? g_bootRecoveryCandidate : active;
                    const Stage recoveryStage = g.stage;
                    const bool needsApply = confirmed != active;
                    g.rebootPending = false;
                    g_bootPrompt = false;
                    g_bootRecoveryCandidate = -1;
                    clearVminSweepData();

                    u32 recoveryMask = Config_None;
                    if (recoveryStage == Stage::LowUvQuick) {
                        g.lowUvGood = std::max(0, confirmed);
                        g.lowUvTest = g.lowUvGood;
                        g.stage = Stage::LowUvLong;
                        recoveryMask = Config_LowUv;
                    } else if (recoveryStage == Stage::LowVminQuick) {
                        g.lowVminGood = confirmed;
                        g.lowVminTest = g.lowVminGood;
                        g.stage = Stage::LowVminLong;
                        recoveryMask = Config_LowVmin;
                    }

                    if (!needsApply) {
                        g.pendingConfigMask = Config_None;
                        g.stageReadyAfterBoot = true;
                        saveState();
                    } else {
                        g.stageReadyAfterBoot = false;
                        g.pendingConfigMask = recoveryMask;
                        saveState();
                        g_autoSetMask = recoveryMask;
                        g_autoPrepError.clear();
                        if (applyAutomaticCurrentSetting(recoveryMask)) {
                            g_configCheck.mask = recoveryMask;
                            g_rebootConfirm = true;
                        } else {
                            g_autoPrepConfirm = true;
                        }
                    }
                }
                redraw = true;
            } else if ((k & HidNpadButton_X) && state == BootInference::SaferActive) {
                if (g_bootRecoveryCandidate < 0) g_bootRecoveryCandidate = active;
                if (g.stage == Stage::LowUvQuick)
                    g_bootRecoveryCandidate = std::max(0, g_bootRecoveryCandidate - 1);
                else if (g.stage == Stage::LowVminQuick)
                    g_bootRecoveryCandidate = std::min(750, g_bootRecoveryCandidate + LOW_VMIN_STEP_MV);
                redraw = true;
            } else if (k & HidNpadButton_X) {
                g_bootRecoveryCandidate = -1;
                g.rebootPending = false;
                g_bootPrompt = false;
                handleFail(true);
                redraw = true;
            } else if (k & HidNpadButton_B) {
                break;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_vminScanScreen) {
            if (k & HidNpadButton_A) {
                if (g_vminScanSuccess) {
                    g_vminScanScreen = false;
                    runAutomaticRegionValidation(g_scanForLowUv);
                    redraw = true;
                } else {
                    g_vminScanScreen = false;
                    if (g_scanForLowUv) runAutomaticLowUvScan();
                    else runAutomaticVminScan();
                    redraw = true;
                }
            } else if ((k & HidNpadButton_Plus) && g_vminScanSuccess) {
                g_vminScanScreen = false;
                skipAutomaticRegionValidation(g_scanForLowUv);
                redraw = true;
            } else if (k & HidNpadButton_B) {
                g_vminScanScreen = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_interruptedPrompt) {
            if (k & HidNpadButton_A) {
                g.testRunning = false;
                if (g.testStage >= 0 && g.testStage <= static_cast<int>(Stage::LowUvValidateQuick))
                    g.stage = static_cast<Stage>(g.testStage);
                g.testKind = g.testDurationSec = g.testStage = 0;
                saveState();
                handleFail(false);
                g_interruptedPrompt = false;
                redraw = true;
            } else if (k & HidNpadButton_X) {
                g.testRunning = false;
                if (g.testStage >= 0 && g.testStage <= static_cast<int>(Stage::LowUvValidateQuick))
                    g.stage = static_cast<Stage>(g.testStage);
                g.testKind = g.testDurationSec = g.testStage = 0;
                saveState();
                g_interruptedPrompt = false;
                redraw = true;
            } else if (k & HidNpadButton_B) {
                break;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_configDebugScreen) {
            if (k & HidNpadButton_A) {
                g_configDebugPage = (g_configDebugPage + 1) % 4;
                redraw = true;
            } else if (k & HidNpadButton_X) {
                g_configDebugPage = (g_configDebugPage + 3) % 4;
                redraw = true;
            } else if (k & HidNpadButton_B) {
                g_configDebugScreen = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_configPrompt) {
            if (g_configPromptSafetyOnly) {
                if (k & HidNpadButton_A) {
                    if (guardWizardTunableState()) {
                        g_configPromptSafetyOnly = false;
                        g_configPrompt = false;
                    }
                    redraw = true;
                } else if (k & HidNpadButton_B) {
                    g_configPromptSafetyOnly = false;
                    g_configPrompt = false;
                    redraw = true;
                }
                svcSleepThread(20'000'000);
                continue;
            }
            if ((k & HidNpadButton_Y) && (g_configCheck.mask & (Config_Prepare | Config_LowUv | Config_LowVmin))) {
                g_autoSetMask = g_configCheck.mask;
                g_autoPrepError.clear();
                g_configPrompt = false;
                g_autoPrepConfirm = true;
                redraw = true;
            } else if ((k & HidNpadButton_X) && g.stage == Stage::Preparation) {
                if (captureCurrentSettingsBaseline()) {
                    g_configPrompt = false;
                    continueFromPreparationBaseline();
                }
                redraw = true;
            } else if (k & HidNpadButton_A) {
                u32 mask = g_configCheck.mask;
                if (g.stage == Stage::LowUvQuick || g.stage == Stage::LowVminQuick)
                    mask = defaultConfigMaskForStage(g.stage);
                if (verifyPersistentSettings(mask)) {
                    g.stageReadyAfterBoot = false;
                    g.pendingConfigMask = mask;
                    g_configCheck.mask = mask;
                    g_configPrompt = false;
                    g_rebootConfirm = true;
                    saveState();
                }
                redraw = true;
            } else if (k & HidNpadButton_B) {
                g_configPrompt = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_autoPrepConfirm) {
            if (k & HidNpadButton_A) {
                g_autoPrepError.clear();
                if (applyAutomaticCurrentSetting(g_autoSetMask)) {
                    if (g_autoSetMask & (Config_LowUv | Config_LowVmin))
                        g.stageReadyAfterBoot = false;
                    g.pendingConfigMask = g_autoSetMask;
                    g_autoPrepConfirm = false;
                    g_configPrompt = false;
                    g_configCheck.mask = g_autoSetMask;
                    g_rebootConfirm = true;
                    saveState();
                }
                redraw = true;
            } else if (k & HidNpadButton_B) {
                g_autoPrepConfirm = false;
                g_autoPrepError.clear();
                g_configPrompt = true;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_rebootConfirm) {
            if (k & HidNpadButton_A) {
                const bool safeToReboot = (g.stage == Stage::Preparation)
                    ? verifyPersistentSettings(Config_Prepare)
                    : guardWizardTunableState();
                if (!safeToReboot) {
                    g_rebootConfirm = false;
                    if (g.stage == Stage::Preparation) g_configPrompt = true;
                    redraw = true;
                    svcSleepThread(20'000'000);
                    continue;
                }
                g.pendingConfigMask = g_configCheck.mask;
                g.rebootPending = true;
                g_rebootConfirm = false;
                saveState();

                guiPageClear();
                uiPrintf(6, "\x1b[32mSetting verified.\x1b[0m");
                uiPrintf(8, "Restarting console...");
                uiPresent();
                svcSleepThread(400'000'000);

                g_rebootError = appletRequestToReboot();
                if (R_FAILED(g_rebootError)) {
                    g.rebootPending = false;
                    saveState();
                    guiPageClear();
                    uiPrintf(5, "\x1b[31mAutomatic restart failed.\x1b[0m");
                    uiPrintf(7, "Result : 0x%08X", g_rebootError);
                    uiPrintf(9, "Restart CFW manually, then reopen Wizard.");
                    uiPrintf(11, "B : Exit");
                    uiPresent();
                    while (appletMainLoop()) {
                        padUpdate(&pad);
                        if (padGetButtonsDown(&pad) & HidNpadButton_B) break;
                        svcSleepThread(20'000'000);
                    }
                    break;
                }
            } else if (k & HidNpadButton_B) {
                g_rebootConfirm = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_overridePrompt) {
            if (k & HidNpadButton_A) {
                g_overridePrompt = false;
                if (g_overrideAction == PendingOverrideAction::VminProbe) runAutomaticVminScan();
                else runCurrentTest();
                redraw = true;
            } else if (k & HidNpadButton_B) {
                g_overridePrompt = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_resultScreen) {
            if (k & HidNpadButton_A || k & HidNpadButton_B) {
                g_resultScreen = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (g_resetConfirm) {
            if (k & HidNpadButton_A) {
                resetState();
                // A reset starts a new tuning run. Show the safety notice again
                // on the next app start while the Wizard is back at Baseline.
                unlink(DISCLAIMER_ACK);
                fsdevCommitDevice("sdmc");
                detectRamHardware();
                g_resetConfirm = false;
                redraw = true;
            } else if (k & HidNpadButton_B) {
                g_resetConfirm = false;
                redraw = true;
            }
            svcSleepThread(20'000'000);
            continue;
        }

        if (k & HidNpadButton_Minus) {
            g_resetConfirm = true;
            redraw = true;
        } else if ((k & HidNpadButton_B) && g.stage == Stage::RealWorldValidate && g_realWorldHelpPage) {
            g_realWorldHelpPage = false;
            redraw = true;
        } else if (k & HidNpadButton_B) {
            saveState();
            break;
        } else if (g.stage == Stage::HardwareDetection) {
            if (k & HidNpadButton_A) {
                if (!g.ramDetected) detectRamHardware();
                else handlePass();
                redraw = true;
            }
        } else if (g.stage == Stage::Preparation && (k & HidNpadButton_Y)) {
            g_autoSetMask = Config_Prepare;
            g_autoPrepError.clear();
            g_autoPrepConfirm = true;
            redraw = true;
        } else if (g.stage == Stage::Preparation && (k & HidNpadButton_X)) {
            if (captureCurrentSettingsBaseline()) continueFromPreparationBaseline();
            else g_configPrompt = true;
            redraw = true;
        } else if (g.limitNoticePending) {
            // A limit page is informational/confirmational only. Do not let
            // Y / + / X fall through into normal search actions.
            if (k & HidNpadButton_A) {
                confirmWizardLimitAndContinue();
                redraw = true;
            }
        } else if ((k & HidNpadButton_Y) && g.stage != Stage::Preparation) {
            const u32 cfgMask = activeConfigMask();
            if (cfgMask & (Config_LowUv | Config_LowVmin)) {
                g_autoSetMask = cfgMask;
                g_autoPrepError.clear();
                g_autoPrepConfirm = true;
                redraw = true;
            }
        } else if ((k & HidNpadButton_Plus) && g.stage != Stage::Preparation) {
            if (g.stage == Stage::RealWorldValidate && !g_realWorldHelpPage) {
                g_manualPass = true;
                handlePass();
                g_manualPass = false;
            } else if (g.stage == Stage::LowUvValidateQuick) {
                skipAutomaticRegionValidation(true);
            } else if (g.stage == Stage::LowVminPlateauValidate) {
                skipAutomaticRegionValidation(false);
            } else if (isVminSweepStage(g.stage)) {
                runAutomaticVminScan();
            } else {
                const u32 cfgMask = activeConfigMask();
                stress::Kind skipKind;
                int skipSeconds = 0;
                const bool searchSetting = g.stage == Stage::LowUvQuick ||
                                           g.stage == Stage::LowVminQuick ||
                                           g.stage == Stage::VddqQuick ||
                                           g.stage == Stage::Vdd2Quick ||
                                           g.stage == Stage::HighUvQuick;
                if (cfgMask != Config_None && searchSetting) {
                    g_manualPass = true;
                    handlePass();
                    g_manualPass = false;
                } else if (cfgMask != Config_None) {
                    if (verifyPersistentSettings(cfgMask)) {
                        g_manualPass = true;
                        handlePass();
                        g_manualPass = false;
                    } else {
                        g_configPrompt = true;
                    }
                } else if (testPlan(g.stage, skipKind, skipSeconds)) {
                    g_manualPass = true;
                    handlePass();
                    g_manualPass = false;
                }
            }
            redraw = true;
        } else if (k & HidNpadButton_X) {
            // X is only a manual "known unstable" shortcut while searching a
            // new candidate. Long/final validations record FAIL automatically;
            // crashes/reboots are handled by the interrupted-test popup on restart.
            const u32 cfgMask = activeConfigMask();
            const bool searchSetting = g.stage == Stage::LowUvQuick ||
                                       g.stage == Stage::LowVminQuick ||
                                       g.stage == Stage::VddqQuick ||
                                       g.stage == Stage::Vdd2Quick ||
                                       g.stage == Stage::HighUvQuick;
            if (cfgMask != Config_None && searchSetting) {
                handleFail(false);
                redraw = true;
            }
        } else if (k & HidNpadButton_A) {
            if (g.stage == Stage::RealWorldValidate) {
                if (!g_realWorldHelpPage) {
                    g_realWorldHelpPage = true;
                } else {
                    g_manualPass = true;
                    handlePass();
                    g_manualPass = false;
                }
                redraw = true;
                svcSleepThread(20'000'000);
                continue;
            }
            const bool bootSearch = g.stage == Stage::LowUvQuick || g.stage == Stage::LowVminQuick;
                const u32 cfgMask = bootSearch ? defaultConfigMaskForStage(g.stage) : activeConfigMask();
                if (cfgMask != Config_None) {
                if (verifyPersistentSettings(cfgMask) && guardWizardTunableState()) {
                    if (bootSearch) g.stageReadyAfterBoot = false;
                    g.pendingConfigMask = cfgMask;
                    g_configCheck.mask = cfgMask;
                    g_rebootConfirm = true;
                    saveState();
                } else {
                    g_configPrompt = true;
                }
            } else if (g.stage == Stage::LowUvLong) {
                runAutomaticLowUvScan();
            } else if (g.stage == Stage::LowUvValidateQuick) {
                runAutomaticRegionValidation(true);
            } else if (g.stage == Stage::LowVminLong || isVminSweepStage(g.stage)) {
                runAutomaticVminScan();
            } else if (g.stage == Stage::LowVminPlateauValidate) {
                runAutomaticRegionValidation(false);
            } else {
                stress::Kind kind;
                int seconds = 0;
                if (testPlan(g.stage, kind, seconds)) runCurrentTest();
                else handlePass();
            }
            redraw = true;
        }

        svcSleepThread(20'000'000);
    }

    gui::shutdown();
    return 0;
}

