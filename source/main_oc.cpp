#include <switch.h>

#include "gui_console.hpp"
#include "hoc_monitor.h"
#include "oc_profiles.hpp"
#include "oc_engine.hpp"
#include "oc_bench.hpp"
#include "oc_config.hpp"
#include "stress_tests.hpp"
#include "updater.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr const char* APP_DIR = "sdmc:/switch/HOC-Overclocking-Wizard";
constexpr const char* BACKUP_DIR = "sdmc:/switch/HOC-Overclocking-Wizard/SafetyBackup";
constexpr const char* STATE_FILE = "sdmc:/switch/HOC-Overclocking-Wizard/state.ini";
constexpr const char* POINTS_FILE = "sdmc:/switch/HOC-Overclocking-Wizard/measurements.csv";
constexpr const char* RESULTS_FILE = "sdmc:/switch/HOC-Overclocking-Wizard/results.txt";
constexpr const char* DISCLAIMER_FILE = "sdmc:/switch/HOC-Overclocking-Wizard/disclaimer.accepted";
constexpr const char* PERF_OC_DIR = "sdmc:/switch/.packages/Performance Modes/OCMode";
constexpr const char* HOC_CONFIG = "sdmc:/config/horizon-oc/config.ini";
constexpr const char* HOC_KIP = "sdmc:/atmosphere/kips/hoc.kip";

constexpr u32 CPU_BASE_HZ = 1020000000U;
constexpr u32 GPU_BASE_HZ = 384000000U;
constexpr u32 RAM_BASE_HZ = 1331000000U;
constexpr int CPU_SAFE_MAX_MHZ = 2397;  // HOC Mariko safe clock envelope with UV.
constexpr int GPU_SAFE_MAX_MHZ = 1382;   // HOC Mariko safe clock envelope; device must still validate it.
constexpr int GPU_AUTO_VMAX_MV = 825;   // First HOC Mariko GPU Vmax threshold; automatic search never exceeds it.
constexpr int CPU_LOW_VMIN_FLOOR = 590; // conservative guide floor for automatic Low search
constexpr int CPU_HIGH_VMIN_FLOOR = 650; // current HOC UI High VMIN lower bound
constexpr int CPU_VMAX_SAFE = 1120;      // NVIDIA/HOC CPU voltage rating used as automatic ceiling
constexpr int VDDQ_MIN_MV = 400;
constexpr int VDD2_MIN_UV = 912500;
constexpr int GPU_MIN_MV = 480;

const int GPU_FREQS[] = {768,844,921,998,1075,1152,1228,1267,1305,1344,1382};
const int CPU_FREQS[] = {1683,1785,1887,1963,2091,2193,2295,2397};
const int SOC_FREQS[] = {1866,2000,2133,2200,2266,2333,2400,2433,2466,2533,2566,2600,2666,2700,2733,2766,2800,2833,2900,2933,3000,3033,3100,3133,3166,3200,3266,3333};
const int SOC_MV[] = {637,650,662,675,687,700,712,725,737,750,762,775,787,800,812,825,837,850,862,875,887,900,912,925,937,950,962,975,987,1000,1012,1025,1037,1050,1062,1075,1087,1100,1112,1125,1137,1150,1162,1175,1187,1200};

enum class Stage : int {
    Hardware = 0,
    BenchmarkPrep,
    RamPreparation,
    RamSweep,
    RamGraph,
    RamHpSet,
    RamHpTest,
    RamStSet,
    RamStTest,
    RamDvb,
    RamVdd2,
    RamVddq,
    RamSoc,
    RamFinalGraph,
    GpuPreparation,
    GpuTune,
    GpuGraph,
    GpuRamCombined,
    CpuPreparation,
    CpuSweep,
    CpuHighUv,
    CpuLowUv,
    CpuLowVmin,
    CpuTbreak2Set,
    CpuTbreak2Test,
    CpuTbreak3Set,
    CpuTbreak3Test,
    CpuHighVmin,
    CpuVmax,
    CpuFinalSweep,
    CpuGraph,
    CpuRamCombined,
    Finalize,
    Complete,
};

struct State {
    Stage stage = Stage::Hardware;
    int dramId = -1;
    int is8GB = 0;
    int consoleType = -1;
    int profileIndex = -1;
    int benchmarkReady = 0;
    int backupDone = 0;

    int ramSearchIndex = -1;
    int ramSearchEndIndex = -1;
    int ramRecommendedMHz = 0;
    int ramStableMaxMHz = 0;
    int ramTimingMode = 0; // 0 Common, 1 ST
    int ramHpMode = 0;
    int dvbGood = 5;
    int dvbCandidate = 4;
    int dvbApplied = 0;
    int vdd2GoodUv = 1175000;
    int vdd2CandidateUv = 1162500;
    int vdd2Applied = 0;
    int vddqGoodMv = 600;
    int vddqCandidateMv = 590;
    int vddqApplied = 0;
    int socTableMHz = 0;
    int socGoodMv = 0;
    int socCandidateMv = 0;
    int socApplied = 0;

    int gpuPrepApplied = 0;
    int gpuIndex = 0;
    int gpuHaveBaseline = 0;
    int gpuGoodMv = 800;
    int gpuCandidateMv = 790;
    int gpuApplied = 0;
    int gpuRecommendedMHz = 0;
    int gpuStableMaxMHz = 0;
    int gpuLastPerfMilli = 0;
    int gpuRamTrial = 0;
    int gpuRamOriginalRam = 0;
    int gpuRamOriginalGpu = 0;
    int gpuRamOriginalMv = 0;
    int gpuRamOriginalSoc = 0;
    int gpuRamOriginalVdd2Uv = 0;

    int cpuPrepApplied = 0;
    int cpuIndex = 0;
    int cpuRecommendedMHz = 0;
    int cpuStableMaxMHz = 0;
    int highUvGood = 5;
    int highUvCandidate = 6;
    int highUvApplied = 0;
    int lowUvGood = 0;
    int lowUvCandidate = 1;
    int lowUvApplied = 0;
    int lowLastCostMv = 0;
    int lowBestUv = 0;
    int lowBestVmin = 620;
    int lowBestCostMv = 0;
    int lowVminCandidate = 610;
    int lowVminApplied = 0;
    int finalTbreak = 3;
    int tbreak2CostMv = 0;
    int tbreak3CostMv = 0;
    int highVminGood = 870;
    int highVminCandidate = 850;
    int highVminApplied = 0;
    int vmaxGood = CPU_VMAX_SAFE;
    int vmaxCandidate = 0;
    int vmaxApplied = 0;
    int cpuFinalIndex = 0;

    int cpuRamTrial = 0;
    int cpuRamOriginalRam = 0;
    int cpuRamOriginalCpu = 0;
    int cpuRamOriginalHighUv = 0;
    int cpuRamOriginalSoc = 0;
    int cpuRamOriginalVdd2Uv = 0;

    int rebootPending = 0;
    int testRunning = 0;
    int testStage = -1;
};

State g;
std::vector<oc::SweepPoint> ramPoints, gpuPoints, cpuPoints;
std::string g_message;
bool g_errorModal = false;
bool g_recoveryModal = false;
HocMonClocks g_active{};

const oc::RamProfile* profile() {
    if (g.profileIndex < 0 || g.profileIndex >= int(sizeof(oc::RAM_PROFILES)/sizeof(oc::RAM_PROFILES[0]))) return nullptr;
    return &oc::RAM_PROFILES[g.profileIndex];
}

int profileIndex(const oc::RamProfile* p) {
    if (!p) return -1;
    for (int i=0;i<int(sizeof(oc::RAM_PROFILES)/sizeof(oc::RAM_PROFILES[0]));++i)
        if (&oc::RAM_PROFILES[i] == p) return i;
    return -1;
}

void ensureDir(const char* path) { mkdir(path, 0777); }
bool fileExists(const char* path) { struct stat st{}; return stat(path,&st)==0; }

bool copyFile(const char* src, const char* dst) {
    std::ifstream in(src, std::ios::binary); if(!in) return false;
    std::ofstream out(dst, std::ios::binary|std::ios::trunc); if(!out) return false;
    out << in.rdbuf(); out.flush(); return bool(out);
}

std::string fmtMvUv(int uv) {
    std::ostringstream o; o << (uv/1000);
    if (uv%1000==500) o << ".5";
    o << " mV"; return o.str();
}
std::string fmt1(double v) { char b[48]; std::snprintf(b,sizeof(b),"%.1f",v); return b; }

void saveState() {
    ensureDir(APP_DIR);
    std::ofstream f(STATE_FILE,std::ios::trunc); if(!f) return;
    f << "stage=" << int(g.stage) << '\n';
#define W(x) f << #x << '=' << g.x << '\n'
    W(dramId); W(is8GB); W(consoleType); W(profileIndex); W(benchmarkReady); W(backupDone);
    W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramTimingMode); W(ramHpMode); W(dvbGood); W(dvbCandidate); W(dvbApplied);
    W(vdd2GoodUv); W(vdd2CandidateUv); W(vdd2Applied); W(vddqGoodMv); W(vddqCandidateMv); W(vddqApplied); W(socTableMHz); W(socGoodMv); W(socCandidateMv); W(socApplied);
    W(gpuPrepApplied); W(gpuIndex); W(gpuHaveBaseline); W(gpuGoodMv); W(gpuCandidateMv); W(gpuApplied); W(gpuRecommendedMHz); W(gpuStableMaxMHz); W(gpuLastPerfMilli);
    W(gpuRamTrial); W(gpuRamOriginalRam); W(gpuRamOriginalGpu); W(gpuRamOriginalMv); W(gpuRamOriginalSoc); W(gpuRamOriginalVdd2Uv);
    W(cpuPrepApplied); W(cpuIndex); W(cpuRecommendedMHz); W(cpuStableMaxMHz); W(highUvGood); W(highUvCandidate); W(highUvApplied);
    W(lowUvGood); W(lowUvCandidate); W(lowUvApplied); W(lowLastCostMv); W(lowBestUv); W(lowBestVmin); W(lowBestCostMv); W(lowVminCandidate); W(lowVminApplied);
    W(finalTbreak); W(tbreak2CostMv); W(tbreak3CostMv); W(highVminGood); W(highVminCandidate); W(highVminApplied); W(vmaxGood); W(vmaxCandidate); W(vmaxApplied); W(cpuFinalIndex);
    W(cpuRamTrial); W(cpuRamOriginalRam); W(cpuRamOriginalCpu); W(cpuRamOriginalHighUv); W(cpuRamOriginalSoc); W(cpuRamOriginalVdd2Uv);
    W(rebootPending); W(testRunning); W(testStage);
#undef W
    f.flush(); fsdevCommitDevice("sdmc");
}

void loadState() {
    std::ifstream f(STATE_FILE); if(!f) return;
    std::string line;
    while(std::getline(f,line)) {
        auto p=line.find('='); if(p==std::string::npos) continue;
        std::string k=line.substr(0,p), v=line.substr(p+1); int n=std::atoi(v.c_str());
        if(k=="stage"){g.stage=Stage(n);continue;}
#define R(name) if(k==#name){g.name=decltype(g.name)(n);continue;}
        R(dramId) R(is8GB) R(consoleType) R(profileIndex) R(benchmarkReady) R(backupDone)
        R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramTimingMode) R(ramHpMode) R(dvbGood) R(dvbCandidate) R(dvbApplied)
        R(vdd2GoodUv) R(vdd2CandidateUv) R(vdd2Applied) R(vddqGoodMv) R(vddqCandidateMv) R(vddqApplied) R(socTableMHz) R(socGoodMv) R(socCandidateMv) R(socApplied)
        R(gpuPrepApplied) R(gpuIndex) R(gpuHaveBaseline) R(gpuGoodMv) R(gpuCandidateMv) R(gpuApplied) R(gpuRecommendedMHz) R(gpuStableMaxMHz) R(gpuLastPerfMilli)
        R(gpuRamTrial) R(gpuRamOriginalRam) R(gpuRamOriginalGpu) R(gpuRamOriginalMv) R(gpuRamOriginalSoc) R(gpuRamOriginalVdd2Uv)
        R(cpuPrepApplied) R(cpuIndex) R(cpuRecommendedMHz) R(cpuStableMaxMHz) R(highUvGood) R(highUvCandidate) R(highUvApplied)
        R(lowUvGood) R(lowUvCandidate) R(lowUvApplied) R(lowLastCostMv) R(lowBestUv) R(lowBestVmin) R(lowBestCostMv) R(lowVminCandidate) R(lowVminApplied)
        R(finalTbreak) R(tbreak2CostMv) R(tbreak3CostMv) R(highVminGood) R(highVminCandidate) R(highVminApplied) R(vmaxGood) R(vmaxCandidate) R(vmaxApplied) R(cpuFinalIndex)
        R(cpuRamTrial) R(cpuRamOriginalRam) R(cpuRamOriginalCpu) R(cpuRamOriginalHighUv) R(cpuRamOriginalSoc) R(cpuRamOriginalVdd2Uv)
        R(rebootPending) R(testRunning) R(testStage)
#undef R
    }
}

void savePoints() {
    ensureDir(APP_DIR);
    std::ofstream f(POINTS_FILE,std::ios::trunc); if(!f) return;
    auto wr=[&](const std::vector<oc::SweepPoint>& v){for(const auto&p:v)f<<int(p.domain)<<','<<p.requestedMHz<<','<<p.realMHz<<','<<p.railMv<<','<<p.auxMv<<','<<p.performance<<','<<p.latencyNs<<','<<p.bandwidthMBs<<','<<p.batteryPowerW<<','<<p.stable<<','<<p.combinedStable<<'\n';};
    wr(ramPoints); wr(gpuPoints); wr(cpuPoints); f.flush(); fsdevCommitDevice("sdmc");
}

void loadPoints() {
    std::ifstream f(POINTS_FILE); if(!f) return; std::string l;
    while(std::getline(f,l)) {
        std::stringstream s(l); std::string a; oc::SweepPoint p; int d=0,stable=0,comb=0;
        auto next=[&](){std::getline(s,a,',');return a;};
        d=std::atoi(next().c_str()); p.domain=oc::Domain(d); p.requestedMHz=std::strtoul(next().c_str(),nullptr,10); p.realMHz=std::atof(next().c_str()); p.railMv=std::strtoul(next().c_str(),nullptr,10); p.auxMv=std::strtoul(next().c_str(),nullptr,10); p.performance=std::atof(next().c_str()); p.latencyNs=std::atof(next().c_str()); p.bandwidthMBs=std::atof(next().c_str()); p.batteryPowerW=std::atof(next().c_str()); stable=std::atoi(next().c_str()); comb=std::atoi(next().c_str()); p.stable=stable; p.combinedStable=comb;
        auto& v = p.domain==oc::Domain::Ram?ramPoints:(p.domain==oc::Domain::Gpu?gpuPoints:cpuPoints); v.push_back(p);
    }
}

void recordPoint(std::vector<oc::SweepPoint>& v, const oc::SweepPoint& p) {
    v.erase(std::remove_if(v.begin(),v.end(),[&](const oc::SweepPoint&q){return q.requestedMHz==p.requestedMHz;}),v.end());
    v.push_back(p); std::sort(v.begin(),v.end(),[](const auto&a,const auto&b){return a.requestedMHz<b.requestedMHz;}); savePoints();
}

int progressStep(Stage s) {
    if(s<=Stage::RamPreparation) return 1;
    if(s<=Stage::RamGraph) return 2;
    if(s<=Stage::RamFinalGraph) return 3;
    if(s<=Stage::GpuRamCombined) return 4;
    if(s<=Stage::CpuTbreak3Test) return 5;
    if(s<=Stage::CpuRamCombined) return 6;
    return 7;
}

bool clockMatch(u32 actual,u32 expected) { return expected==0 || (actual>expected?actual-expected:expected-actual)<=5000000U; }

bool setOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err) {
    Result rc=hocmonSetOverride(HocMonModule_CPU,cpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_GPU,gpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_MEM,ram);
    if(R_FAILED(rc)){char b[64];std::snprintf(b,sizeof(b),"Temporary Override failed: 0x%08X",rc);err=b;return false;}
    svcSleepThread(500'000'000);
    HocMonClocks c{}; rc=hocmonGetTelemetry(&c); if(R_FAILED(rc)){err="Could not verify HOC active values.";return false;}
    if(!clockMatch(c.overrideHz[0],cpu)||!clockMatch(c.overrideHz[1],gpu)||!clockMatch(c.overrideHz[2],ram)||!clockMatch(c.realHz[0],cpu)||!clockMatch(c.realHz[1],gpu)||!clockMatch(c.realHz[2],ram)){
        err="Requested and Real clocks do not match. This candidate may be capped or experiencing a PLL drop.";return false;
    }
    g_active=c; return true;
}

void clearOverrides(){hocmonSetOverride(HocMonModule_CPU,0);hocmonSetOverride(HocMonModule_GPU,0);hocmonSetOverride(HocMonModule_MEM,0);}

bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx){
    g.testRunning=1;g.testStage=int(g.stage);saveState();
    auto r=stress::run(k,seconds,title,ctx);
    g.testRunning=0;g.testStage=-1;saveState();
    return r.outcome==stress::Outcome::Pass;
}

bool requestReboot(Stage next) {
    clearOverrides(); g.stage=next; g.rebootPending=1; saveState();
    gui::ModalView m; m.version=HOC_WIZARD_VERSION; m.eyebrow="SETTINGS SAVED"; m.title="Restart required"; m.body={"The new HOC/KIP values were saved.","The Wizard will continue automatically after reboot."}; m.tone=gui::ModalTone::Amber; gui::presentModal(m); svcSleepThread(400'000'000);
    Result rc=appletRequestToReboot(); if(R_FAILED(rc)){g.rebootPending=0;saveState();g_message="Automatic reboot failed. Restart CFW manually, then reopen the Wizard.";g_errorModal=true;return false;} return true;
}

int ramEndIndex(){
    const int n=int(sizeof(oc::RAM_STEPS_MHZ)/sizeof(oc::RAM_STEPS_MHZ[0]));
    for(int i=n-1;i>=0;--i) if(oc::RAM_STEPS_MHZ[i]<=3400) return i;
    return n-1;
}
int nearestSocFreq(int mhz){int best=SOC_FREQS[0],d=99999;for(int f:SOC_FREQS){int x=std::abs(f-mhz);if(x<d){d=x;best=f;}}return best;}
int nextLowerSocMv(int mv){int best=0;for(int v:SOC_MV){if(v<mv)best=v;else break;}return best;}
int nextHigherSocMv(int mv){for(int v:SOC_MV)if(v>mv)return v;return 0;}
int previousPointMHz(const std::vector<oc::SweepPoint>& pts,int current){int prev=0;for(const auto&p:pts)if(int(p.requestedMHz)<current&&p.stable)prev=std::max(prev,int(p.requestedMHz));return prev;}

void analyzeRam(){auto a=oc::analyzeSweep(ramPoints);if(a.recommended>=0){g.ramRecommendedMHz=int(ramPoints[a.recommended].requestedMHz);g.ramStableMaxMHz=int(ramPoints[a.stableMax].requestedMHz);}saveState();}
void analyzeGpu(){auto a=oc::analyzeSweep(gpuPoints);if(a.recommended>=0){g.gpuRecommendedMHz=int(gpuPoints[a.recommended].requestedMHz);g.gpuStableMaxMHz=int(gpuPoints[a.stableMax].requestedMHz);}saveState();}
void analyzeCpu(){auto a=oc::analyzeSweep(cpuPoints);if(a.recommended>=0){g.cpuRecommendedMHz=int(cpuPoints[a.recommended].requestedMHz);g.cpuStableMaxMHz=int(cpuPoints[a.stableMax].requestedMHz);}saveState();}

std::vector<gui::ChartPoint> chart(const std::vector<oc::SweepPoint>& pts){
    auto a=oc::analyzeSweep(pts);std::vector<gui::ChartPoint> out;for(int i=0;i<int(pts.size());++i){gui::ChartPoint q;q.x=pts[i].requestedMHz;q.performance=pts[i].performance;q.voltage=pts[i].railMv;q.power=0.0;q.stable=pts[i].stable&&pts[i].combinedStable;q.sweetSpot=i==a.sweetSpot;q.stableMax=i==a.stableMax;q.recommended=i==a.recommended;out.push_back(q);}return out;
}

void modalError(const std::string&s){g_message=s;g_errorModal=true;}

bool backupOriginal(){
    if(g.backupDone) return true;
    ensureDir(APP_DIR);ensureDir(BACKUP_DIR);
    bool a=copyFile(HOC_CONFIG,(std::string(BACKUP_DIR)+"/config.ini").c_str());
    bool b=copyFile(HOC_KIP,(std::string(BACKUP_DIR)+"/hoc.kip").c_str());
    if(!a||!b){modalError("Could not create the mandatory HOC safety backup. No tuning values were written.");return false;}
    g.backupDone=1;saveState();return true;
}

void detectHardware(){HocMonHardware h{};Result rc=hocmonGetHardware(&h);if(R_FAILED(rc)){modalError("Horizon OC hardware detection failed.");return;}g.dramId=h.dramId;g.is8GB=h.isDram8GB?1:0;g.consoleType=int(h.consoleType);const auto*p=oc::findRamProfile(h.dramId,h.isDram8GB);g.profileIndex=profileIndex(p);saveState();}

bool batteryReady(u32& pct,PsmChargerType& charger){pct=0;charger=PsmChargerType_Unconnected;if(R_FAILED(psmInitialize()))return false;Result a=psmGetBatteryChargePercentage(&pct);Result b=psmGetChargerType(&charger);psmExit();return R_SUCCEEDED(a)&&R_SUCCEEDED(b);}

void expectedTimings(std::uint32_t t[8]){const auto*p=profile();if(!p){for(int i=0;i<8;++i)t[i]=0;return;}const auto& src=g.ramTimingMode?p->st:p->common;for(int i=0;i<8;++i)t[i]=src.t[i];}

bool guardRamConfig(const char* context){
    const auto*p=profile(); if(!p) return false;
    HocMonOcPreparation d{}; d.uncappedClocks=true; d.hpMode=g.ramHpMode!=0; d.ramMaxKHz=3400000U;
    d.vdd2Uv=u32(g.vdd2Applied?g.vdd2CandidateUv:g.vdd2GoodUv); d.vddqUv=u32((g.vddqApplied?g.vddqCandidateMv:g.vddqGoodMv)*1000);
    d.dvbShift=u32(g.dvbApplied?g.dvbCandidate:g.dvbGood); d.socVmaxUv=1200; expectedTimings(d.timings);
    u32 mm=0; Result rc=hocmonVerifyOcPreparation(&d,&mm);
    if(R_FAILED(rc)||mm!=0){modalError(std::string("Unexpected HOC setting before ")+context+". Restore the Wizard values; do not test with multiple changes at once.");return false;}
    return true;
}

bool guardCpuConfig(int lowUv,int highUv,int tb,int lowVmin,int highVmin,int vmax,int maxClock,const char* context){
    int a,b,c,d,e,f;std::uint32_t gmax;std::string err;
    if(!occonfig::getCpuTuning(a,b,c,d,e,f,gmax,err)||a!=lowUv||b!=highUv||c!=tb||d!=lowVmin||e!=highVmin||f!=vmax||int(gmax)!=maxClock){modalError(std::string("Unexpected CPU setting before ")+context+". Restore the Wizard values first.");return false;}return true;
}

void render() {
    hocmonGetTelemetry(&g_active);
    if(g_errorModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="WIZARD NOTICE";m.title="Action required";m.body={g_message};m.primaryAction="A  OK";m.tone=gui::ModalTone::Red;gui::presentModal(m);return;}
    if(g_recoveryModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED TEST";m.title="Previous candidate did not finish";m.body={"A crash, freeze or reboot occurred while a candidate was being tested.","The Wizard will restore the last known good value before continuing."};m.primaryAction="A  Recover last good value";m.secondaryAction="B  Exit";m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;}

    gui::View v;v.version=HOC_WIZARD_VERSION;v.activeStep=progressStep(g.stage);v.pulse=true;v.haveActiveValues=false;

    auto setValue=[&](int i,const char* label,const std::string& value){v.values[i]={label,value,false};};
    if(g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph){
        v.haveActiveValues=true;
        const int dvbNow=g.dvbApplied?g.dvbCandidate:g.dvbGood;
        setValue(0,"RAM",fmt1(g_active.realHz[2]/1e6)+" MHz");
        setValue(1,"VDD2",fmt1(g_active.vdd2VoltageUv/1000.0)+" mV");
        setValue(2,"VDDQ",fmt1(g_active.vddqVoltageUv/1000.0)+" mV");
        setValue(3,"SoC",fmt1(g_active.socVoltageUv/1000.0)+" mV");
        setValue(4,"DVB Shift",std::to_string(dvbNow));
    }else if(g.stage>=Stage::GpuPreparation && g.stage<=Stage::GpuRamCombined){
        v.haveActiveValues=true;
        setValue(0,"GPU",fmt1(g_active.realHz[1]/1e6)+" MHz");
        setValue(1,"GPU Voltage",fmt1(g_active.gpuVoltageUv/1000.0)+" mV");
        setValue(2,"RAM",fmt1(g_active.realHz[2]/1e6)+" MHz");
        setValue(3,"SoC",fmt1(g_active.socVoltageUv/1000.0)+" mV");
        setValue(4,"VDD2",fmt1(g_active.vdd2VoltageUv/1000.0)+" mV");
    }else if(g.stage>=Stage::CpuPreparation && g.stage<=Stage::CpuRamCombined){
        v.haveActiveValues=true;
        setValue(0,"CPU",fmt1(g_active.realHz[0]/1e6)+" MHz");
        setValue(1,"CPU Voltage",fmt1(g_active.cpuVoltageUv/1000.0)+" mV");
        setValue(2,"RAM",fmt1(g_active.realHz[2]/1e6)+" MHz");
        if(g.stage==Stage::CpuLowUv || g.stage==Stage::CpuLowVmin){
            const int lowUvNow=g.lowUvApplied?g.lowUvCandidate:g.lowUvGood;
            const int lowVminNow=g.lowVminApplied?g.lowVminCandidate:g.lowBestVmin;
            setValue(3,"Low UV",std::to_string(lowUvNow));
            setValue(4,"Low VMIN",std::to_string(lowVminNow)+" mV");
        }else if(g.stage==Stage::CpuTbreak2Set || g.stage==Stage::CpuTbreak2Test || g.stage==Stage::CpuTbreak3Set || g.stage==Stage::CpuTbreak3Test){
            const int tb=(g.stage==Stage::CpuTbreak2Set || g.stage==Stage::CpuTbreak2Test)?2:3;
            const int highUvNow=g.highUvApplied?g.highUvCandidate:g.highUvGood;
            setValue(3,"High UV",std::to_string(highUvNow));
            setValue(4,"TBreak",std::to_string(tb));
        }else if(g.stage==Stage::CpuVmax){
            const int vmaxNow=g.vmaxApplied?g.vmaxCandidate:g.vmaxGood;
            setValue(3,"High UV",std::to_string(g.highUvGood));
            setValue(4,"VMAX",std::to_string(vmaxNow)+" mV");
        }else{
            const int highUvNow=g.highUvApplied?g.highUvCandidate:g.highUvGood;
            const int highVminNow=g.highVminApplied?g.highVminCandidate:g.highVminGood;
            setValue(3,"High UV",std::to_string(highUvNow));
            setValue(4,"High VMIN",std::to_string(highVminNow)+" mV");
        }
    }
    auto print=[&](int row,const std::string&s){gui::printLeft(row,s.c_str());};

    switch(g.stage){
        case Stage::Hardware:{
            const bool detected=g.dramId>=0;
            v.stageTitle="Hardware Detection";
            v.instructionTitle=detected?"Hardware detected":"Detect this console";
            v.instructionLine1=detected?"Review the detected RAM before tuning begins.":"The Wizard will identify the installed RAM and select its HOC table.";
            v.instructionLine2=detected?"A  Continue":"A  Detect hardware";
            gui::begin(v);
            if(!detected){
                print(1,"Detect the installed memory before the OC search starts.");
            }else{
                print(1,"DRAM ID: "+std::to_string(g.dramId));
                if(profile()){
                    print(3,std::string("Detected RAM: ")+profile()->name+"  |  Tier "+profile()->tier);
                    print(4,"Expected Max OC: "+std::to_string(profile()->minMHz)+"-"+std::to_string(profile()->maxMHz)+" MHz");
                    print(6,"The measured stable limit may differ from the expected RAM-class range.");
                }else{
                    print(3,"RAM preset: manual only / unsupported ID");
                    print(4,"Expected Max OC: unavailable");
                }
            }
            print(8,detected?"A : Continue":"A : Detect hardware");
            print(9,"B : Exit");
            gui::present();break;
        }
        case Stage::BenchmarkPrep:{u32 pct=0;PsmChargerType ch=PsmChargerType_Unconnected;bool ok=batteryReady(pct,ch);v.stageTitle="Benchmark Preparation";v.fullWidthLayout=true;gui::begin(v);print(1,"All curve measurements must use the same conditions for meaningful comparisons.");print(3,"Battery: "+(ok?std::to_string(pct)+" %":"unavailable"));print(4,std::string("Charger: ")+(ok&&ch!=PsmChargerType_Unconnected?"connected":"NOT detected"));print(6,"Required: battery 100%, charger connected, brightness fixed at 100%.");print(7,"Battery must read 100% so charging current does not bias benchmark comparisons.");print(9,"Disable screen dimming / system sleep and keep dock/handheld state unchanged.");print(12,"A : Conditions are set / continue");print(13,"B : Exit");gui::present();break;}
        case Stage::RamPreparation:{v.stageTitle="RAM Preparation";v.preparationLayout=true;v.hideValuesCard=true;v.instructionTitle="Set the RAM search baseline";v.instructionLine1="Common timings first; HP and ST are validated after max clock discovery.";v.instructionLine2="Y  Apply automatically";const auto*p=profile();gui::begin(v);if(!p){print(1,"No safe automatic timing profile is available for this DRAM ID.");print(3,"Unknown / ambiguous 8 GB memory is never assigned guessed timings.");print(8,"B : Exit");}else{print(1,"The HOC RAM table supplies starting values only. The console determines the final result.");print(3,std::string("RAM profile: ")+p->name+"  |  expected class "+std::to_string(p->minMHz)+"-"+std::to_string(p->maxMHz)+" MHz");print(5,"Search controls: HP OFF  |  DVB Shift 5  |  SoC VMAX 1200 mV ceiling");print(6,"VDD2: "+std::to_string(p->vdd2Mv)+" mV  |  VDDQ: "+std::to_string(p->vddqMv)+" mV");std::ostringstream t;t<<"Common timings: ";for(int i=0;i<8;++i){if(i)t<<'-';t<<p->common.t[i];}print(7,t.str());print(10,"A : Check manually set values");print(11,"Y : Apply baseline automatically + reboot");print(12,"B : Exit");}gui::present();break;}
        case Stage::RamSweep:{int freq=(g.ramSearchIndex>=0)?int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]):0;v.stageTitle="RAM Clock Search";v.instructionTitle="Test the next RAM clock";v.instructionLine1="Real-clock / PLL check, stability test and Memory Benchmark.";v.instructionLine2="A  Start test";gui::begin(v);print(1,"The table range is guidance, not a hard device limit; search may continue to the HOC safe ceiling.");print(3,"Candidate: "+std::to_string(freq)+" MHz");print(4,"Last stable: "+std::to_string(g.ramStableMaxMHz)+" MHz");print(8,"A : Run candidate test");print(9,"X : Known unstable / stop upward search");print(10,"B : Exit");gui::present();break;}
        case Stage::RamGraph:case Stage::RamFinalGraph:{v.stageTitle=g.stage==Stage::RamGraph?"RAM Capability Result":"RAM Final Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="RAM performance / electrical-cost curve";v.chartXLabel="RAM MHz";v.chartCostLabel="Measured rail cost";v.chartPoints=chart(ramPoints);v.chartSummary="Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz   |   Recommended: "+std::to_string(g.ramRecommendedMHz)+" MHz";gui::begin(v);print(12,"A : Continue");print(13,"B : Exit");gui::present();break;}
        case Stage::RamHpSet:{v.stageTitle="RAM HP Mode";v.instructionTitle="Validate HP Mode after the clock search";v.instructionLine1="HP improves latency but is not assumed stable.";v.instructionLine2="A  Enable HP + reboot";gui::begin(v);print(1,"The maximum clock was found with HP disabled so HP cannot hide the frequency limit.");print(3,"A : Enable HP Mode and validate");print(4,"Y : Keep HP Mode OFF");print(9,"B : Exit");gui::present();break;}
        case Stage::RamHpTest:{v.stageTitle="RAM HP Mode";v.instructionTitle="Validate HP Mode";v.instructionLine1="RAM stability + Memory Benchmark at the recommended clock.";v.instructionLine2="A  Start validation";gui::begin(v);print(1,"If HP fails, the Wizard restores HP OFF before continuing.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStSet:{const auto*p=profile();v.stageTitle="RAM Timing Validation";v.instructionTitle="Try Super Tight timings";v.instructionLine1="ST is attempted only after clock capability and HP are known.";v.instructionLine2="A  Apply ST + reboot";gui::begin(v);if(p){std::ostringstream t;t<<"ST timings: ";for(int i=0;i<8;++i){if(i)t<<'-';t<<p->st.t[i];}print(2,t.str());}print(4,"ST starts with extra DVB reserve. DVB is optimized separately afterward.");print(8,"A : Apply ST + DVB 6 and reboot");print(9,"Y : Keep Common timings");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStTest:{v.stageTitle="RAM Timing Validation";v.instructionTitle="Validate ST timings";v.instructionLine1="RAM stability + Memory Benchmark.";v.instructionLine2="A  Start validation";gui::begin(v);print(1,"If ST fails, Common timings are restored before any other variable changes.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::RamDvb:{v.stageTitle="RAM DVB Optimization";v.instructionTitle=g.dvbApplied?"Test the DVB candidate":"Apply the next DVB candidate";v.instructionLine1="Only DVB changes; first fail restores the previous value.";v.instructionLine2="A  Continue";gui::begin(v);print(3,"Last good DVB: "+std::to_string(g.dvbGood));print(4,"Candidate DVB: "+std::to_string(g.dvbCandidate));print(8,"A : "+std::string(g.dvbApplied?"Run candidate test":"Apply candidate + reboot"));print(9,"X : Keep last good DVB");print(10,"B : Exit");gui::present();break;}
        case Stage::RamVdd2:{v.stageTitle="RAM VDD2 Optimization";v.instructionTitle=g.vdd2Applied?"Test the applied VDD2":"Apply the next VDD2 candidate";v.instructionLine1="One HOC step at a time; VDDQ stays fixed.";v.instructionLine2="A  Continue";gui::begin(v);print(3,"Last good: "+fmtMvUv(g.vdd2GoodUv));print(4,"Candidate: "+fmtMvUv(g.vdd2CandidateUv));print(8,"A : "+std::string(g.vdd2Applied?"Run candidate test":"Apply candidate + reboot"));print(9,"X : Keep last good VDD2");print(10,"B : Exit");gui::present();break;}
        case Stage::RamVddq:{v.stageTitle="RAM VDDQ Optimization";v.instructionTitle=g.vddqApplied?"Test the applied VDDQ":"Apply the next VDDQ candidate";v.instructionLine1="Only VDDQ changes; validated VDD2 stays fixed.";v.instructionLine2="A  Continue";gui::begin(v);print(3,"Last good: "+std::to_string(g.vddqGoodMv)+" mV");print(4,"Candidate: "+std::to_string(g.vddqCandidateMv)+" mV");print(8,"A : "+std::string(g.vddqApplied?"Run candidate test":"Apply candidate + reboot"));print(9,"X : Keep last good VDDQ");print(10,"B : Exit");gui::present();break;}
        case Stage::RamSoc:{v.stageTitle="RAM SoC Voltage Optimization";v.instructionTitle=g.socApplied?"Test the applied SoC voltage":"Apply the next SoC candidate";v.instructionLine1="Only the SoC table point used by the chosen RAM clock changes.";v.instructionLine2="A  Continue";gui::begin(v);print(3,"Table point: "+std::to_string(g.socTableMHz)+" MHz");print(4,"Last good: "+std::to_string(g.socGoodMv)+" mV");print(5,"Candidate: "+std::to_string(g.socCandidateMv)+" mV");print(8,"A : "+std::string(g.socApplied?"Run candidate test":"Apply candidate + reboot"));print(9,"X : Keep last good SoC voltage");print(10,"B : Exit");gui::present();break;}
        case Stage::GpuPreparation:{v.stageTitle="GPU Preparation";v.instructionTitle="Create a conservative GPU capability baseline";v.instructionLine1="High UV table; each clock must prove real frequency before voltage tuning.";v.instructionLine2="A  Apply + reboot";gui::begin(v);print(1,"GPU points start at the automatic 825 mV HOC threshold, then each stable point is reduced in 5 mV steps.");print(3,"Automatic clock search: 768-1382 MHz within HOC's Mariko safe clock envelope.");print(4,"Stable Max and Daily Recommended are calculated from this console's own measured curve.");print(8,"A : Apply GPU capability baseline + reboot");print(10,"B : Exit");gui::present();break;}
        case Stage::GpuTune:{int f=GPU_FREQS[std::clamp(g.gpuIndex,0,int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0]))-1)];v.stageTitle="GPU Voltage Curve";v.instructionTitle=!g.gpuHaveBaseline?"Verify this GPU clock at the safe search ceiling":(g.gpuApplied==2?"Measure the restored stable point":(g.gpuApplied?"Test the voltage candidate":"Apply the next voltage candidate"));v.instructionLine1=!g.gpuHaveBaseline?"Real clock + stability + Benchmark Toolbox FPS must pass first.":(g.gpuApplied==2?"The last stable voltage is active after reboot.":"Stability verifier first, Benchmark Toolbox FPS second.");v.instructionLine2="A  Continue";gui::begin(v);print(1,"Base RAM is used here so a high-RAM DVFS floor cannot hide the intrinsic GPU curve.");print(3,"GPU clock: "+std::to_string(f)+" MHz");if(!g.gpuHaveBaseline){print(4,"Capability ceiling: "+std::to_string(GPU_AUTO_VMAX_MV)+" mV");print(5,"A fail or capped Real Clock ends the upward GPU clock search.");}else{print(4,"Last good: "+std::to_string(g.gpuGoodMv)+" mV");if(g.gpuApplied!=2)print(5,"Candidate: "+std::to_string(g.gpuCandidateMv)+" mV");}print(8,"A : Continue");if(g.gpuHaveBaseline&&g.gpuApplied!=2)print(9,"X : Keep last good voltage for this point");print(10,"B : Exit");gui::present();break;}
        case Stage::GpuGraph:{v.stageTitle="GPU Sweep Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="GPU Benchmark FPS / voltage curve";v.chartXLabel="GPU MHz";v.chartCostLabel="GPU mV";v.chartPoints=chart(gpuPoints);v.chartSummary="Stable Max: "+std::to_string(g.gpuStableMaxMHz)+" MHz   |   Daily Recommended: "+std::to_string(g.gpuRecommendedMHz)+" MHz";gui::begin(v);print(12,"A : Continue to GPU + RAM validation");print(13,"B : Exit");gui::present();break;}
        case Stage::GpuRamCombined:{v.stageTitle="GPU + RAM Integration";v.instructionTitle="Validate the two measured recommendations together";v.instructionLine1="After a fail, only one domain is changed and ineffective changes are restored.";v.instructionLine2="A  Start / continue diagnosis";gui::begin(v);print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"GPU: "+std::to_string(g.gpuRecommendedMHz)+" MHz");if(g.gpuRamTrial==1)print(6,"Diagnostic: GPU voltage +10 mV only.");else if(g.gpuRamTrial==2)print(6,"Diagnostic: GPU restored; SoC one step higher.");else if(g.gpuRamTrial==3)print(6,"Diagnostic: SoC restored; VDD2 one step higher.");else if(g.gpuRamTrial==4)print(6,"Diagnostic: VDD2 restored; RAM one clock step lower.");else if(g.gpuRamTrial==5)print(6,"Diagnostic: RAM restored; GPU one clock step lower.");print(8,"A : Run combined validation");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuPreparation:{v.stageTitle="CPU Preparation";v.instructionTitle="Find the usable CPU range first";v.instructionLine1="Conservative CPU voltage settings prevent false RAM-vs-CPU attribution.";v.instructionLine2="A  Apply + reboot";gui::begin(v);print(1,"The CPU maximum is not assumed. The Wizard measures this console from 1683 MHz upward.");print(3,"Start: High UV 5 | TBreak 1683 | Low VMIN 620 | High VMIN 870 | VMAX 1120");print(8,"A : Apply conservative CPU baseline + reboot");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuSweep:{int f=CPU_FREQS[std::clamp(g.cpuIndex,0,int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0]))-1)];v.stageTitle="CPU Capability Sweep";v.instructionTitle="Measure CPU performance with final RAM active";v.instructionLine1="Combined stability + CPU Ray Trace FPS + Real Clock.";v.instructionLine2="A  Start measurement";gui::begin(v);print(1,"The first unstable/capped point stops the upward capability search.");print(3,"CPU candidate: "+std::to_string(f)+" MHz");print(4,"Current RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Run measurement");print(9,"X : Known unstable / stop CPU sweep");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuHighUv:{v.stageTitle="CPU High UV Search";v.instructionTitle=g.highUvApplied?"Validate this High UV across the whole High range":"Apply the next High UV level";v.instructionLine1="Every measured High frequency is screened; a mid-curve fail counts.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"A High UV level is accepted only if all retained High CPU points pass with final RAM.");print(3,"Last good High UV: "+std::to_string(g.highUvGood));print(4,"Candidate High UV: "+std::to_string(g.highUvCandidate));print(8,"A : "+std::string(g.highUvApplied?"Run full High-range validation":"Apply candidate + reboot"));print(9,"X : Keep last good High UV");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuLowUv:{v.stageTitle="CPU Low UV Search";v.instructionTitle=g.lowUvApplied?"Validate this Low UV at both Low anchors":"Apply the next Low UV level";v.instructionLine1="1020 MHz and the upper Low point are tested with final RAM.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"Low UV is not judged from one idle/low clock. Both ends of the Low curve must work.");print(3,"Last good Low UV: "+std::to_string(g.lowUvGood));print(4,"Candidate Low UV: "+std::to_string(g.lowUvCandidate)+" @ 620 mV VMIN");print(8,"A : Continue");print(9,"X : Keep last good Low UV");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuLowVmin:{v.stageTitle="CPU Low VMIN / UV Pair";v.instructionTitle=g.lowVminApplied?"Validate this Low pair":"Apply the next Low pair";v.instructionLine1="VMIN and Low UV are treated as an interacting pair, not two independent minima.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"If a lower VMIN fails, the Wizard can try one less-aggressive Low UV at the same VMIN.");print(3,"Working pair: Low UV "+std::to_string(g.lowUvGood)+" / "+std::to_string(g.lowVminCandidate)+" mV");print(4,"Best measured pair: UV "+std::to_string(g.lowBestUv)+" / "+std::to_string(g.lowBestVmin)+" mV");print(8,"A : Continue");print(9,"X : Finish with best measured pair");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuTbreak2Set:case Stage::CpuTbreak3Set:{int tb=g.stage==Stage::CpuTbreak2Set?1581:1683;v.stageTitle="CPU TBreak Selection";v.instructionTitle="Apply "+std::to_string(tb)+" MHz TBreak";v.instructionLine1="The split is selected only after Low and High curves are known.";v.instructionLine2="A  Apply + reboot";gui::begin(v);print(1,"The Wizard compares real voltage and stability on both sides of the table boundary.");print(3,"Candidate TBreak: "+std::to_string(tb)+" MHz");print(8,"A : Apply candidate + reboot");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuTbreak2Test:case Stage::CpuTbreak3Test:{int tb=g.stage==Stage::CpuTbreak2Test?1581:1683;v.stageTitle="CPU TBreak Selection";v.instructionTitle="Measure this TBreak";v.instructionLine1="1581 and 1683 MHz are both checked with final RAM.";v.instructionLine2="A  Run boundary comparison";gui::begin(v);print(3,"Active TBreak: "+std::to_string(tb)+" MHz");print(8,"A : Run comparison");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuHighVmin:{v.stageTitle="CPU High VMIN";v.instructionTitle=g.highVminApplied?"Test the High VMIN candidate":"Apply the next High VMIN candidate";v.instructionLine1="This is tuned after TBreak so the lower High anchor is known.";v.instructionLine2="A  Continue";gui::begin(v);print(3,"Last good: "+std::to_string(g.highVminGood)+" mV");print(4,"Candidate: "+std::to_string(g.highVminCandidate)+" mV");print(5,"Wizard floor: 720 mV (current HOC guidance)");print(8,"A : Continue");print(9,"X : Keep last good High VMIN");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuVmax:{v.stageTitle="CPU VMAX";v.instructionTitle=g.vmaxApplied?"Test the VMAX candidate":"Apply the next VMAX candidate";v.instructionLine1="VMAX is last. Requested AND Real CPU clock must remain equal.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"A lower Real Clock means the cap is too low; that is not a successful undervolt.");print(3,"Last good VMAX: "+std::to_string(g.vmaxGood)+" mV");if(g.vmaxCandidate>0)print(4,"Candidate: "+std::to_string(g.vmaxCandidate)+" mV");print(5,"Top retained CPU: "+std::to_string(g.cpuStableMaxMHz)+" MHz");print(8,"A : Continue");print(9,"X : Keep last good VMAX");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuFinalSweep:{int f=CPU_FREQS[std::clamp(g.cpuFinalIndex,0,int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0]))-1)];v.stageTitle="CPU Final Measurement";v.instructionTitle="Re-measure the finished CPU curve";v.instructionLine1="Final High UV, TBreak, VMIN and VMAX are now active.";v.instructionLine2="A  Measure next point";gui::begin(v);print(3,"CPU point: "+std::to_string(f)+" MHz");print(4,"Final RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Run final measurement");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuGraph:{v.stageTitle="CPU Final Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="CPU Ray Trace FPS / final voltage curve";v.chartXLabel="CPU MHz";v.chartCostLabel="CPU mV";v.chartPoints=chart(cpuPoints);v.chartSummary="Stable Max: "+std::to_string(g.cpuStableMaxMHz)+" MHz   |   Recommended: "+std::to_string(g.cpuRecommendedMHz)+" MHz   |   TBreak: "+std::to_string(g.finalTbreak==2?1581:1683)+" MHz";gui::begin(v);print(12,"A : Continue to final CPU + RAM validation");print(13,"B : Exit");gui::present();break;}
        case Stage::CpuRamCombined:{v.stageTitle="CPU + RAM Integration";v.instructionTitle="Longer final combined validation";v.instructionLine1="A fail reopens earlier choices one domain at a time.";v.instructionLine2="A  Start / continue diagnosis";gui::begin(v);print(3,"CPU: "+std::to_string(g.cpuRecommendedMHz)+" MHz");print(4,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");if(g.cpuRamTrial==1)print(6,"Diagnostic: High UV one step safer only.");else if(g.cpuRamTrial==2)print(6,"Diagnostic: CPU restored; SoC one step higher.");else if(g.cpuRamTrial==3)print(6,"Diagnostic: SoC restored; VDD2 one step higher.");else if(g.cpuRamTrial==4)print(6,"Diagnostic: VDD2 restored; RAM one clock step lower.");else if(g.cpuRamTrial==5)print(6,"Diagnostic: RAM restored; CPU one clock step lower.");print(8,"A : Run 5 minute combined validation");print(10,"B : Exit");gui::present();break;}
        case Stage::Finalize:{v.stageTitle="Final Profile";v.fullWidthLayout=true;gui::begin(v);print(1,"The result is derived from this console's measured curves and combined tests.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz | "+(g.ramTimingMode?"Super Tight":"Common")+" | HP "+(g.ramHpMode?"ON":"OFF")+" | DVB "+std::to_string(g.dvbGood));print(4,"VDD2: "+fmtMvUv(g.vdd2GoodUv)+" | VDDQ: "+std::to_string(g.vddqGoodMv)+" mV | SoC: "+std::to_string(g.socGoodMv)+" mV");print(5,"GPU: "+std::to_string(g.gpuRecommendedMHz)+" MHz");print(6,"CPU: "+std::to_string(g.cpuRecommendedMHz)+" MHz | Low UV "+std::to_string(g.lowBestUv)+" / "+std::to_string(g.lowBestVmin)+" mV | High UV "+std::to_string(g.highUvGood));print(7,"TBreak: "+std::to_string(g.finalTbreak==2?1581:1683)+" MHz | High VMIN "+std::to_string(g.highVminGood)+" mV | VMAX "+std::to_string(g.vmaxGood)+" mV");print(10,"A : Save current HOC files to Performance Modes · OC Mode");print(12,"B : Exit");gui::present();break;}
        case Stage::Complete:{v.stageTitle="Complete";v.fullWidthLayout=true;gui::begin(v);print(1,"OVERCLOCKING COMPLETE");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"GPU: "+std::to_string(g.gpuRecommendedMHz)+" MHz");print(5,"CPU: "+std::to_string(g.cpuRecommendedMHz)+" MHz");print(6,"CPU Low UV: "+std::to_string(g.lowBestUv)+" | High UV: "+std::to_string(g.highUvGood));print(7,"TBreak: "+std::to_string(g.finalTbreak==2?1581:1683)+" MHz | VMAX: "+std::to_string(g.vmaxGood)+" mV");print(9,"Saved to Performance Modes · OC Mode");print(12,"B : Exit");gui::present();break;}
    }
}

bool prepareRamAuto(){
    const auto*p=profile();if(!p){modalError("No automatic RAM profile is available for this memory.");return false;}if(!backupOriginal())return false;
    std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=p->common.t[i];std::string e;
    if(!occonfig::setRamPreparation(false,3400,p->vdd2Mv,p->vddqMv,5,1200,t,e)){modalError(e);return false;}
    g.ramHpMode=0;g.ramTimingMode=0;g.dvbGood=5;g.dvbCandidate=4;g.vdd2GoodUv=int(p->vdd2Mv*1000);g.vdd2CandidateUv=g.vdd2GoodUv-12500;g.vddqGoodMv=int(p->vddqMv);g.vddqCandidateMv=g.vddqGoodMv-10;g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex();saveState();return requestReboot(Stage::RamSweep);
}

void finishRamSweep(){analyzeRam();if(g.ramRecommendedMHz<=0){modalError("No stable RAM point was measured.");return;}g.stage=Stage::RamGraph;saveState();}

void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){finishRamSweep();return;}
    if(!runStress(stress::Kind::Ram,45,"RAM Clock Stability","RAM "+std::to_string(freq)+" MHz")){finishRamSweep();return;}
    auto b=ocbench::runRam();if(!b.ok){finishRamSweep();return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB5";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}

void validateHp(){
    std::string e;if(!guardRamConfig("HP validation"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    bool pass=runStress(stress::Kind::Ram,60,"RAM HP Mode Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz");auto b=pass?ocbench::runRam():ocbench::RamResult{};
    if(pass&&b.ok){g.ramHpMode=1;g.stage=Stage::RamStSet;saveState();}
    else{if(!occonfig::setHpMode(false,e)){modalError(e);return;}g.ramHpMode=0;saveState();requestReboot(Stage::RamStSet);}
}

void validateSt(){
    std::string e;if(!guardRamConfig("ST validation"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    bool pass=runStress(stress::Kind::Ram,60,"RAM Super Tight Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz");auto b=pass?ocbench::runRam():ocbench::RamResult{};
    if(pass&&b.ok){g.ramTimingMode=1;g.dvbGood=6;g.dvbCandidate=5;g.dvbApplied=0;g.stage=Stage::RamDvb;saveState();}
    else{const auto*pr=profile();if(!pr){modalError("Cannot restore Common timings.");return;}std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];if(!occonfig::setRamTimings(t,e)||!occonfig::setDvbShift(5,e)){modalError(e);return;}g.ramTimingMode=0;g.dvbGood=5;g.dvbCandidate=4;g.dvbApplied=0;saveState();requestReboot(Stage::RamDvb);}
}

void runDvb(){
    std::string e;if(!g.dvbApplied){if(g.dvbCandidate<1){g.stage=Stage::RamVdd2;saveState();return;}if(!occonfig::setDvbShift(g.dvbCandidate,e)){modalError(e);return;}g.dvbApplied=1;saveState();requestReboot(Stage::RamDvb);return;}
    if(!guardRamConfig("DVB test"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    if(runStress(stress::Kind::Ram,60,"DVB Stability","DVB "+std::to_string(g.dvbCandidate))){g.dvbGood=g.dvbCandidate;g.dvbCandidate--;g.dvbApplied=0;saveState();}
    else{if(!occonfig::setDvbShift(g.dvbGood,e)){modalError(e);return;}g.dvbApplied=0;saveState();requestReboot(Stage::RamVdd2);}
}

void runVdd2(){std::string e;if(!g.vdd2Applied){if(g.vdd2CandidateUv<VDD2_MIN_UV){g.stage=Stage::RamVddq;saveState();return;}if(!occonfig::setVdd2Uv(g.vdd2CandidateUv,e)){modalError(e);return;}g.vdd2Applied=1;saveState();requestReboot(Stage::RamVdd2);return;}if(!guardRamConfig("VDD2 test"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(runStress(stress::Kind::Ram,60,"VDD2 Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.vdd2GoodUv=g.vdd2CandidateUv;g.vdd2CandidateUv-=12500;g.vdd2Applied=0;saveState();}else{if(!occonfig::setVdd2Uv(g.vdd2GoodUv,e)){modalError(e);return;}g.vdd2Applied=0;saveState();requestReboot(Stage::RamVddq);}}
void runVddq(){std::string e;if(!g.vddqApplied){if(g.vddqCandidateMv<VDDQ_MIN_MV){g.stage=Stage::RamSoc;saveState();return;}if(!occonfig::setVddq(g.vddqCandidateMv,e)){modalError(e);return;}g.vddqApplied=1;saveState();requestReboot(Stage::RamVddq);return;}if(!guardRamConfig("VDDQ test"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(runStress(stress::Kind::Ram,60,"VDDQ Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.vddqGoodMv=g.vddqCandidateMv;g.vddqCandidateMv-=10;g.vddqApplied=0;saveState();}else{if(!occonfig::setVddq(g.vddqGoodMv,e)){modalError(e);return;}g.vddqApplied=0;saveState();requestReboot(Stage::RamSoc);}}

void initSoc(){if(g.socGoodMv>0)return;std::string e;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}HocMonClocks c{};hocmonGetTelemetry(&c);g.socTableMHz=nearestSocFreq(g.ramRecommendedMHz);g.socGoodMv=int(std::round(c.socVoltageUv/1000.0));if(g.socGoodMv<637){if(!occonfig::getSocPoint(g.socTableMHz,g.socGoodMv,e)){modalError(e);return;}}g.socCandidateMv=nextLowerSocMv(g.socGoodMv);saveState();}
void runSoc(){initSoc();if(g_errorModal)return;std::string e;if(!g.socApplied){if(g.socCandidateMv<637||g.socCandidateMv<=0){g.stage=Stage::RamFinalGraph;saveState();return;}if(!occonfig::setSocPoint(g.socTableMHz,g.socCandidateMv,e)){modalError(e);return;}g.socApplied=1;saveState();requestReboot(Stage::RamSoc);return;}if(!guardRamConfig("SoC test"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(runStress(stress::Kind::Ram,60,"SoC Voltage Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.socGoodMv=g.socCandidateMv;g.socCandidateMv=nextLowerSocMv(g.socGoodMv);g.socApplied=0;saveState();}else{if(!occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e)){modalError(e);return;}g.socApplied=0;saveState();requestReboot(Stage::RamFinalGraph);}}

bool prepareGpu(){
    if(!backupOriginal())return false;
    std::string e;
    if(!occonfig::setGpuUvTable(4,e)||!occonfig::setGpuVmin(580,e)||!occonfig::setGpuVmax(GPU_AUTO_VMAX_MV,e)){modalError(e);return false;}
    for(int f:GPU_FREQS){if(f>GPU_SAFE_MAX_MHZ)break;if(!occonfig::setGpuPoint(f,GPU_AUTO_VMAX_MV,e)){modalError(e);return false;}}
    g.gpuPrepApplied=1;g.gpuIndex=0;g.gpuHaveBaseline=0;g.gpuGoodMv=GPU_AUTO_VMAX_MV;g.gpuCandidateMv=GPU_AUTO_VMAX_MV-5;g.gpuApplied=0;saveState();
    return requestReboot(Stage::GpuTune);
}

void finishGpuSweep(){
    analyzeGpu();
    if(g.gpuRecommendedMHz<=0){modalError("No stable GPU point was measured inside the automatic safety envelope.");return;}
    g.stage=Stage::GpuGraph;saveState();
}

void finishGpuPoint(){
    int f=GPU_FREQS[g.gpuIndex];std::string e;
    if(!setOverrides(CPU_BASE_HZ,u32(f)*1000000U,RAM_BASE_HZ,e)){modalError(e);return;}
    auto b=ocbench::runGpu(7);if(!b.ok){modalError(b.error);return;}
    oc::SweepPoint p;p.domain=oc::Domain::Gpu;p.requestedMHz=f;p.realMHz=b.telemetry.realGpuMHz;p.railMv=g.gpuGoodMv;p.performance=b.fps;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Base RAM intrinsic GPU curve";recordPoint(gpuPoints,p);
    ++g.gpuIndex;g.gpuHaveBaseline=0;g.gpuGoodMv=GPU_AUTO_VMAX_MV;g.gpuCandidateMv=GPU_AUTO_VMAX_MV-5;g.gpuApplied=0;
    if(g.gpuIndex>=int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0])))finishGpuSweep();else saveState();
}

void runGpuTune(){
    if(g.gpuIndex>=int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0]))){finishGpuSweep();return;}
    int f=GPU_FREQS[g.gpuIndex];
    if(f>GPU_SAFE_MAX_MHZ){finishGpuSweep();return;}
    std::string e;

    // First prove this clock can really run at the conservative automatic
    // voltage ceiling. A capped/unstable baseline ends the upward clock search;
    // it is not mislabelled as a voltage-undervolt failure.
    if(!g.gpuHaveBaseline){
        if(!setOverrides(CPU_BASE_HZ,u32(f)*1000000U,RAM_BASE_HZ,e)){
            if(e.find("Requested and Real clocks do not match")!=std::string::npos){finishGpuSweep();return;}
            modalError(e);return;
        }
        if(!runStress(stress::Kind::Gpu,45,"GPU Capability Baseline","GPU "+std::to_string(f)+" MHz @ "+std::to_string(GPU_AUTO_VMAX_MV)+" mV")){finishGpuSweep();return;}
        auto b=ocbench::runGpu(5);if(!b.ok){modalError(b.error);return;}
        if(std::abs(b.telemetry.realGpuMHz-f)>5.0){finishGpuSweep();return;}
        g.gpuGoodMv=GPU_AUTO_VMAX_MV;g.gpuCandidateMv=GPU_AUTO_VMAX_MV-5;g.gpuHaveBaseline=1;g.gpuApplied=0;saveState();return;
    }

    // state 2 means a failed/capped candidate was restored and rebooted;
    // benchmark the actual last-good voltage before advancing.
    if(g.gpuApplied==2){finishGpuPoint();return;}

    if(g.gpuApplied==0){
        if(g.gpuCandidateMv<GPU_MIN_MV){finishGpuPoint();return;}
        if(!occonfig::setGpuPoint(f,g.gpuCandidateMv,e)){modalError(e);return;}
        g.gpuApplied=1;saveState();requestReboot(Stage::GpuTune);return;
    }

    if(!setOverrides(CPU_BASE_HZ,u32(f)*1000000U,RAM_BASE_HZ,e)){
        // A lower voltage can make HOC/PCV cap real frequency. Treat that
        // exactly like instability: restore the last-good point.
        if(!occonfig::setGpuPoint(f,g.gpuGoodMv,e)){modalError(e);return;}
        g.gpuApplied=2;saveState();requestReboot(Stage::GpuTune);return;
    }
    bool pass=runStress(stress::Kind::Gpu,45,"GPU Voltage Stability","GPU "+std::to_string(f)+" MHz @ "+std::to_string(g.gpuCandidateMv)+" mV");
    if(pass){g.gpuGoodMv=g.gpuCandidateMv;g.gpuCandidateMv-=5;g.gpuApplied=0;saveState();}
    else{if(!occonfig::setGpuPoint(f,g.gpuGoodMv,e)){modalError(e);return;}g.gpuApplied=2;saveState();requestReboot(Stage::GpuTune);}
}

void runGpuRam(){
    std::string e;int gpuMv=0;if(!occonfig::getGpuPoint(g.gpuRecommendedMHz,gpuMv,e)){modalError(e);return;}
    if(!setOverrides(CPU_BASE_HZ,u32(g.gpuRecommendedMHz)*1000000U,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    bool pass=runStress(stress::Kind::Gpu,90,"GPU + RAM Integration","GPU "+std::to_string(g.gpuRecommendedMHz)+" | RAM "+std::to_string(g.ramRecommendedMHz));
    if(pass){g.gpuRamTrial=0;g.stage=Stage::CpuPreparation;saveState();return;}

    if(g.gpuRamTrial==0){g.gpuRamOriginalRam=g.ramRecommendedMHz;g.gpuRamOriginalGpu=g.gpuRecommendedMHz;g.gpuRamOriginalMv=gpuMv;g.gpuRamOriginalSoc=g.socGoodMv;g.gpuRamOriginalVdd2Uv=g.vdd2GoodUv;if(!occonfig::setGpuPoint(g.gpuRecommendedMHz,std::min(800,gpuMv+10),e)){modalError(e);return;}g.gpuRamTrial=1;saveState();requestReboot(Stage::GpuRamCombined);return;}
    if(g.gpuRamTrial==1){if(!occonfig::setGpuPoint(g.gpuRamOriginalGpu,g.gpuRamOriginalMv,e)){modalError(e);return;}int up=nextHigherSocMv(g.gpuRamOriginalSoc);if(up>0&&occonfig::setSocPoint(g.socTableMHz,up,e)){g.socGoodMv=up;g.gpuRamTrial=2;saveState();requestReboot(Stage::GpuRamCombined);return;}}
    if(g.gpuRamTrial==2){if(!occonfig::setSocPoint(g.socTableMHz,g.gpuRamOriginalSoc,e)){modalError(e);return;}g.socGoodMv=g.gpuRamOriginalSoc;if(!occonfig::setVdd2Uv(g.gpuRamOriginalVdd2Uv+12500,e)){modalError(e);return;}g.vdd2GoodUv=g.gpuRamOriginalVdd2Uv+12500;g.gpuRamTrial=3;saveState();requestReboot(Stage::GpuRamCombined);return;}
    if(g.gpuRamTrial==3){if(!occonfig::setVdd2Uv(g.gpuRamOriginalVdd2Uv,e)){modalError(e);return;}g.vdd2GoodUv=g.gpuRamOriginalVdd2Uv;int lower=previousPointMHz(ramPoints,g.gpuRamOriginalRam);if(lower>0){g.ramRecommendedMHz=lower;g.gpuRamTrial=4;saveState();return;}}
    if(g.gpuRamTrial==4){g.ramRecommendedMHz=g.gpuRamOriginalRam;int lower=previousPointMHz(gpuPoints,g.gpuRamOriginalGpu);if(lower>0){g.gpuRecommendedMHz=lower;g.gpuRamTrial=5;saveState();return;}}
    modalError("GPU + RAM remains unstable after isolated GPU, SoC, VDD2, RAM and GPU-clock checks. Review the measured curves before continuing.");
}

bool prepareCpu(){
    std::string e;if(!occonfig::setCpuTuning(0,5,3,620,870,CPU_VMAX_SAFE,CPU_SAFE_MAX_MHZ,e)){modalError(e);return false;}
    g.cpuPrepApplied=1;g.cpuIndex=0;g.highUvGood=5;g.highUvCandidate=6;g.highUvApplied=0;g.lowUvGood=0;g.lowUvCandidate=1;g.lowVminCandidate=610;g.highVminGood=870;g.highVminCandidate=850;g.vmaxGood=CPU_VMAX_SAFE;g.vmaxCandidate=0;saveState();return requestReboot(Stage::CpuSweep);
}

void finishCpuCapability(){
    analyzeCpu();if(g.cpuStableMaxMHz<=0){modalError("No stable High CPU point was measured.");return;}g.highUvGood=5;g.highUvCandidate=6;g.highUvApplied=0;g.stage=Stage::CpuHighUv;saveState();
}

void runCpuCapability(){
    if(g.cpuIndex>=int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0]))){finishCpuCapability();return;}int f=CPU_FREQS[g.cpuIndex];if(f>CPU_SAFE_MAX_MHZ){finishCpuCapability();return;}std::string e;
    if(!guardCpuConfig(0,5,3,620,870,CPU_VMAX_SAFE,CPU_SAFE_MAX_MHZ,"CPU capability test"))return;
    if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){finishCpuCapability();return;}
    if(!runStress(stress::Kind::Combined,60,"CPU Capability Stability","CPU "+std::to_string(f)+" MHz + RAM "+std::to_string(g.ramRecommendedMHz))){finishCpuCapability();return;}
    auto b=ocbench::runCpu(7);if(!b.ok||std::abs(b.telemetry.realCpuMHz-f)>5.0){finishCpuCapability();return;}
    oc::SweepPoint p;p.domain=oc::Domain::Cpu;p.requestedMHz=f;p.realMHz=b.telemetry.realCpuMHz;p.railMv=std::uint32_t(std::round(b.telemetry.cpuMv));p.performance=b.fps;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Conservative CPU capability sweep + final RAM";recordPoint(cpuPoints,p);g.cpuStableMaxMHz=f;if(++g.cpuIndex>=int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0])))finishCpuCapability();else saveState();
}

bool testHighUvCurve(){
    std::string e;for(int f:CPU_FREQS){if(f>g.cpuStableMaxMHz)break;if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){return false;}if(!runStress(stress::Kind::Combined,30,"CPU High UV Screening","CPU "+std::to_string(f)+" MHz | High UV "+std::to_string(g.highUvCandidate)))return false;}return true;
}

void runHighUv(){
    std::string e;if(!g.highUvApplied){if(g.highUvCandidate>12){g.stage=Stage::CpuLowUv;saveState();return;}if(!occonfig::setCpuTuning(0,g.highUvCandidate,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.highUvApplied=1;saveState();requestReboot(Stage::CpuHighUv);return;}
    if(testHighUvCurve()){g.highUvGood=g.highUvCandidate;++g.highUvCandidate;g.highUvApplied=0;saveState();}
    else{if(!occonfig::setCpuTuning(0,g.highUvGood,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.highUvApplied=0;g.lowUvGood=0;g.lowUvCandidate=1;saveState();requestReboot(Stage::CpuLowUv);}
}

bool testLowPair(int uv,int vmin,int&cost){
    std::string e;cost=0;for(int f:{1020,1428}){if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e))return false;if(!runStress(stress::Kind::Combined,60,"CPU Low Curve Stability","CPU "+std::to_string(f)+" MHz | UV "+std::to_string(uv)+" / "+std::to_string(vmin)+" mV"))return false;HocMonClocks c{};if(R_FAILED(hocmonGetTelemetry(&c)))return false;cost+=int(std::round(c.cpuVoltageUv/1000.0));}return true;
}

void beginLowVmin(){
    g.lowBestUv=g.lowUvGood;g.lowBestVmin=620;g.lowBestCostMv=g.lowLastCostMv>0?g.lowLastCostMv:99999;g.lowVminCandidate=610;g.lowVminApplied=0;g.stage=Stage::CpuLowVmin;saveState();
}

void runLowUv(){
    std::string e;if(!g.lowUvApplied){if(g.lowUvCandidate>8){beginLowVmin();return;}if(!occonfig::setCpuTuning(g.lowUvCandidate,g.highUvGood,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.lowUvApplied=1;saveState();requestReboot(Stage::CpuLowUv);return;}
    int cost=0;if(testLowPair(g.lowUvCandidate,620,cost)){g.lowUvGood=g.lowUvCandidate;g.lowLastCostMv=cost;++g.lowUvCandidate;g.lowUvApplied=0;saveState();}
    else{if(!occonfig::setCpuTuning(g.lowUvGood,g.highUvGood,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.lowUvApplied=0;beginLowVmin();requestReboot(Stage::CpuLowVmin);}
}

void applyBestLowAndContinue(){
    std::string e;g.lowUvGood=g.lowBestUv;if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,3,g.lowBestVmin,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.lowVminApplied=0;saveState();requestReboot(Stage::CpuTbreak2Set);
}

void runLowVmin(){
    std::string e;if(g.lowVminCandidate<CPU_LOW_VMIN_FLOOR){applyBestLowAndContinue();return;}
    if(!g.lowVminApplied){if(!occonfig::setCpuTuning(g.lowUvGood,g.highUvGood,3,g.lowVminCandidate,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.lowVminApplied=1;saveState();requestReboot(Stage::CpuLowVmin);return;}
    int cost=0;if(testLowPair(g.lowUvGood,g.lowVminCandidate,cost)){if(cost<g.lowBestCostMv){g.lowBestCostMv=cost;g.lowBestUv=g.lowUvGood;g.lowBestVmin=g.lowVminCandidate;}g.lowVminCandidate-=10;g.lowVminApplied=0;saveState();return;}
    if(g.lowUvGood>0){--g.lowUvGood;g.lowVminApplied=0;saveState();return;}
    applyBestLowAndContinue();
}

bool tbreakBoundaryCost(int&out){std::string e;double sum=0;for(int f:{1581,1683}){if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e))return false;if(!runStress(stress::Kind::Combined,45,"CPU TBreak Boundary","CPU "+std::to_string(f)+" MHz"))return false;HocMonClocks c{};if(R_FAILED(hocmonGetTelemetry(&c)))return false;sum+=c.cpuVoltageUv/1000.0;}out=int(std::round(sum/2.0));return true;}

void beginHighVmin(){g.highVminGood=870;g.highVminCandidate=850;g.highVminApplied=0;g.stage=Stage::CpuHighVmin;saveState();}

void runHighVmin(){
    std::string e;if(g.highVminCandidate<CPU_HIGH_VMIN_FLOOR){g.stage=Stage::CpuVmax;saveState();return;}
    if(!g.highVminApplied){if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminCandidate,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.highVminApplied=1;saveState();requestReboot(Stage::CpuHighVmin);return;}
    int f=g.finalTbreak==2?1581:1683;if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    if(runStress(stress::Kind::Combined,60,"CPU High VMIN Stability","CPU "+std::to_string(f)+" MHz + RAM "+std::to_string(g.ramRecommendedMHz))){g.highVminGood=g.highVminCandidate;g.highVminCandidate-=10;g.highVminApplied=0;saveState();}
    else{if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminGood,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e)){modalError(e);return;}g.highVminApplied=0;saveState();requestReboot(Stage::CpuVmax);}
}

void finishVmax(){
    std::string e;if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminGood,g.vmaxGood,g.cpuStableMaxMHz,e)){modalError(e);return;}g.vmaxApplied=0;g.cpuFinalIndex=0;saveState();requestReboot(Stage::CpuFinalSweep);
}

void runVmax(){
    std::string e;if(g.vmaxCandidate==0){if(!setOverrides(u32(g.cpuStableMaxMHz)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(!runStress(stress::Kind::Combined,45,"CPU VMAX Baseline","CPU "+std::to_string(g.cpuStableMaxMHz)+" MHz")){modalError("Top CPU point is no longer stable before VMAX tuning.");return;}HocMonClocks c{};hocmonGetTelemetry(&c);int actual=int(std::round(c.cpuVoltageUv/10000.0))*10;g.vmaxGood=CPU_VMAX_SAFE;g.vmaxCandidate=std::min(CPU_VMAX_SAFE-10,actual+20);if(g.vmaxCandidate>=CPU_VMAX_SAFE)g.vmaxCandidate=CPU_VMAX_SAFE-10;saveState();return;}
    if(!g.vmaxApplied){if(g.vmaxCandidate<800){finishVmax();return;}if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminGood,g.vmaxCandidate,g.cpuStableMaxMHz,e)){modalError(e);return;}g.vmaxApplied=1;saveState();requestReboot(Stage::CpuVmax);return;}
    bool clocks=setOverrides(u32(g.cpuStableMaxMHz)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e);bool pass=clocks&&runStress(stress::Kind::Combined,60,"CPU VMAX Stability","CPU "+std::to_string(g.cpuStableMaxMHz)+" MHz @ cap "+std::to_string(g.vmaxCandidate)+" mV");HocMonClocks c{};if(clocks)hocmonGetTelemetry(&c);bool realOk=clocks&&clockMatch(c.realHz[0],u32(g.cpuStableMaxMHz)*1000000U);
    if(pass&&realOk){g.vmaxGood=g.vmaxCandidate;g.vmaxCandidate-=10;g.vmaxApplied=0;saveState();}
    else finishVmax();
}

void runCpuFinal(){
    while(g.cpuFinalIndex<int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0]))&&CPU_FREQS[g.cpuFinalIndex]>g.cpuStableMaxMHz)++g.cpuFinalIndex;
    if(g.cpuFinalIndex>=int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0]))){analyzeCpu();g.stage=Stage::CpuGraph;saveState();return;}
    int f=CPU_FREQS[g.cpuFinalIndex];std::string e;if(!guardCpuConfig(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminGood,g.vmaxGood,g.cpuStableMaxMHz,"final CPU measurement"))return;if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(!runStress(stress::Kind::Combined,60,"CPU Final Stability","CPU "+std::to_string(f)+" MHz")){modalError("A point in the final CPU curve failed. Use one step less aggressive High UV and revalidate before continuing.");return;}auto b=ocbench::runCpu(7);if(!b.ok){modalError(b.error);return;}oc::SweepPoint p;p.domain=oc::Domain::Cpu;p.requestedMHz=f;p.realMHz=b.telemetry.realCpuMHz;p.railMv=std::uint32_t(std::round(b.telemetry.cpuMv));p.performance=b.fps;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Final CPU curve + final RAM";recordPoint(cpuPoints,p);++g.cpuFinalIndex;saveState();
}

void runCpuRam(){
    std::string e;if(!setOverrides(u32(g.cpuRecommendedMHz)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}bool pass=runStress(stress::Kind::Combined,300,"CPU + RAM Final Validation","CPU "+std::to_string(g.cpuRecommendedMHz)+" | RAM "+std::to_string(g.ramRecommendedMHz));if(pass){g.cpuRamTrial=0;g.stage=Stage::Finalize;saveState();return;}
    if(g.cpuRamTrial==0){g.cpuRamOriginalRam=g.ramRecommendedMHz;g.cpuRamOriginalCpu=g.cpuRecommendedMHz;g.cpuRamOriginalHighUv=g.highUvGood;g.cpuRamOriginalSoc=g.socGoodMv;g.cpuRamOriginalVdd2Uv=g.vdd2GoodUv;if(g.highUvGood>0&&occonfig::setCpuTuning(g.lowBestUv,g.highUvGood-1,g.finalTbreak,g.lowBestVmin,g.highVminGood,g.vmaxGood,g.cpuStableMaxMHz,e)){g.highUvGood--;g.cpuRamTrial=1;saveState();requestReboot(Stage::CpuRamCombined);return;}}
    if(g.cpuRamTrial==1){g.highUvGood=g.cpuRamOriginalHighUv;if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminGood,g.vmaxGood,g.cpuStableMaxMHz,e)){modalError(e);return;}int up=nextHigherSocMv(g.cpuRamOriginalSoc);if(up>0&&occonfig::setSocPoint(g.socTableMHz,up,e)){g.socGoodMv=up;g.cpuRamTrial=2;saveState();requestReboot(Stage::CpuRamCombined);return;}}
    if(g.cpuRamTrial==2){if(!occonfig::setSocPoint(g.socTableMHz,g.cpuRamOriginalSoc,e)){modalError(e);return;}g.socGoodMv=g.cpuRamOriginalSoc;if(!occonfig::setVdd2Uv(g.cpuRamOriginalVdd2Uv+12500,e)){modalError(e);return;}g.vdd2GoodUv=g.cpuRamOriginalVdd2Uv+12500;g.cpuRamTrial=3;saveState();requestReboot(Stage::CpuRamCombined);return;}
    if(g.cpuRamTrial==3){if(!occonfig::setVdd2Uv(g.cpuRamOriginalVdd2Uv,e)){modalError(e);return;}g.vdd2GoodUv=g.cpuRamOriginalVdd2Uv;int lower=previousPointMHz(ramPoints,g.cpuRamOriginalRam);if(lower>0){g.ramRecommendedMHz=lower;g.cpuRamTrial=4;saveState();return;}}
    if(g.cpuRamTrial==4){g.ramRecommendedMHz=g.cpuRamOriginalRam;int lower=previousPointMHz(cpuPoints,g.cpuRamOriginalCpu);if(lower>0){g.cpuRecommendedMHz=lower;g.cpuRamTrial=5;saveState();return;}}
    modalError("CPU + RAM remains unstable after isolated CPU-UV, SoC, VDD2, RAM-clock and CPU-clock checks. Review the curves before saving a profile.");
}

void saveFinal(){
    ensureDir(PERF_OC_DIR);bool a=copyFile(HOC_CONFIG,(std::string(PERF_OC_DIR)+"/config.ini").c_str());bool b=copyFile(HOC_KIP,(std::string(PERF_OC_DIR)+"/hoc.kip").c_str());std::ofstream f(RESULTS_FILE,std::ios::trunc);
    f<<"HOC Overclocking Wizard "<<HOC_WIZARD_VERSION<<"\n";f<<"RAM="<<g.ramRecommendedMHz<<" MHz\nGPU="<<g.gpuRecommendedMHz<<" MHz\nCPU="<<g.cpuRecommendedMHz<<" MHz\nLowUV="<<g.lowBestUv<<"\nLowVMIN="<<g.lowBestVmin<<" mV\nHighUV="<<g.highUvGood<<"\nTBreak="<<(g.finalTbreak==2?1581:1683)<<" MHz\nHighVMIN="<<g.highVminGood<<" mV\nVMAX="<<g.vmaxGood<<" mV\nVDD2="<<fmtMvUv(g.vdd2GoodUv)<<"\nVDDQ="<<g.vddqGoodMv<<" mV\nSoC="<<g.socGoodMv<<" mV\n";f.flush();fsdevCommitDevice("sdmc");if(!a||!b){modalError("Tuning finished, but Performance Modes OCMode files could not both be saved.");return;}g.stage=Stage::Complete;saveState();
}

void resetAll(){clearOverrides();unlink(STATE_FILE);unlink(POINTS_FILE);unlink(RESULTS_FILE);unlink(DISCLAIMER_FILE);g=State{};ramPoints.clear();gpuPoints.clear();cpuPoints.clear();detectHardware();saveState();}

void recoverInterrupted(){
    g.testRunning=0;g.testStage=-1;std::string e;
    switch(g.stage){
        case Stage::RamDvb:if(g.dvbApplied){occonfig::setDvbShift(g.dvbGood,e);g.dvbApplied=0;requestReboot(Stage::RamVdd2);return;}break;
        case Stage::RamVdd2:if(g.vdd2Applied){occonfig::setVdd2Uv(g.vdd2GoodUv,e);g.vdd2Applied=0;requestReboot(Stage::RamVddq);return;}break;
        case Stage::RamVddq:if(g.vddqApplied){occonfig::setVddq(g.vddqGoodMv,e);g.vddqApplied=0;requestReboot(Stage::RamSoc);return;}break;
        case Stage::RamSoc:if(g.socApplied){occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e);g.socApplied=0;requestReboot(Stage::RamFinalGraph);return;}break;
        case Stage::GpuTune:if(g.gpuApplied==1){int f=GPU_FREQS[g.gpuIndex];occonfig::setGpuPoint(f,g.gpuGoodMv,e);g.gpuApplied=2;saveState();requestReboot(Stage::GpuTune);return;}break;
        case Stage::CpuHighUv:if(g.highUvApplied){occonfig::setCpuTuning(0,g.highUvGood,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e);g.highUvApplied=0;requestReboot(Stage::CpuLowUv);return;}break;
        case Stage::CpuLowUv:if(g.lowUvApplied){occonfig::setCpuTuning(g.lowUvGood,g.highUvGood,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e);g.lowUvApplied=0;requestReboot(Stage::CpuLowVmin);return;}break;
        case Stage::CpuLowVmin:if(g.lowVminApplied){applyBestLowAndContinue();return;}break;
        case Stage::CpuHighVmin:if(g.highVminApplied){occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,g.highVminGood,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e);g.highVminApplied=0;requestReboot(Stage::CpuVmax);return;}break;
        case Stage::CpuVmax:if(g.vmaxApplied){finishVmax();return;}break;
        default:break;
    }
    saveState();
}

} // namespace

int main(int argc,char**argv){
    socketInitializeDefault(); nxlinkStdio();
    ensureDir(APP_DIR); loadState(); loadPoints();
    PadState pad; padConfigureInput(1,HidNpadStyleSet_NpadStandard); padInitializeDefault(&pad);
    if(!gui::init()){socketExit();return 1;}
    appletSetAutoSleepDisabled(true);

    if(updater::startupCheckAndPrompt(pad,argc,argv)){gui::shutdown();socketExit();return 0;}

    if(!fileExists(DISCLAIMER_FILE)){
        gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="SAFETY NOTICE";m.title="Overclocking can cause crashes or data corruption";m.body={"This Wizard changes Horizon OC clocks, voltages and timings.","RAM instability can corrupt SD/NAND data. Keep backups and a no-OC recovery boot.","Use entirely at your own risk."};m.primaryAction="A  I understand / continue";m.secondaryAction="B  Exit";m.tone=gui::ModalTone::Red;gui::presentModal(m);
        bool accepted=false;while(appletMainLoop()){padUpdate(&pad);u64 k=padGetButtonsDown(&pad);if(k&HidNpadButton_A){std::ofstream(DISCLAIMER_FILE)<<"accepted\n";fsdevCommitDevice("sdmc");accepted=true;break;}if(k&HidNpadButton_B)break;svcSleepThread(20'000'000);}if(!accepted){gui::shutdown();socketExit();return 0;}
    }

    if(g.rebootPending){g.rebootPending=0;saveState();}
    if(g.testRunning)g_recoveryModal=true;
    if(g.dramId<0)detectHardware();

    bool redraw=true;
    while(appletMainLoop()){
        if(redraw){render();redraw=false;}
        padUpdate(&pad);u64 k=padGetButtonsDown(&pad);if(!k){svcSleepThread(20'000'000);continue;}
        if(g_errorModal){if(k&HidNpadButton_A||k&HidNpadButton_B){g_errorModal=false;redraw=true;}continue;}
        if(g_recoveryModal){if(k&HidNpadButton_A){g_recoveryModal=false;recoverInterrupted();redraw=true;}else if(k&HidNpadButton_B)break;continue;}
        if(k&HidNpadButton_Minus){resetAll();redraw=true;continue;}
        if(k&HidNpadButton_B){saveState();break;}

        if(g.stage==Stage::Hardware&&(k&HidNpadButton_A)){if(g.dramId<0){detectHardware();if(!g_errorModal&&!profile())modalError("This DRAM ID has no safe automatic timing profile. Automatic RAM preparation is unavailable.");}else if(profile()){g.stage=Stage::BenchmarkPrep;saveState();}else modalError("Automatic RAM preparation is unavailable for this DRAM ID.");redraw=true;continue;}
        if(g.stage==Stage::BenchmarkPrep&&(k&HidNpadButton_A)){u32 pct=0;PsmChargerType ch=PsmChargerType_Unconnected;batteryReady(pct,ch);if(ch==PsmChargerType_Unconnected)modalError("Connect the charger before starting the benchmark series.");else if(pct<100)modalError("Charge the console to 100% before starting the benchmark series.");else if(!backupOriginal()){}else{g.benchmarkReady=1;g.stage=Stage::RamPreparation;saveState();}redraw=true;continue;}
        if(g.stage==Stage::RamPreparation){if(k&HidNpadButton_Y){prepareRamAuto();redraw=true;continue;}if(k&HidNpadButton_A){const auto*p=profile();HocMonOcPreparation d{};d.uncappedClocks=true;d.hpMode=false;d.ramMaxKHz=3400000U;d.vdd2Uv=p->vdd2Mv*1000U;d.vddqUv=p->vddqMv*1000U;d.dvbShift=5;d.socVmaxUv=1200;for(int i=0;i<8;++i)d.timings[i]=p->common.t[i];u32 mm=0;Result rc=hocmonVerifyOcPreparation(&d,&mm);if(R_SUCCEEDED(rc)&&mm==0){g.ramHpMode=0;g.ramTimingMode=0;g.dvbGood=5;g.dvbCandidate=4;g.vdd2GoodUv=int(d.vdd2Uv);g.vdd2CandidateUv=g.vdd2GoodUv-12500;g.vddqGoodMv=int(p->vddqMv);g.vddqCandidateMv=g.vddqGoodMv-10;g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex();requestReboot(Stage::RamSweep);}else modalError("Preparation values do not match. Set the shown Common/HP/DVB/rail values or use automatic setup.");redraw=true;continue;}}
        if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamCandidate();redraw=true;continue;}if(k&HidNpadButton_X){finishRamSweep();redraw=true;continue;}}
        if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A)){g.stage=Stage::RamHpSet;saveState();redraw=true;continue;}
        if(g.stage==Stage::RamHpSet){if(k&HidNpadButton_Y){g.ramHpMode=0;g.stage=Stage::RamStSet;saveState();redraw=true;continue;}if(k&HidNpadButton_A){std::string e;if(!occonfig::setHpMode(true,e))modalError(e);else{g.ramHpMode=1;requestReboot(Stage::RamHpTest);}redraw=true;continue;}}
        if(g.stage==Stage::RamHpTest&&(k&HidNpadButton_A)){validateHp();redraw=true;continue;}
        if(g.stage==Stage::RamStSet){if(k&HidNpadButton_Y){g.ramTimingMode=0;g.dvbGood=5;g.dvbCandidate=4;g.stage=Stage::RamDvb;saveState();redraw=true;continue;}if(k&HidNpadButton_A){const auto*p=profile();std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=p->st.t[i];std::string e;if(!occonfig::setRamTimings(t,e)||!occonfig::setDvbShift(6,e))modalError(e);else{g.ramTimingMode=1;g.dvbGood=6;g.dvbCandidate=5;requestReboot(Stage::RamStTest);}redraw=true;continue;}}
        if(g.stage==Stage::RamStTest&&(k&HidNpadButton_A)){validateSt();redraw=true;continue;}
        if(g.stage==Stage::RamDvb){if(k&HidNpadButton_X){g.stage=Stage::RamVdd2;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runDvb();redraw=true;continue;}}
        if(g.stage==Stage::RamVdd2){if(k&HidNpadButton_X){g.stage=Stage::RamVddq;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runVdd2();redraw=true;continue;}}
        if(g.stage==Stage::RamVddq){if(k&HidNpadButton_X){g.stage=Stage::RamSoc;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runVddq();redraw=true;continue;}}
        if(g.stage==Stage::RamSoc){if(k&HidNpadButton_X){g.stage=Stage::RamFinalGraph;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runSoc();redraw=true;continue;}}
        if(g.stage==Stage::RamFinalGraph&&(k&HidNpadButton_A)){g.stage=Stage::GpuPreparation;saveState();redraw=true;continue;}
        if(g.stage==Stage::GpuPreparation&&(k&HidNpadButton_A)){prepareGpu();redraw=true;continue;}
        if(g.stage==Stage::GpuTune){if(k&HidNpadButton_A){runGpuTune();redraw=true;continue;}if((k&HidNpadButton_X)&&g.gpuApplied!=2){std::string e;int f=GPU_FREQS[g.gpuIndex];if(!occonfig::setGpuPoint(f,g.gpuGoodMv,e))modalError(e);else{g.gpuApplied=2;saveState();requestReboot(Stage::GpuTune);}redraw=true;continue;}}
        if(g.stage==Stage::GpuGraph&&(k&HidNpadButton_A)){g.stage=Stage::GpuRamCombined;saveState();redraw=true;continue;}
        if(g.stage==Stage::GpuRamCombined&&(k&HidNpadButton_A)){runGpuRam();redraw=true;continue;}
        if(g.stage==Stage::CpuPreparation&&(k&HidNpadButton_A)){prepareCpu();redraw=true;continue;}
        if(g.stage==Stage::CpuSweep){if(k&HidNpadButton_X){finishCpuCapability();redraw=true;continue;}if(k&HidNpadButton_A){runCpuCapability();redraw=true;continue;}}
        if(g.stage==Stage::CpuHighUv){if(k&HidNpadButton_X){std::string e;occonfig::setCpuTuning(0,g.highUvGood,3,620,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e);g.highUvApplied=0;g.stage=Stage::CpuLowUv;saveState();requestReboot(Stage::CpuLowUv);redraw=true;continue;}if(k&HidNpadButton_A){runHighUv();redraw=true;continue;}}
        if(g.stage==Stage::CpuLowUv){if(k&HidNpadButton_X){beginLowVmin();redraw=true;continue;}if(k&HidNpadButton_A){runLowUv();redraw=true;continue;}}
        if(g.stage==Stage::CpuLowVmin){if(k&HidNpadButton_X){applyBestLowAndContinue();redraw=true;continue;}if(k&HidNpadButton_A){runLowVmin();redraw=true;continue;}}
        if(g.stage==Stage::CpuTbreak2Set&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,2,g.lowBestVmin,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e))modalError(e);else requestReboot(Stage::CpuTbreak2Test);redraw=true;continue;}
        if(g.stage==Stage::CpuTbreak2Test&&(k&HidNpadButton_A)){if(!tbreakBoundaryCost(g.tbreak2CostMv))modalError("1581 MHz TBreak boundary test failed.");else{g.stage=Stage::CpuTbreak3Set;saveState();}redraw=true;continue;}
        if(g.stage==Stage::CpuTbreak3Set&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,3,g.lowBestVmin,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e))modalError(e);else requestReboot(Stage::CpuTbreak3Test);redraw=true;continue;}
        if(g.stage==Stage::CpuTbreak3Test&&(k&HidNpadButton_A)){if(!tbreakBoundaryCost(g.tbreak3CostMv))modalError("1683 MHz TBreak boundary test failed.");else{g.finalTbreak=(g.tbreak2CostMv>0&&g.tbreak2CostMv+5<g.tbreak3CostMv)?2:3;std::string e;if(!occonfig::setCpuTuning(g.lowBestUv,g.highUvGood,g.finalTbreak,g.lowBestVmin,870,CPU_VMAX_SAFE,g.cpuStableMaxMHz,e))modalError(e);else{beginHighVmin();requestReboot(Stage::CpuHighVmin);}}redraw=true;continue;}
        if(g.stage==Stage::CpuHighVmin){if(k&HidNpadButton_X){g.stage=Stage::CpuVmax;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runHighVmin();redraw=true;continue;}}
        if(g.stage==Stage::CpuVmax){if(k&HidNpadButton_X){finishVmax();redraw=true;continue;}if(k&HidNpadButton_A){runVmax();redraw=true;continue;}}
        if(g.stage==Stage::CpuFinalSweep&&(k&HidNpadButton_A)){runCpuFinal();redraw=true;continue;}
        if(g.stage==Stage::CpuGraph&&(k&HidNpadButton_A)){g.stage=Stage::CpuRamCombined;saveState();redraw=true;continue;}
        if(g.stage==Stage::CpuRamCombined&&(k&HidNpadButton_A)){runCpuRam();redraw=true;continue;}
        if(g.stage==Stage::Finalize&&(k&HidNpadButton_A)){saveFinal();redraw=true;continue;}
        if(g.stage==Stage::Complete&&(k&HidNpadButton_B))break;
        svcSleepThread(20'000'000);
    }

    clearOverrides(); appletSetAutoSleepDisabled(false); gui::shutdown(); socketExit(); return 0;
}
