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
constexpr int VDDQ_MIN_MV = 400;
constexpr int VDD2_MIN_UV = 912500;
constexpr int GPU_MIN_MV = 480;

const int GPU_FREQS[] = {768,844,921,998,1075,1152,1228,1267,1305};
const int CPU_FREQS[] = {1683,1785,1887,1963,2091,2193,2295,2397};
const int SOC_FREQS[] = {1866,2000,2133,2200,2266,2333,2400,2433,2466,2533,2566,2600,2666,2700,2733,2766,2800,2833,2900,2933,3000,3033,3100,3133,3166,3200,3266,3333};
const int SOC_MV[] = {637,650,662,675,687,700,712,725,737,750,762,775,787,800,812,825,837,850,862,875,887,900,912,925,937,950,962,975,987,1000,1012,1025,1037,1050,1062,1075,1087,1100,1112,1125,1137,1150,1162,1175,1187,1200};

enum class Stage : int {
    Hardware = 0,
    BenchmarkPrep,
    RamPreparation,
    RamSweep,
    RamGraph,
    RamStSet,
    RamStTest,
    RamVdd2,
    RamVddq,
    RamSoc,
    RamFinalGraph,
    GpuTune,
    GpuGraph,
    GpuRamCombined,
    CpuHighUv,
    CpuSweep,
    CpuTbreak2Set,
    CpuTbreak2Test,
    CpuTbreak3Set,
    CpuTbreak3Test,
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

    int ramSearchIndex = -1;
    int ramSearchEndIndex = -1;
    int ramRecommendedMHz = 0;
    int ramStableMaxMHz = 0;
    int ramTimingMode = 0; // 0 common, 1 ST
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

    int gpuIndex = 0;
    int gpuHaveBaseline = 0;
    int gpuGoodMv = 0;
    int gpuCandidateMv = 0;
    int gpuApplied = 0;
    int gpuRecommendedMHz = 0;
    int gpuStableMaxMHz = 0;
    int gpuLastPerfMilli = 0;
    int gpuLastPowerMilli = 0;

    int highUvGood = 0;
    int highUvCandidate = 1;
    int highUvApplied = 0;
    int cpuIndex = 0;
    int cpuRecommendedMHz = 0;
    int cpuStableMaxMHz = 0;
    int finalTbreak = 3;
    int tbreak2CostMv = 0;
    int tbreak3CostMv = 0;

    int gpuRamTrial = 0;
    int gpuRamOriginalRam = 0;
    int gpuRamOriginalGpu = 0;
    int cpuRamTrial = 0;
    int cpuRamOriginalRam = 0;
    int cpuRamOriginalCpu = 0;

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
    W(dramId); W(is8GB); W(consoleType); W(profileIndex); W(benchmarkReady);
    W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramTimingMode);
    W(vdd2GoodUv); W(vdd2CandidateUv); W(vdd2Applied); W(vddqGoodMv); W(vddqCandidateMv); W(vddqApplied);
    W(socTableMHz); W(socGoodMv); W(socCandidateMv); W(socApplied);
    W(gpuIndex); W(gpuHaveBaseline); W(gpuGoodMv); W(gpuCandidateMv); W(gpuApplied); W(gpuRecommendedMHz); W(gpuStableMaxMHz); W(gpuLastPerfMilli); W(gpuLastPowerMilli);
    W(highUvGood); W(highUvCandidate); W(highUvApplied); W(cpuIndex); W(cpuRecommendedMHz); W(cpuStableMaxMHz); W(finalTbreak); W(tbreak2CostMv); W(tbreak3CostMv);
    W(gpuRamTrial); W(gpuRamOriginalRam); W(gpuRamOriginalGpu); W(cpuRamTrial); W(cpuRamOriginalRam); W(cpuRamOriginalCpu);
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
#define R(name) if(k==#name){g.name=decltype(g.name)(n);continue;}
        R(stage) R(dramId) R(is8GB) R(consoleType) R(profileIndex) R(benchmarkReady)
        R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramTimingMode)
        R(vdd2GoodUv) R(vdd2CandidateUv) R(vdd2Applied) R(vddqGoodMv) R(vddqCandidateMv) R(vddqApplied)
        R(socTableMHz) R(socGoodMv) R(socCandidateMv) R(socApplied)
        R(gpuIndex) R(gpuHaveBaseline) R(gpuGoodMv) R(gpuCandidateMv) R(gpuApplied) R(gpuRecommendedMHz) R(gpuStableMaxMHz) R(gpuLastPerfMilli) R(gpuLastPowerMilli)
        R(highUvGood) R(highUvCandidate) R(highUvApplied) R(cpuIndex) R(cpuRecommendedMHz) R(cpuStableMaxMHz) R(finalTbreak) R(tbreak2CostMv) R(tbreak3CostMv)
        R(gpuRamTrial) R(gpuRamOriginalRam) R(gpuRamOriginalGpu) R(cpuRamTrial) R(cpuRamOriginalRam) R(cpuRamOriginalCpu)
        R(rebootPending) R(testRunning) R(testStage)
#undef R
    }
}

void savePoints() {
    ensureDir(APP_DIR);
    std::ofstream f(POINTS_FILE,std::ios::trunc); if(!f) return;
    auto wr=[&](const std::vector<oc::SweepPoint>& v){for(auto&p:v)f<<int(p.domain)<<','<<p.requestedMHz<<','<<p.realMHz<<','<<p.railMv<<','<<p.auxMv<<','<<p.performance<<','<<p.latencyNs<<','<<p.bandwidthMBs<<','<<p.batteryPowerW<<','<<p.stable<<','<<p.combinedStable<<'\n';};
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
    v.push_back(p); std::sort(v.begin(),v.end(),[](auto&a,auto&b){return a.requestedMHz<b.requestedMHz;}); savePoints();
}

int progressStep(Stage s) {
    if(s<=Stage::RamPreparation) return 1;
    if(s<=Stage::RamGraph) return 2;
    if(s<=Stage::RamFinalGraph) return 3;
    if(s<=Stage::GpuRamCombined) return 4;
    if(s<=Stage::CpuGraph) return 5;
    if(s<=Stage::CpuRamCombined) return 6;
    return 7;
}

bool clockMatch(u32 actual,u32 expected) { return expected==0 || (actual>expected?actual-expected:expected-actual)<=5000000U; }

bool setOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err) {
    Result rc=hocmonSetOverride(HocMonModule_CPU,cpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_GPU,gpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_MEM,ram);
    if(R_FAILED(rc)){char b[64];std::snprintf(b,sizeof(b),"Temporary Override failed: 0x%08X",rc);err=b;return false;}
    svcSleepThread(500'000'000);
    HocMonClocks c{}; rc=hocmonGetTelemetry(&c); if(R_FAILED(rc)){err="Could not verify HOC active values.";return false;}
    if(!clockMatch(c.overrideHz[0],cpu)||!clockMatch(c.overrideHz[1],gpu)||!clockMatch(c.overrideHz[2],ram)||!clockMatch(c.realHz[0],cpu)||!clockMatch(c.realHz[1],gpu)||!clockMatch(c.realHz[2],ram)){err="Active clocks do not match the Wizard request. Correct the red values before testing.";return false;}
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

int ramEndIndex(const oc::RamProfile* p){
    int best=oc::maxRamSearchIndex(p); int n=int(sizeof(oc::RAM_STEPS_MHZ)/sizeof(oc::RAM_STEPS_MHZ[0]));
    for(int i=best;i<n;++i){if(oc::RAM_STEPS_MHZ[i]<=std::min<std::uint32_t>(3400,p?p->maxMHz+100:3000))best=i;else break;}return best;
}

int nearestSocFreq(int mhz){int best=SOC_FREQS[0],d=99999;for(int f:SOC_FREQS){int x=std::abs(f-mhz);if(x<d){d=x;best=f;}}return best;}
int nextLowerSocMv(int mv){int best=0;for(int v:SOC_MV){if(v<mv)best=v;else break;}return best;}

void analyzeRam(){auto a=oc::analyzeSweep(ramPoints);if(a.recommended>=0){g.ramRecommendedMHz=int(ramPoints[a.recommended].requestedMHz);g.ramStableMaxMHz=int(ramPoints[a.stableMax].requestedMHz);}saveState();}
void analyzeGpu(){auto a=oc::analyzeSweep(gpuPoints);if(a.recommended>=0){g.gpuRecommendedMHz=int(gpuPoints[a.recommended].requestedMHz);g.gpuStableMaxMHz=int(gpuPoints[a.stableMax].requestedMHz);}saveState();}
void analyzeCpu(){auto a=oc::analyzeSweep(cpuPoints);if(a.recommended>=0){g.cpuRecommendedMHz=int(cpuPoints[a.recommended].requestedMHz);g.cpuStableMaxMHz=int(cpuPoints[a.stableMax].requestedMHz);}saveState();}

std::vector<gui::ChartPoint> chart(const std::vector<oc::SweepPoint>& pts){
    auto a=oc::analyzeSweep(pts);std::vector<gui::ChartPoint> out;for(int i=0;i<int(pts.size());++i){gui::ChartPoint q;q.x=pts[i].requestedMHz;q.performance=pts[i].performance;q.voltage=pts[i].railMv;q.power=pts[i].powerReliable?pts[i].batteryPowerW:0;q.stable=pts[i].stable&&pts[i].combinedStable;q.sweetSpot=i==a.sweetSpot;q.stableMax=i==a.stableMax;q.recommended=i==a.recommended;out.push_back(q);}return out;
}

void detectHardware(){HocMonHardware h{};Result rc=hocmonGetHardware(&h);if(R_FAILED(rc)){g_message="Horizon OC hardware detection failed.";g_errorModal=true;return;}g.dramId=h.dramId;g.is8GB=h.isDram8GB?1:0;g.consoleType=int(h.consoleType);const auto*p=oc::findRamProfile(h.dramId,h.isDram8GB);g.profileIndex=profileIndex(p);saveState();}

bool batteryReady(u32& pct,PsmChargerType& charger){pct=0;charger=PsmChargerType_Unconnected;if(R_FAILED(psmInitialize()))return false;Result a=psmGetBatteryChargePercentage(&pct);Result b=psmGetChargerType(&charger);psmExit();return R_SUCCEEDED(a)&&R_SUCCEEDED(b);}

void modalError(const std::string&s){g_message=s;g_errorModal=true;}

void render() {
    hocmonGetTelemetry(&g_active);
    if(g_errorModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="WIZARD NOTICE";m.title="Action required";m.body={g_message};m.primaryAction="A  OK";m.tone=gui::ModalTone::Red;gui::presentModal(m);return;}
    if(g_recoveryModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED TEST";m.title="Previous candidate did not finish";m.body={"A crash, freeze or reboot occurred while a candidate was being tested.","The Wizard will treat that candidate as unstable and return to the last known good value."};m.primaryAction="A  Recover last good value";m.secondaryAction="B  Exit";m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;}

    gui::View v;v.version=HOC_WIZARD_VERSION;v.activeStep=progressStep(g.stage);v.pulse=true;v.haveActiveValues=true;
    v.values[0]={"CPU",fmt1(g_active.realHz[0]/1e6)+" MHz",false};v.values[1]={"GPU",fmt1(g_active.realHz[1]/1e6)+" MHz",false};v.values[2]={"RAM",fmt1(g_active.realHz[2]/1e6)+" MHz",false};v.values[3]={"VDD2",fmt1(g_active.vdd2VoltageUv/1000.0)+" mV",false};v.values[4]={"VDDQ",fmt1(g_active.vddqVoltageUv/1000.0)+" mV",false};

    auto print=[&](int row,const std::string&s){gui::printLeft(row,s.c_str());};

    switch(g.stage){
        case Stage::Hardware:{v.stageTitle="Hardware Detection";v.instructionTitle="Detect this console";v.instructionLine1="RAM type determines the safe search range.";v.instructionLine2="A  Detect hardware";gui::begin(v);print(1,"The OC Wizard uses your console's own measurements, not fixed end values.");if(g.dramId>=0){print(3,"DRAM ID: "+std::to_string(g.dramId));if(profile())print(4,std::string("Detected RAM: ")+profile()->name+"  |  Tier "+profile()->tier);else print(4,"RAM preset: manual only / unsupported ID");}print(8,"A : Detect / continue");print(9,"B : Exit");gui::present();break;}
        case Stage::BenchmarkPrep:{u32 pct=0;PsmChargerType ch=PsmChargerType_Unconnected;bool ok=batteryReady(pct,ch);v.stageTitle="Benchmark Preparation";v.fullWidthLayout=true;gui::begin(v);print(1,"For comparable performance and power data, keep the test conditions fixed for the whole Wizard.");print(3,"Battery: "+(ok?std::to_string(pct)+" %":"unavailable"));print(4,std::string("Charger: ")+(ok&&ch!=PsmChargerType_Unconnected?"connected":"NOT detected"));print(6,"Required: fully charged console, charger connected, brightness 100%.");print(7,"Disable screen dimming / sleep in System Settings while tuning.");print(8,"Do not change dock/handheld state during one measurement series.");print(11,"A : Conditions are set / continue");print(12,"B : Exit");gui::present();break;}
        case Stage::RamPreparation:{v.stageTitle="RAM Preparation";v.preparationLayout=true;v.hideValuesCard=true;v.instructionTitle="Set the RAM baseline";v.instructionLine1="Common timings are used first; ST is tested later.";v.instructionLine2="Y  Apply automatically";const auto*p=profile();gui::begin(v);if(!p){print(1,"No safe automatic timing profile is available for this DRAM ID.");print(3,"Automatic timing changes are disabled for unknown / 8 GB memory.");print(8,"B : Exit");}else{print(1,"The Wizard starts conservatively, finds the clock limit, then optimizes timings and rails.");print(3,std::string("RAM profile: ")+p->name+"  |  Tier "+p->tier);print(4,"Search range: "+std::to_string(p->minMHz)+" - "+std::to_string(std::min<std::uint32_t>(3400,p->maxMHz+100))+" MHz");print(6,"HP Mode: ON   |   DVB Shift: 2   |   SoC VMAX: 1200 mV");print(7,"VDD2: "+std::to_string(p->vdd2Mv)+" mV   |   VDDQ: "+std::to_string(p->vddqMv)+" mV");std::ostringstream t;t<<"Common timings: ";for(int i=0;i<8;++i){if(i)t<<'-';t<<p->common.t[i];}print(8,t.str());print(11,"A : Check manually set values");print(12,"Y : Apply recommended baseline automatically");print(13,"B : Exit");}gui::present();break;}
        case Stage::RamSweep:{const auto*p=profile();int freq=(g.ramSearchIndex>=0)?int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]):0;v.stageTitle="RAM Clock Search";v.instructionTitle="Test the next RAM clock";v.instructionLine1="1 min stability + Memory Benchmark.";v.instructionLine2="A  Start test";gui::begin(v);print(1,"The Wizard searches this console's real RAM limit with safe baseline voltages.");print(3,"Candidate: "+std::to_string(freq)+" MHz");print(4,"Last stable: "+std::to_string(g.ramStableMaxMHz)+" MHz");if(p)print(5,std::string("Detected class: ")+p->name);print(8,"A : Run candidate test");print(9,"X : Known unstable / stop search here");print(10,"B : Exit");gui::present();break;}
        case Stage::RamGraph:case Stage::RamFinalGraph:{v.stageTitle=g.stage==Stage::RamGraph?"RAM Sweep Result":"RAM Final Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="RAM performance / electrical cost";v.chartXLabel="RAM MHz";v.chartCostLabel="VDD2 / battery power";v.chartPoints=chart(ramPoints);v.chartSummary="Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz   |   Recommended: "+std::to_string(g.ramRecommendedMHz)+" MHz";gui::begin(v);print(12,"A : Continue");print(13,"B : Exit");gui::present();break;}
        case Stage::RamStSet:{const auto*p=profile();v.stageTitle="RAM Timing Validation";v.instructionTitle="Try Super Tight timings";v.instructionLine1="The clock is already known stable.";v.instructionLine2="A  Apply ST + reboot";gui::begin(v);print(1,"Super Tight is tested only after the RAM clock search.");if(p){std::ostringstream t;t<<"ST timings: ";for(int i=0;i<8;++i){if(i)t<<'-';t<<p->st.t[i];}print(3,t.str());}print(5,"If ST fails, Common timings are restored automatically.");print(8,"A : Apply ST and reboot");print(9,"Y : Keep Common timings / skip ST");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStTest:{v.stageTitle="RAM Timing Validation";v.instructionTitle="Validate ST timings";v.instructionLine1="1 min RAM test + Memory Benchmark.";v.instructionLine2="A  Start validation";gui::begin(v);print(1,"Testing Super Tight at the recommended RAM clock.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Start validation");print(9,"B : Exit");gui::present();break;}
        case Stage::RamVdd2:{v.stageTitle="RAM VDD2 Optimization";v.instructionTitle=g.vdd2Applied?"Test the applied VDD2":"Apply the next VDD2 candidate";v.instructionLine1=g.vdd2Applied?"1 min RAM stability test.":"One 12.5 mV step at a time.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"Only VDD2 changes in this step. If it fails, the last good value is restored.");print(3,"Last good: "+fmtMvUv(g.vdd2GoodUv));print(4,"Candidate: "+fmtMvUv(g.vdd2CandidateUv));print(8,"A : "+std::string(g.vdd2Applied?"Run candidate test":"Apply candidate and reboot"));print(9,"X : Stop here / keep last good VDD2");print(10,"B : Exit");gui::present();break;}
        case Stage::RamVddq:{v.stageTitle="RAM VDDQ Optimization";v.instructionTitle=g.vddqApplied?"Test the applied VDDQ":"Apply the next VDDQ candidate";v.instructionLine1=g.vddqApplied?"1 min RAM stability test.":"One 10 mV step at a time.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"Only VDDQ changes in this step. If it fails, the last good value is restored.");print(3,"Last good: "+std::to_string(g.vddqGoodMv)+" mV");print(4,"Candidate: "+std::to_string(g.vddqCandidateMv)+" mV");print(8,"A : "+std::string(g.vddqApplied?"Run candidate test":"Apply candidate and reboot"));print(9,"X : Stop here / keep last good VDDQ");print(10,"B : Exit");gui::present();break;}
        case Stage::RamSoc:{v.stageTitle="RAM SoC Voltage Optimization";v.instructionTitle=g.socApplied?"Test the applied SoC voltage":"Apply the next SoC candidate";v.instructionLine1="Only the nearest SoC table point changes.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"The Wizard lowers the SoC table point used by the final RAM clock.");print(3,"Table point: "+std::to_string(g.socTableMHz)+" MHz");print(4,"Last good: "+std::to_string(g.socGoodMv)+" mV");print(5,"Candidate: "+std::to_string(g.socCandidateMv)+" mV");print(8,"A : "+std::string(g.socApplied?"Run candidate test":"Apply candidate and reboot"));print(9,"X : Stop here / keep last good SoC voltage");print(10,"B : Exit");gui::present();break;}
        case Stage::GpuTune:{int f=GPU_FREQS[std::clamp(g.gpuIndex,0,int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0]))-1)];v.stageTitle="GPU Voltage Curve";v.instructionTitle=!g.gpuHaveBaseline?"Measure the safe starting voltage":(g.gpuApplied?"Test the voltage candidate":"Apply the next voltage candidate");v.instructionLine1="GPU is measured with base RAM first.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"Each GPU clock gets its own measured minimum stable voltage.");print(3,"GPU clock: "+std::to_string(f)+" MHz");if(g.gpuHaveBaseline){print(4,"Last good: "+std::to_string(g.gpuGoodMv)+" mV");print(5,"Candidate: "+std::to_string(g.gpuCandidateMv)+" mV");}print(8,"A : Continue");if(g.gpuHaveBaseline)print(9,"X : Known unstable / keep last good voltage");print(10,"B : Exit");gui::present();break;}
        case Stage::GpuGraph:{v.stageTitle="GPU Sweep Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="GPU performance / voltage curve";v.chartXLabel="GPU MHz";v.chartCostLabel="GPU mV / battery power";v.chartPoints=chart(gpuPoints);v.chartSummary="Stable Max: "+std::to_string(g.gpuStableMaxMHz)+" MHz   |   Recommended: "+std::to_string(g.gpuRecommendedMHz)+" MHz";gui::begin(v);print(12,"A : Continue to GPU + RAM validation");print(13,"B : Exit");gui::present();break;}
        case Stage::GpuRamCombined:{v.stageTitle="GPU + RAM Integration";v.instructionTitle="Validate the combined recommendation";v.instructionLine1="Only one domain is changed after a failure.";v.instructionLine2="A  Start combined validation";gui::begin(v);print(1,"A point can be stable alone and still fail when GPU and RAM are both high.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"GPU: "+std::to_string(g.gpuRecommendedMHz)+" MHz");if(g.gpuRamTrial==1)print(6,"Trial: RAM lowered one step; GPU unchanged.");if(g.gpuRamTrial==2)print(6,"Trial: GPU lowered one step; RAM restored.");print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuHighUv:{v.stageTitle="CPU High UV Search";v.instructionTitle=g.highUvApplied?"Test the applied High UV":"Apply the next High UV level";v.instructionLine1="Final RAM stays active during the search.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"The Wizard finds the most aggressive common High-UV curve that remains stable with final RAM.");print(3,"Last good High UV: "+std::to_string(g.highUvGood));print(4,"Candidate High UV: "+std::to_string(g.highUvCandidate));print(5,"Test clock: 2397 MHz");print(8,"A : "+std::string(g.highUvApplied?"Run 2397 MHz validation":"Apply candidate and reboot"));print(9,"X : Known unstable / keep last good High UV");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuSweep:{int f=CPU_FREQS[std::clamp(g.cpuIndex,0,int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0]))-1)];v.stageTitle="CPU Performance Sweep";v.instructionTitle="Measure CPU performance";v.instructionLine1="CPU Ray Trace FPS + combined stability.";v.instructionLine2="A  Start measurement";gui::begin(v);print(1,"The final RAM clock remains active so the CPU curve reflects the real OC profile.");print(3,"CPU candidate: "+std::to_string(f)+" MHz");print(4,"High UV: "+std::to_string(g.highUvGood));print(8,"A : Run measurement");print(9,"X : Known unstable / stop CPU sweep");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuTbreak2Set:case Stage::CpuTbreak3Set:{int tb=g.stage==Stage::CpuTbreak2Set?1581:1683;v.stageTitle="CPU TBreak Selection";v.instructionTitle="Apply "+std::to_string(tb)+" MHz TBreak";v.instructionLine1="Both table choices are measured on this CPU.";v.instructionLine2="A  Apply and reboot";gui::begin(v);print(1,"TBreak is chosen from measured Low-vs-High table efficiency, not a fixed default.");print(3,"Candidate TBreak: "+std::to_string(tb)+" MHz");print(8,"A : Apply candidate and reboot");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuTbreak2Test:case Stage::CpuTbreak3Test:{int tb=g.stage==Stage::CpuTbreak2Test?1581:1683;v.stageTitle="CPU TBreak Selection";v.instructionTitle="Measure this TBreak";v.instructionLine1="1581 and 1683 MHz are compared.";v.instructionLine2="A  Run comparison";gui::begin(v);print(1,"The Wizard compares actual CPU voltage and stability around the table boundary.");print(3,"Active TBreak: "+std::to_string(tb)+" MHz");print(8,"A : Run boundary comparison");print(10,"B : Exit");gui::present();break;}
        case Stage::CpuGraph:{v.stageTitle="CPU Sweep Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="CPU Ray Trace FPS / voltage curve";v.chartXLabel="CPU MHz";v.chartCostLabel="CPU mV / battery power";v.chartPoints=chart(cpuPoints);v.chartSummary="Stable Max: "+std::to_string(g.cpuStableMaxMHz)+" MHz   |   Recommended: "+std::to_string(g.cpuRecommendedMHz)+" MHz   |   TBreak: "+std::to_string(g.finalTbreak==2?1581:1683)+" MHz";gui::begin(v);print(12,"A : Continue to CPU + RAM validation");print(13,"B : Exit");gui::present();break;}
        case Stage::CpuRamCombined:{v.stageTitle="CPU + RAM Integration";v.instructionTitle="Validate final CPU + RAM";v.instructionLine1="A failed combination can revise an earlier recommendation.";v.instructionLine2="A  Start validation";gui::begin(v);print(1,"Only one domain is backed off at a time so the limiting setting can be identified.");print(3,"CPU: "+std::to_string(g.cpuRecommendedMHz)+" MHz");print(4,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");if(g.cpuRamTrial==1)print(6,"Trial: RAM lowered one step; CPU unchanged.");if(g.cpuRamTrial==2)print(6,"Trial: CPU lowered one step; RAM restored.");print(8,"A : Start 5 minute combined validation");print(10,"B : Exit");gui::present();break;}
        case Stage::Finalize:{v.stageTitle="Final Profile";v.fullWidthLayout=true;gui::begin(v);print(1,"The adaptive sweeps and combined validations are complete.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz   |   "+(g.ramTimingMode?"Super Tight":"Common"));print(4,"VDD2: "+fmtMvUv(g.vdd2GoodUv)+"   |   VDDQ: "+std::to_string(g.vddqGoodMv)+" mV   |   SoC: "+std::to_string(g.socGoodMv)+" mV");print(5,"GPU: "+std::to_string(g.gpuRecommendedMHz)+" MHz");print(6,"CPU: "+std::to_string(g.cpuRecommendedMHz)+" MHz   |   High UV "+std::to_string(g.highUvGood)+"   |   TBreak "+std::to_string(g.finalTbreak==2?1581:1683)+" MHz");print(8,"A : Save current HOC files to Performance Modes · OC Mode");print(10,"B : Exit");gui::present();break;}
        case Stage::Complete:{v.stageTitle="Complete";v.fullWidthLayout=true;gui::begin(v);print(1,"OVERCLOCKING COMPLETE");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"GPU: "+std::to_string(g.gpuRecommendedMHz)+" MHz");print(5,"CPU: "+std::to_string(g.cpuRecommendedMHz)+" MHz");print(6,"CPU High UV: "+std::to_string(g.highUvGood));print(7,"CPU TBreak: "+std::to_string(g.finalTbreak==2?1581:1683)+" MHz");print(9,"Saved to Performance Modes · OC Mode");print(12,"B : Exit");gui::present();break;}
    }
}

bool prepareRamAuto(){const auto*p=profile();if(!p){modalError("No automatic RAM profile is available for this memory.");return false;}std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=p->common.t[i];std::string e;auto max=std::min<std::uint32_t>(3400,p->maxMHz+100);if(!occonfig::setRamPreparation(true,max,p->vdd2Mv,p->vddqMv,2,1200,t,e)){modalError(e);return false;}g.vdd2GoodUv=int(p->vdd2Mv*1000);g.vdd2CandidateUv=g.vdd2GoodUv-12500;g.vddqGoodMv=int(p->vddqMv);g.vddqCandidateMv=g.vddqGoodMv-10;g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex(p);saveState();return requestReboot(Stage::RamSweep);}

void finishRamSweep(){analyzeRam();if(g.ramRecommendedMHz<=0){modalError("No stable RAM point was measured.");return;}g.stage=Stage::RamGraph;saveState();}

void runRamCandidate(){const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){modalError(e);return;}if(!runStress(stress::Kind::Ram,60,"RAM Clock Stability","RAM "+std::to_string(freq)+" MHz")){finishRamSweep();return;}auto b=ocbench::runRam();if(!b.ok){finishRamSweep();return;}oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.auxMv=std::uint32_t(std::round(b.telemetry.vddqMv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=b.telemetry.powerSamples>1;p.stable=true;recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}}

void validateSt(){std::string e;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}bool pass=runStress(stress::Kind::Ram,60,"RAM Super Tight Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz");auto b=pass?ocbench::runRam():ocbench::RamResult{};if(pass&&b.ok){g.ramTimingMode=1;oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=g.ramRecommendedMHz;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.auxMv=std::uint32_t(std::round(b.telemetry.vddqMv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=b.telemetry.powerSamples>1;p.stable=true;recordPoint(ramPoints,p);g.stage=Stage::RamVdd2;saveState();}else{const auto*pr=profile();if(!pr){modalError("Cannot restore Common timings.");return;}std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];if(!occonfig::setRamTimings(t,e)){modalError(e);return;}g.ramTimingMode=0;saveState();requestReboot(Stage::RamVdd2);}}

void runVdd2(){std::string e;if(!g.vdd2Applied){if(g.vdd2CandidateUv<VDD2_MIN_UV){g.stage=Stage::RamVddq;saveState();return;}if(!occonfig::setVdd2Uv(g.vdd2CandidateUv,e)){modalError(e);return;}g.vdd2Applied=1;saveState();requestReboot(Stage::RamVdd2);return;}if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(runStress(stress::Kind::Ram,60,"VDD2 Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.vdd2GoodUv=g.vdd2CandidateUv;g.vdd2CandidateUv-=12500;g.vdd2Applied=0;saveState();}else{if(!occonfig::setVdd2Uv(g.vdd2GoodUv,e)){modalError(e);return;}g.vdd2Applied=0;saveState();requestReboot(Stage::RamVddq);}}

void runVddq(){std::string e;if(!g.vddqApplied){if(g.vddqCandidateMv<VDDQ_MIN_MV){g.stage=Stage::RamSoc;saveState();return;}if(!occonfig::setVddq(g.vddqCandidateMv,e)){modalError(e);return;}g.vddqApplied=1;saveState();requestReboot(Stage::RamVddq);return;}if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(runStress(stress::Kind::Ram,60,"VDDQ Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.vddqGoodMv=g.vddqCandidateMv;g.vddqCandidateMv-=10;g.vddqApplied=0;saveState();}else{if(!occonfig::setVddq(g.vddqGoodMv,e)){modalError(e);return;}g.vddqApplied=0;saveState();requestReboot(Stage::RamSoc);}}

void initSoc(){if(g.socGoodMv>0)return;std::string e;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}HocMonClocks c{};hocmonGetTelemetry(&c);g.socTableMHz=nearestSocFreq(g.ramRecommendedMHz);g.socGoodMv=int(std::round(c.socVoltageUv/1000.0));if(g.socGoodMv<637)g.socGoodMv=875;g.socCandidateMv=nextLowerSocMv(g.socGoodMv);saveState();}
void runSoc(){initSoc();if(g_errorModal)return;std::string e;if(!g.socApplied){if(g.socCandidateMv<637||g.socCandidateMv<=0){g.stage=Stage::RamFinalGraph;saveState();return;}if(!occonfig::setSocPoint(g.socTableMHz,g.socCandidateMv,e)){modalError(e);return;}g.socApplied=1;saveState();requestReboot(Stage::RamSoc);return;}if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(runStress(stress::Kind::Ram,60,"SoC Voltage Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.socGoodMv=g.socCandidateMv;g.socCandidateMv=nextLowerSocMv(g.socGoodMv);g.socApplied=0;saveState();}else{if(!occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e)){modalError(e);return;}g.socApplied=0;saveState();requestReboot(Stage::RamFinalGraph);}}

void finishGpuPoint(){int f=GPU_FREQS[g.gpuIndex];oc::SweepPoint p;p.domain=oc::Domain::Gpu;p.requestedMHz=f;p.realMHz=f;p.railMv=g.gpuGoodMv;p.performance=g.gpuLastPerfMilli/1000.0;p.batteryPowerW=g.gpuLastPowerMilli/1000.0;p.powerReliable=g.gpuLastPowerMilli>0;p.stable=true;recordPoint(gpuPoints,p);++g.gpuIndex;g.gpuHaveBaseline=0;g.gpuApplied=0;g.gpuGoodMv=g.gpuCandidateMv=0;g.gpuLastPerfMilli=g.gpuLastPowerMilli=0;if(g.gpuIndex>=int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0]))){analyzeGpu();g.stage=Stage::GpuGraph;}saveState();}

void runGpuTune(){if(g.gpuIndex>=int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0]))){analyzeGpu();g.stage=Stage::GpuGraph;saveState();return;}int f=GPU_FREQS[g.gpuIndex];std::string e;if(!g.gpuHaveBaseline){if(!setOverrides(CPU_BASE_HZ,u32(f)*1000000U,RAM_BASE_HZ,e)){modalError(e);return;}auto b=ocbench::runGpu();if(!b.ok){modalError(b.error);return;}g.gpuGoodMv=int(std::round(b.telemetry.gpuMv/5.0)*5.0);if(g.gpuGoodMv<GPU_MIN_MV)g.gpuGoodMv=700;g.gpuCandidateMv=g.gpuGoodMv-10;g.gpuLastPerfMilli=int(std::round(b.gflops*1000.0));g.gpuLastPowerMilli=int(std::round(b.telemetry.batteryPowerW*1000.0));g.gpuHaveBaseline=1;saveState();return;}if(!g.gpuApplied){if(g.gpuCandidateMv<GPU_MIN_MV){finishGpuPoint();return;}if(!occonfig::setGpuPoint(f,g.gpuCandidateMv,e)){modalError(e);return;}g.gpuApplied=1;saveState();requestReboot(Stage::GpuTune);return;}if(!setOverrides(CPU_BASE_HZ,u32(f)*1000000U,RAM_BASE_HZ,e)){modalError(e);return;}bool pass=runStress(stress::Kind::Gpu,60,"GPU Voltage Stability","GPU "+std::to_string(f)+" MHz @ "+std::to_string(g.gpuCandidateMv)+" mV");auto b=pass?ocbench::runGpu():ocbench::GpuResult{};if(pass&&b.ok){g.gpuGoodMv=g.gpuCandidateMv;g.gpuCandidateMv-=5;g.gpuLastPerfMilli=int(std::round(b.gflops*1000.0));g.gpuLastPowerMilli=int(std::round(b.telemetry.batteryPowerW*1000.0));g.gpuApplied=0;saveState();}else{if(!occonfig::setGpuPoint(f,g.gpuGoodMv,e)){modalError(e);return;}g.gpuApplied=0;finishGpuPoint();requestReboot(g.stage);}}

int previousPointMHz(const std::vector<oc::SweepPoint>& pts,int current){int prev=0;for(auto&p:pts)if(int(p.requestedMHz)<current)prev=std::max(prev,int(p.requestedMHz));return prev;}

void runGpuRam(){std::string e;if(!setOverrides(CPU_BASE_HZ,u32(g.gpuRecommendedMHz)*1000000U,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}bool pass=runStress(stress::Kind::Ram,60,"GPU + RAM Integration","GPU "+std::to_string(g.gpuRecommendedMHz)+" | RAM "+std::to_string(g.ramRecommendedMHz));auto b=pass?ocbench::runGpu():ocbench::GpuResult{};pass=pass&&b.ok;if(pass){if(g.gpuRamTrial==1||g.gpuRamTrial==2){g.gpuRamTrial=0;}g.stage=Stage::CpuHighUv;saveState();return;}if(g.gpuRamTrial==0){g.gpuRamOriginalRam=g.ramRecommendedMHz;g.gpuRamOriginalGpu=g.gpuRecommendedMHz;int lower=previousPointMHz(ramPoints,g.ramRecommendedMHz);if(lower>0){g.ramRecommendedMHz=lower;g.gpuRamTrial=1;saveState();return;}}if(g.gpuRamTrial==1){g.ramRecommendedMHz=g.gpuRamOriginalRam;int lower=previousPointMHz(gpuPoints,g.gpuRecommendedMHz);if(lower>0){g.gpuRecommendedMHz=lower;g.gpuRamTrial=2;saveState();return;}}modalError("GPU + RAM remains unstable after single-domain backoff. Review the RAM/GPU curves before continuing.");}

void runHighUv(){std::string e;if(!g.highUvApplied){if(g.highUvCandidate>13){g.stage=Stage::CpuSweep;saveState();return;}if(!occonfig::setCpuTuning(0,g.highUvCandidate,3,620,750,1200,2397,e)){modalError(e);return;}g.highUvApplied=1;saveState();requestReboot(Stage::CpuHighUv);return;}if(!setOverrides(2397000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}bool pass=runStress(stress::Kind::Combined,60,"CPU High UV Stability","2397 MHz + final RAM");auto b=pass?ocbench::runCpu(6):ocbench::CpuResult{};if(pass&&b.ok){g.highUvGood=g.highUvCandidate;++g.highUvCandidate;g.highUvApplied=0;saveState();}else{if(!occonfig::setCpuTuning(0,g.highUvGood,3,620,750,1200,2397,e)){modalError(e);return;}g.highUvApplied=0;g.stage=Stage::CpuSweep;saveState();requestReboot(Stage::CpuSweep);}}

void finishCpuSweep(){analyzeCpu();if(g.cpuRecommendedMHz<=0){modalError("No stable CPU point was measured.");return;}g.stage=Stage::CpuTbreak2Set;saveState();}
void runCpuSweep(){int f=CPU_FREQS[g.cpuIndex];std::string e;if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}if(!runStress(stress::Kind::Combined,60,"CPU Sweep Stability","CPU "+std::to_string(f)+" MHz + RAM "+std::to_string(g.ramRecommendedMHz))){finishCpuSweep();return;}auto b=ocbench::runCpu(6);if(!b.ok){finishCpuSweep();return;}oc::SweepPoint p;p.domain=oc::Domain::Cpu;p.requestedMHz=f;p.realMHz=b.telemetry.realCpuMHz;p.railMv=std::uint32_t(std::round(b.telemetry.cpuMv));p.performance=b.fps;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=b.telemetry.powerSamples>1;p.stable=true;recordPoint(cpuPoints,p);g.cpuStableMaxMHz=f;if(++g.cpuIndex>=int(sizeof(CPU_FREQS)/sizeof(CPU_FREQS[0])))finishCpuSweep();else saveState();}

bool tbreakBoundaryCost(int&out){std::string e;double sum=0;for(int f:{1581,1683}){if(!setOverrides(u32(f)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return false;}if(!runStress(stress::Kind::Cpu,30,"CPU TBreak Boundary","CPU "+std::to_string(f)+" MHz"))return false;auto b=ocbench::runCpu(5);if(!b.ok)return false;sum+=b.telemetry.cpuMv;}out=int(std::round(sum/2.0));return true;}

void runCpuRam(){std::string e;if(!setOverrides(u32(g.cpuRecommendedMHz)*1000000U,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}bool pass=runStress(stress::Kind::Combined,300,"CPU + RAM Final Validation","CPU "+std::to_string(g.cpuRecommendedMHz)+" | RAM "+std::to_string(g.ramRecommendedMHz));if(pass){g.cpuRamTrial=0;g.stage=Stage::Finalize;saveState();return;}if(g.cpuRamTrial==0){g.cpuRamOriginalRam=g.ramRecommendedMHz;g.cpuRamOriginalCpu=g.cpuRecommendedMHz;int lower=previousPointMHz(ramPoints,g.ramRecommendedMHz);if(lower>0){g.ramRecommendedMHz=lower;g.cpuRamTrial=1;saveState();return;}}if(g.cpuRamTrial==1){g.ramRecommendedMHz=g.cpuRamOriginalRam;int lower=previousPointMHz(cpuPoints,g.cpuRecommendedMHz);if(lower>0){g.cpuRecommendedMHz=lower;g.cpuRamTrial=2;saveState();return;}}modalError("CPU + RAM remains unstable after single-domain backoff. Review the curves before continuing.");}

void saveFinal(){ensureDir(PERF_OC_DIR);bool a=copyFile(HOC_CONFIG,(std::string(PERF_OC_DIR)+"/config.ini").c_str());bool b=copyFile(HOC_KIP,(std::string(PERF_OC_DIR)+"/hoc.kip").c_str());std::ofstream f(RESULTS_FILE,std::ios::trunc);f<<"HOC Overclocking Wizard "<<HOC_WIZARD_VERSION<<"\n";f<<"RAM="<<g.ramRecommendedMHz<<" MHz\nGPU="<<g.gpuRecommendedMHz<<" MHz\nCPU="<<g.cpuRecommendedMHz<<" MHz\nHighUV="<<g.highUvGood<<"\nTBreak="<<(g.finalTbreak==2?1581:1683)<<" MHz\nVDD2="<<fmtMvUv(g.vdd2GoodUv)<<"\nVDDQ="<<g.vddqGoodMv<<" mV\nSoC="<<g.socGoodMv<<" mV\n";f.flush();fsdevCommitDevice("sdmc");if(!a||!b){modalError("Tuning finished, but Performance Modes OCMode files could not both be saved.");return;}g.stage=Stage::Complete;saveState();}

void resetAll(){clearOverrides();unlink(STATE_FILE);unlink(POINTS_FILE);unlink(RESULTS_FILE);unlink(DISCLAIMER_FILE);g=State{};ramPoints.clear();gpuPoints.clear();cpuPoints.clear();detectHardware();saveState();}

void recoverInterrupted(){g.testRunning=0;g.testStage=-1;std::string e;switch(g.stage){case Stage::RamVdd2:if(g.vdd2Applied){occonfig::setVdd2Uv(g.vdd2GoodUv,e);g.vdd2Applied=0;g.stage=Stage::RamVddq;requestReboot(g.stage);return;}break;case Stage::RamVddq:if(g.vddqApplied){occonfig::setVddq(g.vddqGoodMv,e);g.vddqApplied=0;g.stage=Stage::RamSoc;requestReboot(g.stage);return;}break;case Stage::RamSoc:if(g.socApplied){occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e);g.socApplied=0;g.stage=Stage::RamFinalGraph;requestReboot(g.stage);return;}break;case Stage::GpuTune:if(g.gpuApplied){int f=GPU_FREQS[g.gpuIndex];occonfig::setGpuPoint(f,g.gpuGoodMv,e);g.gpuApplied=0;finishGpuPoint();requestReboot(g.stage);return;}break;case Stage::CpuHighUv:if(g.highUvApplied){occonfig::setCpuTuning(0,g.highUvGood,3,620,750,1200,2397,e);g.highUvApplied=0;g.stage=Stage::CpuSweep;requestReboot(g.stage);return;}break;default:break;}saveState();}

}

int main(int argc,char**argv){
    socketInitializeDefault(); nxlinkStdio();
    ensureDir(APP_DIR); loadState(); loadPoints();
    PadState pad; padConfigureInput(1,HidNpadStyleSet_NpadStandard); padInitializeDefault(&pad);
    if(!gui::init()){socketExit();return 1;}
    appletSetAutoSleepDisabled(true);

    if(updater::startupCheckAndPrompt(pad,argc,argv)){gui::shutdown();socketExit();return 0;}

    if(!fileExists(DISCLAIMER_FILE)){
        gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="SAFETY NOTICE";m.title="Overclocking can cause crashes or data corruption";m.body={"This Wizard changes Horizon OC clocks, voltages and timings.","Instability can corrupt data and unsafe settings can damage hardware.","Use entirely at your own risk. Keep backups of important data."};m.primaryAction="A  I understand / continue";m.secondaryAction="B  Exit";m.tone=gui::ModalTone::Red;gui::presentModal(m);
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

        if(g.stage==Stage::Hardware&&(k&HidNpadButton_A)){detectHardware();if(g_errorModal){redraw=true;continue;}if(!profile()){modalError("This DRAM ID has no safe automatic profile. Beta 1 will not write guessed timings.");}else{g.stage=Stage::BenchmarkPrep;saveState();}redraw=true;continue;}
        if(g.stage==Stage::BenchmarkPrep&&(k&HidNpadButton_A)){u32 pct=0;PsmChargerType ch=PsmChargerType_Unconnected;batteryReady(pct,ch);if(ch==PsmChargerType_Unconnected){modalError("Connect the charger before starting the benchmark series.");}else if(pct<95){modalError("Charge the console to at least 95% before starting the benchmark series.");}else{g.benchmarkReady=1;g.stage=Stage::RamPreparation;saveState();}redraw=true;continue;}
        if(g.stage==Stage::RamPreparation){if(k&HidNpadButton_Y){prepareRamAuto();redraw=true;continue;}if(k&HidNpadButton_A){const auto*p=profile();HocMonOcPreparation d{};d.uncappedClocks=true;d.hpMode=true;d.ramMaxKHz=std::min<std::uint32_t>(3400,p->maxMHz+100)*1000U;d.vdd2Uv=p->vdd2Mv*1000U;d.vddqUv=p->vddqMv*1000U;d.dvbShift=2;d.socVmaxUv=1200;for(int i=0;i<8;++i)d.timings[i]=p->common.t[i];u32 mm=0;Result rc=hocmonVerifyOcPreparation(&d,&mm);if(R_SUCCEEDED(rc)&&mm==0){g.vdd2GoodUv=int(d.vdd2Uv);g.vdd2CandidateUv=g.vdd2GoodUv-12500;g.vddqGoodMv=int(p->vddqMv);g.vddqCandidateMv=g.vddqGoodMv-10;g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex(p);requestReboot(Stage::RamSweep);}else modalError("Preparation values do not match yet. Set the shown values or use Y for automatic setup.");redraw=true;continue;}}
        if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamCandidate();redraw=true;continue;}if(k&HidNpadButton_X){finishRamSweep();redraw=true;continue;}}
        if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A)){g.stage=Stage::RamStSet;saveState();redraw=true;continue;}
        if(g.stage==Stage::RamStSet){if(k&HidNpadButton_Y){g.ramTimingMode=0;g.stage=Stage::RamVdd2;saveState();redraw=true;continue;}if(k&HidNpadButton_A){const auto*p=profile();std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=p->st.t[i];std::string e;if(!occonfig::setRamTimings(t,e))modalError(e);else requestReboot(Stage::RamStTest);redraw=true;continue;}}
        if(g.stage==Stage::RamStTest&&(k&HidNpadButton_A)){validateSt();redraw=true;continue;}
        if(g.stage==Stage::RamVdd2){if(k&HidNpadButton_X){g.stage=Stage::RamVddq;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runVdd2();redraw=true;continue;}}
        if(g.stage==Stage::RamVddq){if(k&HidNpadButton_X){g.stage=Stage::RamSoc;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runVddq();redraw=true;continue;}}
        if(g.stage==Stage::RamSoc){if(k&HidNpadButton_X){g.stage=Stage::RamFinalGraph;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runSoc();redraw=true;continue;}}
        if(g.stage==Stage::RamFinalGraph&&(k&HidNpadButton_A)){g.stage=Stage::GpuTune;saveState();redraw=true;continue;}
        if(g.stage==Stage::GpuTune){if(k&HidNpadButton_A){runGpuTune();redraw=true;continue;}if(k&HidNpadButton_X&&g.gpuHaveBaseline){std::string e;int f=GPU_FREQS[g.gpuIndex];occonfig::setGpuPoint(f,g.gpuGoodMv,e);finishGpuPoint();requestReboot(g.stage);redraw=true;continue;}}
        if(g.stage==Stage::GpuGraph&&(k&HidNpadButton_A)){g.stage=Stage::GpuRamCombined;saveState();redraw=true;continue;}
        if(g.stage==Stage::GpuRamCombined&&(k&HidNpadButton_A)){runGpuRam();redraw=true;continue;}
        if(g.stage==Stage::CpuHighUv){if(k&HidNpadButton_X){std::string e;occonfig::setCpuTuning(0,g.highUvGood,3,620,750,1200,2397,e);g.highUvApplied=0;g.stage=Stage::CpuSweep;saveState();requestReboot(Stage::CpuSweep);redraw=true;continue;}if(k&HidNpadButton_A){runHighUv();redraw=true;continue;}}
        if(g.stage==Stage::CpuSweep){if(k&HidNpadButton_X){finishCpuSweep();redraw=true;continue;}if(k&HidNpadButton_A){runCpuSweep();redraw=true;continue;}}
        if(g.stage==Stage::CpuTbreak2Set&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setCpuTuning(0,g.highUvGood,2,620,750,1200,2397,e))modalError(e);else requestReboot(Stage::CpuTbreak2Test);redraw=true;continue;}
        if(g.stage==Stage::CpuTbreak2Test&&(k&HidNpadButton_A)){if(!tbreakBoundaryCost(g.tbreak2CostMv)){modalError("1581 MHz TBreak boundary test failed.");}else g.stage=Stage::CpuTbreak3Set;saveState();redraw=true;continue;}
        if(g.stage==Stage::CpuTbreak3Set&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setCpuTuning(0,g.highUvGood,3,620,750,1200,2397,e))modalError(e);else requestReboot(Stage::CpuTbreak3Test);redraw=true;continue;}
        if(g.stage==Stage::CpuTbreak3Test&&(k&HidNpadButton_A)){if(!tbreakBoundaryCost(g.tbreak3CostMv)){modalError("1683 MHz TBreak boundary test failed.");}else{g.finalTbreak=(g.tbreak2CostMv>0&&g.tbreak2CostMv+5<g.tbreak3CostMv)?2:3;std::string e;if(!occonfig::setCpuTuning(0,g.highUvGood,g.finalTbreak,620,750,1200,2397,e))modalError(e);else{g.stage=Stage::CpuGraph;saveState();requestReboot(Stage::CpuGraph);}}redraw=true;continue;}
        if(g.stage==Stage::CpuGraph&&(k&HidNpadButton_A)){g.stage=Stage::CpuRamCombined;saveState();redraw=true;continue;}
        if(g.stage==Stage::CpuRamCombined&&(k&HidNpadButton_A)){runCpuRam();redraw=true;continue;}
        if(g.stage==Stage::Finalize&&(k&HidNpadButton_A)){saveFinal();redraw=true;continue;}
        if(g.stage==Stage::Complete&&(k&HidNpadButton_B))break;
        svcSleepThread(20'000'000);
    }

    clearOverrides(); appletSetAutoSleepDisabled(false); gui::shutdown(); socketExit(); return 0;
}
