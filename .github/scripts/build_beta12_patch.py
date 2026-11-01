from pathlib import Path


def replace_function(src: str, signature: str, replacement: str) -> str:
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"Function marker missing: {signature}")
    brace = src.find("{", pos)
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"Unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# Version
p = Path("Makefile")
s = p.read_text().replace("APP_VERSION := 0.1.0-beta.9", "APP_VERSION := 0.1.0-beta.12")
p.write_text(s)

# Exact HOC handheld stock clock is 1331 MHz.
p = Path("source/oc_profiles.hpp")
s = p.read_text()
old = """static constexpr std::uint32_t RAM_STEPS_MHZ[] = {
    2133, 2200, 2266, 2300, 2333, 2400, 2433, 2466, 2500, 2533,"""
new = """static constexpr std::uint32_t RAM_STEPS_MHZ[] = {
    1331, 1600, 1866, 2000,
    2133, 2200, 2266, 2300, 2333, 2400, 2433, 2466, 2500, 2533,"""
if old not in s:
    raise SystemExit("RAM step table marker missing")
s = s.replace(old, new, 1)
p.write_text(s)

p = Path("source/main_oc.cpp")
s = p.read_text()

# Reboot confirmation requires a fresh A press.
old = """    PadState rp; padConfigureInput(1,HidNpadStyleSet_NpadStandard); padInitializeDefault(&rp);
    while(appletMainLoop()){padUpdate(&rp);u64 k=padGetButtonsDown(&rp);if(k&HidNpadButton_A)break;svcSleepThread(20'000'000);}
    Result rc=appletRequestToReboot();"""
new = """    PadState rp; padConfigureInput(1,HidNpadStyleSet_NpadStandard); padInitializeDefault(&rp);
    while(appletMainLoop()){padUpdate(&rp);if(!(padGetButtons(&rp)&HidNpadButton_A))break;svcSleepThread(20'000'000);}
    while(appletMainLoop()){padUpdate(&rp);u64 k=padGetButtonsDown(&rp);if(k&HidNpadButton_A)break;svcSleepThread(20'000'000);}
    Result rc=appletRequestToReboot();"""
if old not in s:
    raise SystemExit("reboot confirmation marker missing")
s = s.replace(old, new, 1)

s = replace_function(
    s,
    "bool guardRamConfig(const char* context)",
    r'''bool guardRamConfig(const char* context){
    const auto*p=profile(); if(!p) return false;
    HocMonOcPreparation d{}; d.uncappedClocks=true; d.hpMode=g.ramHpMode!=0;
    const bool finalMax = g.stage==Stage::RamVdd2 || g.stage==Stage::RamVddq || g.stage==Stage::RamFinalGraph;
    d.ramMaxKHz=u32((finalMax && g.ramRecommendedMHz>0 ? g.ramRecommendedMHz : 3400)*1000U);
    d.vdd2Uv=u32(g.vdd2Applied?g.vdd2CandidateUv:g.vdd2GoodUv); d.vddqUv=u32((g.vddqApplied?g.vddqCandidateMv:g.vddqGoodMv)*1000);
    d.dvbShift=u32(g.dvbApplied?g.dvbCandidate:g.dvbGood); d.socVmaxUv=1200; expectedTimings(d.timings);
    u32 mm=0; Result rc=hocmonVerifyOcPreparation(&d,&mm);
    if(R_FAILED(rc)||mm!=0){modalError(std::string("Unexpected HOC setting before ")+context+". Restore the Wizard values; do not test with multiple changes at once.");return false;}
    return true;
}''',
)

# Clock -> DVB: keep capability maximum as working clock until SoC is complete.
s = replace_function(
    s,
    "void finishRamSweep()",
    r'''void finishRamSweep(){
    analyzeRam();
    if(g.ramStableMaxMHz<=0){modalError("No stable RAM point was measured.");return;}
    g.ramRecommendedMHz=g.ramStableMaxMHz;
    g.dvbGood=5;g.dvbCandidate=4;g.dvbApplied=0;
    g.socGoodMv=0;g.socCandidateMv=0;g.socApplied=0;
    g.stage=Stage::RamDvb;saveState();
}''',
)

s = replace_function(
    s,
    "void runRamCandidate()",
    r'''void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){finishRamSweep();return;}
    if(!runStress(stress::Kind::Ram,45,"RAM Clock Stability - "+std::to_string(freq)+" MHz","Testing RAM: "+std::to_string(freq)+" MHz")){finishRamSweep();return;}
    auto b=ocbench::runRam();if(!b.ok){finishRamSweep();return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB5";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}''',
)

s = replace_function(
    s,
    "void runDvb()",
    r'''void runDvb(){
    std::string e;
    if(!g.dvbApplied){
        if(g.dvbCandidate<1){g.stage=Stage::RamHpSet;saveState();return;}
        if(!occonfig::setDvbShift(g.dvbCandidate,e)){modalError(e);return;}
        g.dvbApplied=1;saveState();requestReboot(Stage::RamDvb);return;
    }
    if(!guardRamConfig("DVB test"))return;
    if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    if(runStress(stress::Kind::Ram,60,"DVB Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | DVB "+std::to_string(g.dvbCandidate))){
        g.dvbGood=g.dvbCandidate;g.dvbCandidate--;g.dvbApplied=0;saveState();
    }else{
        if(!occonfig::setDvbShift(g.dvbGood,e)){modalError(e);return;}
        g.dvbApplied=0;saveState();requestReboot(Stage::RamHpSet);
    }
}''',
)

# DVB -> HP -> Timings. Neither HP nor timings may alter the validated DVB value.
s = replace_function(
    s,
    "void validateHp()",
    r'''void validateHp(){
    std::string e;if(!guardRamConfig("HP validation"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    bool pass=runStress(stress::Kind::Ram,60,"RAM HP Mode Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | DVB "+std::to_string(g.dvbGood));auto b=pass?ocbench::runRam():ocbench::RamResult{};
    if(pass&&b.ok){g.ramHpMode=1;g.stage=Stage::RamStSet;saveState();}
    else{if(!occonfig::setHpMode(false,e)){modalError(e);return;}g.ramHpMode=0;saveState();requestReboot(Stage::RamStSet);}
}''',
)

s = replace_function(
    s,
    "void validateSt()",
    r'''void validateSt(){
    std::string e;if(!guardRamConfig("ST validation"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    bool pass=runStress(stress::Kind::Ram,60,"RAM Super Tight Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | DVB "+std::to_string(g.dvbGood));auto b=pass?ocbench::runRam():ocbench::RamResult{};
    if(pass&&b.ok){g.ramTimingMode=1;g.socGoodMv=0;g.socApplied=0;g.stage=Stage::RamSoc;saveState();}
    else{
        const auto*pr=profile();if(!pr){modalError("Cannot restore Common timings.");return;}
        std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];
        if(!occonfig::setRamTimings(t,e)){modalError(e);return;}
        g.ramTimingMode=0;g.socGoodMv=0;g.socApplied=0;saveState();requestReboot(Stage::RamSoc);
    }
}''',
)

# SoC -> efficiency analysis -> selected Sweet Spot.
s = replace_function(
    s,
    "void runSoc()",
    r'''void finishSocAndAnalyze(){
    for(auto& p:ramPoints){
        if(int(p.requestedMHz)==g.ramStableMaxMHz && g.socGoodMv>0){p.railMv=std::uint32_t(g.socGoodMv);break;}
    }
    savePoints();analyzeRam();
    if(g.ramRecommendedMHz<=0){modalError("Could not determine a RAM sweet spot from the measured curve.");return;}
    g.socTableMHz=nearestSocFreq(g.ramRecommendedMHz);
    std::string e;int selectedSoc=0;if(occonfig::getSocPoint(g.socTableMHz,selectedSoc,e))g.socGoodMv=selectedSoc;
    g.stage=Stage::RamGraph;saveState();
}

void runSoc(){
    initSoc();if(g_errorModal)return;std::string e;
    if(!g.socApplied){
        if(g.socCandidateMv<637||g.socCandidateMv<=0){finishSocAndAnalyze();return;}
        if(!occonfig::setSocPoint(g.socTableMHz,g.socCandidateMv,e)){modalError(e);return;}
        g.socApplied=1;saveState();requestReboot(Stage::RamSoc);return;
    }
    if(!guardRamConfig("SoC test"))return;
    if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    if(runStress(stress::Kind::Ram,60,"SoC Voltage Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | SoC "+std::to_string(g.socCandidateMv)+" mV")){
        g.socGoodMv=g.socCandidateMv;g.socCandidateMv=nextLowerSocMv(g.socGoodMv);g.socApplied=0;saveState();
    }else{
        if(!occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e)){modalError(e);return;}
        g.socApplied=0;finishSocAndAnalyze();if(!g_errorModal)requestReboot(Stage::RamGraph);
    }
}''',
)

# Sweet Spot is already set as RAM Max before these voltage searches.
s = replace_function(
    s,
    "void runVdd2()",
    r'''void runVdd2(){
    std::string e;
    if(!g.vdd2Applied){if(g.vdd2CandidateUv<VDD2_MIN_UV){g.stage=Stage::RamVddq;saveState();return;}if(!occonfig::setVdd2Uv(g.vdd2CandidateUv,e)){modalError(e);return;}g.vdd2Applied=1;saveState();requestReboot(Stage::RamVdd2);return;}
    if(!guardRamConfig("VDD2 test"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    if(runStress(stress::Kind::Ram,60,"VDD2 Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.vdd2GoodUv=g.vdd2CandidateUv;g.vdd2CandidateUv-=12500;g.vdd2Applied=0;saveState();}
    else{if(!occonfig::setVdd2Uv(g.vdd2GoodUv,e)){modalError(e);return;}g.vdd2Applied=0;saveState();requestReboot(Stage::RamVddq);}
}''',
)

s = replace_function(
    s,
    "void runVddq()",
    r'''void runVddq(){
    std::string e;
    if(!g.vddqApplied){if(g.vddqCandidateMv<VDDQ_MIN_MV){g.stage=Stage::RamFinalGraph;saveState();return;}if(!occonfig::setVddq(g.vddqCandidateMv,e)){modalError(e);return;}g.vddqApplied=1;saveState();requestReboot(Stage::RamVddq);return;}
    if(!guardRamConfig("VDDQ test"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    if(runStress(stress::Kind::Ram,60,"VDDQ Stability","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz")){g.vddqGoodMv=g.vddqCandidateMv;g.vddqCandidateMv-=10;g.vddqApplied=0;saveState();}
    else{if(!occonfig::setVddq(g.vddqGoodMv,e)){modalError(e);return;}g.vddqApplied=0;saveState();requestReboot(Stage::RamFinalGraph);}
}''',
)

# Replace visible RAM pages.
start = s.index("        case Stage::RamSweep:")
end = s.index("        case Stage::GpuPreparation:{", start)
ram_ui = r'''        case Stage::RamSweep:{int freq=(g.ramSearchIndex>=0&&g.ramSearchIndex<=g.ramSearchEndIndex)?int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]):0;v.stageTitle="RAM Clock Search";v.instructionTitle="Start test";v.instructionLine1="";v.instructionLine2="A  Start test";gui::begin(v);print(1,"WARNING");print(2,"Crash or freeze may occur.");print(3,"If it happens: reboot CFW and reopen Wizard.");print(4,"Test clocks are temporary.");print(9,"A : Start test");print(10,"X : Stop / use last stable");print(11,"B : Exit");gui::present();break;}
        case Stage::RamDvb:{v.stageTitle="RAM DVB Optimization";v.instructionTitle=g.dvbApplied?"Run candidate test":"Apply candidate";v.instructionLine1="Common timings | HP OFF | only DVB changes.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"DVB is optimized before HP and timings so timing changes cannot hide its real requirement.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"Last good DVB: "+std::to_string(g.dvbGood));print(5,"Candidate DVB: "+std::to_string(g.dvbCandidate));print(8,"A : Continue");print(9,"X : Keep last good DVB");print(10,"B : Exit");gui::present();break;}
        case Stage::RamHpSet:{v.stageTitle="RAM HP Mode";v.instructionTitle="Enable HP Mode";v.instructionLine1="Validated DVB stays unchanged.";v.instructionLine2="A  Enable + reboot";gui::begin(v);print(1,"DVB is already fixed. HP is now tested as the only change.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  DVB: "+std::to_string(g.dvbGood));print(8,"A : Enable HP + reboot");print(9,"Y : Keep HP OFF");print(10,"B : Exit");gui::present();break;}
        case Stage::RamHpTest:{v.stageTitle="RAM HP Mode";v.instructionTitle="Start validation";v.instructionLine1="";v.instructionLine2="A  Start validation";gui::begin(v);print(1,"If HP fails, HP OFF is restored; DVB remains unchanged.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  DVB: "+std::to_string(g.dvbGood));print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStSet:{const auto*p=profile();v.stageTitle="RAM Timing Validation";v.instructionTitle="Try Tight/ST timings";v.instructionLine1="DVB and HP are already fixed and are not changed here.";v.instructionLine2="A  Apply ST + reboot";gui::begin(v);if(p){std::ostringstream t;t<<"ST timings: ";for(int i=0;i<8;++i){if(i)t<<'-';t<<p->st.t[i];}print(2,t.str());}print(4,"ST must pass with the already validated DVB value.");print(8,"A : Apply ST + reboot");print(9,"Y : Keep Common timings");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStTest:{v.stageTitle="RAM Timing Validation";v.instructionTitle="Start validation";v.instructionLine1="";v.instructionLine2="A  Start validation";gui::begin(v);print(1,"A timing failure restores Common timings without raising DVB.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  DVB: "+std::to_string(g.dvbGood));print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::RamSoc:{v.stageTitle="RAM SoC Voltage Optimization";v.instructionTitle=g.socApplied?"Run candidate test":"Apply candidate";v.instructionLine1="Only the SoC point for the capability-max RAM clock changes.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"After SoC is known, the Wizard evaluates the performance/electrical-cost curve.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  SoC table: "+std::to_string(g.socTableMHz)+" MHz");print(4,"Last good: "+std::to_string(g.socGoodMv)+" mV");print(5,"Candidate: "+std::to_string(g.socCandidateMv)+" mV");print(8,"A : Continue");print(9,"X : Keep last good SoC");print(10,"B : Exit");gui::present();break;}
        case Stage::RamGraph:{v.stageTitle="RAM Efficiency Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="RAM performance / electrical-cost curve";v.chartXLabel="RAM MHz";v.chartCostLabel="SoC electrical cost";v.chartPoints=chart(ramPoints);v.chartSummary="Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz   |   Sweet Spot: "+std::to_string(g.ramRecommendedMHz)+" MHz";gui::begin(v);print(11,"Recommended Max RAM Clock: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(12,"A : Set this Max Clock + continue to VDD2");print(13,"B : Exit");gui::present();break;}
        case Stage::RamVdd2:{v.stageTitle="RAM VDD2 Optimization";v.instructionTitle=g.vdd2Applied?"Run candidate test":"Apply candidate";v.instructionLine1="Max RAM is fixed to the selected Sweet Spot.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"Only VDD2 changes; VDDQ stays fixed.");print(3,"RAM Max: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"Last good: "+fmtMvUv(g.vdd2GoodUv));print(5,"Candidate: "+fmtMvUv(g.vdd2CandidateUv));print(8,"A : Continue");print(9,"X : Keep last good VDD2");print(10,"B : Exit");gui::present();break;}
        case Stage::RamVddq:{v.stageTitle="RAM VDDQ Optimization";v.instructionTitle=g.vddqApplied?"Run candidate test":"Apply candidate";v.instructionLine1="Validated VDD2 stays fixed.";v.instructionLine2="A  Continue";gui::begin(v);print(1,"Only VDDQ changes.");print(3,"RAM Max: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(4,"Last good: "+std::to_string(g.vddqGoodMv)+" mV");print(5,"Candidate: "+std::to_string(g.vddqCandidateMv)+" mV");print(8,"A : Continue");print(9,"X : Keep last good VDDQ");print(10,"B : Exit");gui::present();break;}
        case Stage::RamFinalGraph:{v.stageTitle="RAM Final Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="Final RAM efficiency curve";v.chartXLabel="RAM MHz";v.chartCostLabel="Electrical cost";v.chartPoints=chart(ramPoints);v.chartSummary="Selected Max: "+std::to_string(g.ramRecommendedMHz)+" MHz   |   VDD2: "+fmtMvUv(g.vdd2GoodUv)+"   |   VDDQ: "+std::to_string(g.vddqGoodMv)+" mV";gui::begin(v);print(12,"A : Continue to GPU tuning");print(13,"B : Exit");gui::present();break;}
'''
s = s[:start] + ram_ui + s[end:]

# Replace RAM controls to enforce Clock -> DVB -> HP -> Timings -> SoC -> Sweet Spot -> Max -> VDD2 -> VDDQ.
start = s.index("        if(g.stage==Stage::RamSweep)")
end = s.index("        if(g.stage==Stage::GpuPreparation", start)
ram_input = r'''        if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamSweepAutomatic();redraw=true;continue;}if(k&HidNpadButton_X){finishRamSweep();redraw=true;continue;}}
        if(g.stage==Stage::RamDvb){if(k&HidNpadButton_X){std::string e;if(g.dvbApplied){if(!occonfig::setDvbShift(g.dvbGood,e))modalError(e);else{g.dvbApplied=0;requestReboot(Stage::RamHpSet);}}else{g.stage=Stage::RamHpSet;saveState();}redraw=true;continue;}if(k&HidNpadButton_A){runDvb();redraw=true;continue;}}
        if(g.stage==Stage::RamHpSet){if(k&HidNpadButton_Y){g.ramHpMode=0;g.stage=Stage::RamStSet;saveState();redraw=true;continue;}if(k&HidNpadButton_A){std::string e;if(!occonfig::setHpMode(true,e))modalError(e);else{g.ramHpMode=1;requestReboot(Stage::RamHpTest);}redraw=true;continue;}}
        if(g.stage==Stage::RamHpTest&&(k&HidNpadButton_A)){validateHp();redraw=true;continue;}
        if(g.stage==Stage::RamStSet){if(k&HidNpadButton_Y){g.ramTimingMode=0;g.socGoodMv=0;g.socApplied=0;g.stage=Stage::RamSoc;saveState();redraw=true;continue;}if(k&HidNpadButton_A){const auto*p=profile();std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=p->st.t[i];std::string e;if(!occonfig::setRamTimings(t,e))modalError(e);else{g.ramTimingMode=1;requestReboot(Stage::RamStTest);}redraw=true;continue;}}
        if(g.stage==Stage::RamStTest&&(k&HidNpadButton_A)){validateSt();redraw=true;continue;}
        if(g.stage==Stage::RamSoc){if(k&HidNpadButton_X){finishSocAndAnalyze();redraw=true;continue;}if(k&HidNpadButton_A){runSoc();redraw=true;continue;}}
        if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setRamMax(g.ramRecommendedMHz,e))modalError(e);else requestReboot(Stage::RamVdd2);redraw=true;continue;}
        if(g.stage==Stage::RamVdd2){if(k&HidNpadButton_X){g.stage=Stage::RamVddq;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runVdd2();redraw=true;continue;}}
        if(g.stage==Stage::RamVddq){if(k&HidNpadButton_X){g.stage=Stage::RamFinalGraph;saveState();redraw=true;continue;}if(k&HidNpadButton_A){runVddq();redraw=true;continue;}}
        if(g.stage==Stage::RamFinalGraph&&(k&HidNpadButton_A)){g.stage=Stage::GpuPreparation;saveState();redraw=true;continue;}
'''
s = s[:start] + ram_input + s[end:]

# Recovery transitions from beta9's patched source.
s = s.replace(
    "case Stage::RamDvb:if(g.dvbApplied){occonfig::setDvbShift(g.dvbGood,e);g.dvbApplied=0;requestReboot(Stage::RamSoc);return;}break;",
    "case Stage::RamDvb:if(g.dvbApplied){occonfig::setDvbShift(g.dvbGood,e);g.dvbApplied=0;requestReboot(Stage::RamHpSet);return;}break;",
)
s = s.replace(
    "case Stage::RamDvb:if(g.dvbApplied){occonfig::setDvbShift(g.dvbGood,e);g.dvbApplied=0;requestReboot(Stage::RamVdd2);return;}break;",
    "case Stage::RamDvb:if(g.dvbApplied){occonfig::setDvbShift(g.dvbGood,e);g.dvbApplied=0;requestReboot(Stage::RamHpSet);return;}break;",
)
s = s.replace(
    "case Stage::RamSoc:if(g.socApplied){occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e);g.socApplied=0;requestReboot(Stage::RamVdd2);return;}break;",
    "case Stage::RamSoc:if(g.socApplied){occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e);g.socApplied=0;finishSocAndAnalyze();requestReboot(Stage::RamGraph);return;}break;",
)

# Explicit interrupted HP/ST recovery.
marker = "        case Stage::GpuTune:"
if marker in s and "case Stage::RamHpTest:if(g.ramHpMode)" not in s:
    add = '''        case Stage::RamHpTest:if(g.ramHpMode){occonfig::setHpMode(false,e);g.ramHpMode=0;requestReboot(Stage::RamStSet);return;}break;\n        case Stage::RamStTest:if(g.ramTimingMode){const auto*pr=profile();if(pr){std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];occonfig::setRamTimings(t,e);}g.ramTimingMode=0;requestReboot(Stage::RamSoc);return;}break;\n'''
    s = s.replace(marker, add + marker, 1)

p.write_text(s)

# UI KISS rule.
p = Path("source/gui_console.cpp")
s = p.read_text()
old = '''    drawText(x + 24, y + 52, 23, C_TEXT,
             fitText(g_view.instructionTitle.empty() ? "Continue Wizard" : g_view.instructionTitle, 23, w - 48));
    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));

    roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));
    drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));'''
new = '''    std::string task = g_view.instructionTitle.empty() ? "Continue" : g_view.instructionTitle;
    if (!g_view.instructionLine2.empty()) {
        std::string a = trim(g_view.instructionLine2);
        if (a.size() > 3 && (a[0]=='A' || a[0]=='Y' || a[0]=='X' || a[0]=='+')) {
            size_t pos=1; while(pos<a.size() && (a[pos]==' ' || a[pos]==':')) ++pos;
            if(pos<a.size()) task=a.substr(pos);
        }
    }
    drawText(x + 24, y + 58, 25, C_TEXT, fitText(task, 25, w - 48));

    roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));
    drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));'''
if old not in s:
    raise SystemExit("YOUR TASK renderer marker missing")
s = s.replace(old, new, 1)
old = '            const bool heading = raw == "Objective:" || raw == "Test:" || raw == "Keys:" ||'
new = '''            if (raw == "WARNING") {
                drawText(x + 28, by, 16, C_RED, raw);
                by += 27; ++shown; continue;
            }
            const bool heading = raw == "Objective:" || raw == "Test:" || raw == "Keys:" ||'''
if old not in s:
    raise SystemExit("WARNING renderer marker missing")
s = s.replace(old, new, 1)
p.write_text(s)

# Build-time assertions for the agreed flow.
main = Path("source/main_oc.cpp").read_text()
prof = Path("source/oc_profiles.hpp").read_text()
checks = {
    "stock 1331": "1331, 1600, 1866, 2000" in prof,
    "automatic RAM sweep": "runRamSweepAutomatic()" in main,
    "tested clock shown": "RAM Clock Stability - " in main and "Testing RAM: " in main,
    "DVB before HP": "Common timings | HP OFF | only DVB changes." in main,
    "HP before timings": "DVB is already fixed. HP is now tested as the only change." in main,
    "timings preserve DVB": "ST must pass with the already validated DVB value." in main,
    "SoC before sweet spot": "finishSocAndAnalyze()" in main,
    "sweet spot sets max": "setRamMax(g.ramRecommendedMHz,e)" in main,
    "VDD2 after max": "requestReboot(Stage::RamVdd2)" in main,
    "VDDQ final": "requestReboot(Stage::RamFinalGraph)" in main,
    "GPU preserved": "GPU + RAM Integration" in main,
    "CPU preserved": "CPU + RAM Final Validation" in main,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
bad = [name for name, ok in checks.items() if not ok]
if bad:
    raise SystemExit("Beta12 source audit failed: " + ", ".join(bad))
