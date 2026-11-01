from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta21 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta21 function missing: {signature}")
    brace = src.find('{', pos)
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
        raise SystemExit(f"beta21 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# Version
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.20','APP_VERSION := 0.1.0-beta.21','version')
p.write_text(s)

p=Path('source/main_oc.cpp')
s=p.read_text()

# Add result stage at the end so existing persisted stage numbers are not shifted.
s=must_replace(s,'    Finalize,\n    Complete,\n};','    Finalize,\n    Complete,\n    RamSweepResult,\n};','RAM sweep result stage')
s=must_replace(s,'    int ramStableMaxMHz = 0;\n','    int ramStableMaxMHz = 0;\n    int ramFailedMHz = 0;\n','RAM failed MHz state')
s=must_replace(s,'W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz);','W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramFailedMHz);','save RAM failed MHz')
s=must_replace(s,'R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz)','R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramFailedMHz)','load RAM failed MHz')
s=must_replace(s,'int progressStep(Stage s) {\n    if(s<=Stage::RamPreparation) return 1;','int progressStep(Stage s) {\n    if(s==Stage::RamSweepResult) return 2;\n    if(s<=Stage::RamPreparation) return 1;','result progress step')

# The sweep always finishes on a result page first. All temporary overrides are removed.
s=replace_function(s,'void finishRamSweep()',r'''void finishRamSweep(){
    clearOverrides();
    analyzeRam();
    if(g.ramStableMaxMHz<=0){modalError("No stable RAM point was measured.");return;}
    if(g.ramFailedMHz<=0 && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex){
        const int current=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
        if(current>g.ramStableMaxMHz) g.ramFailedMHz=current;
    }
    g.ramRecommendedMHz=g.ramStableMaxMHz;
    g.dvbGood=8;g.dvbCandidate=7;g.dvbApplied=0;
    g.socGoodMv=0;g.socCandidateMv=0;g.socApplied=0;
    g.stage=Stage::RamSweepResult;saveState();
}''')

# Overrides are active only for the current candidate. Pass or fail -> clear them.
# An activation/benchmark infrastructure failure is retryable and is not called a RAM stability failure.
s=replace_function(s,'void runRamCandidate()',r'''void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        clearOverrides();
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" Verify the HOC settings and retry.");
        return;
    }
    if(!runStress(stress::Kind::Ram,60,"RAM Clock Stability - "+std::to_string(freq)+" MHz","Testing RAM: "+std::to_string(freq)+" MHz")){
        clearOverrides();g.ramFailedMHz=freq;finishRamSweep();return;
    }
    auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");
    if(!b.ok){
        clearOverrides();
        modalError("Memory Benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" Retry this candidate.");
        return;
    }
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB8 / 66MHz Step Mode";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    clearOverrides();
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}''')

# Stage-specific ACTUAL ACTIVE VALUES. Show what matters for the current step.
side_start=s.index('    if(g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph){')
side_end=s.index('    }else if(g.stage>=Stage::GpuPreparation',side_start)
side=r'''    if(g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph){
        occonfig::RamConfig rc{};std::string ce;
        if(occonfig::getRamConfig(rc,ce)){
            v.haveActiveValues=true;
            if(g.stage==Stage::RamStSet || g.stage==Stage::RamStTest){
                static const char* timingNames[8]={"tRCD","tRP","tRAS","tRRD","tRFC","tRTW","tWTR","tREFI"};
                v.valueCount=8;
                for(int i=0;i<8;++i)setValue(i,timingNames[i],std::to_string(rc.timings[i]));
            }else if(g.stage==Stage::RamDvb){
                v.valueCount=1;setValue(0,"DVB Shift",std::to_string(rc.dvbShift));
            }else if(g.stage==Stage::RamHpSet || g.stage==Stage::RamHpTest){
                v.valueCount=1;setValue(0,"HP Mode",rc.hpMode?"ON":"OFF");
            }else if(g.stage==Stage::RamVdd2){
                v.valueCount=1;setValue(0,"VDD2",fmtMvUv(int(rc.vdd2Uv)));
            }else if(g.stage==Stage::RamVddq){
                v.valueCount=1;setValue(0,"VDDQ",fmtMvUv(int(rc.vddqUv)));
            }else if(g.stage==Stage::RamSoc){
                v.valueCount=2;
                const int sf=g.socTableMHz>0?g.socTableMHz:nearestSocFreq(std::max(1866,g.ramRecommendedMHz));
                int sv=0;std::string se;
                setValue(0,"SoC Table",std::to_string(sf)+" MHz");
                setValue(1,"SoC",occonfig::getSocPoint(sf,sv,se)?(sv>0?fmtSocConfigMv(sv):"No Override"):"unavailable");
            }else if(g.stage==Stage::RamSweep){
                v.valueCount=4;
                setValue(0,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
                setValue(1,"Step Mode",rc.stepMode==0?"66 MHz":"Other");
                setValue(2,"HP Mode",rc.hpMode?"ON":"OFF");
                setValue(3,"DVB Shift",std::to_string(rc.dvbShift));
            }else{
                v.valueCount=3;
                setValue(0,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
                setValue(1,"VDD2",fmtMvUv(int(rc.vdd2Uv)));
                setValue(2,"VDDQ",fmtMvUv(int(rc.vddqUv)));
            }
        }
'''
s=s[:side_start]+side+s[side_end:]

# User-facing RAM pages. LEFT = what happens now. RIGHT = what the user must do now.
# No internal tuning rationale and no duplicate action-button text in YOUR TASK.
ui_start=s.index('        case Stage::RamSweep:')
ui_end=s.index('        case Stage::GpuPreparation:{',ui_start)
ram_ui=r'''        case Stage::RamSweep:{v.stageTitle="RAM Max Clock Search";v.instructionTitle="Start the automatic RAM clock search";v.instructionLine1="Press A to start. The Wizard handles the frequency steps automatically.";v.instructionLine2="";gui::begin(v);print(1,"All RAM frequencies will be tested to find your maximum stable RAM clock.");print(3,"Test clocks are temporary.");print(5,"A crash or freeze can occur during the search.");print(6,"If that happens, reboot CFW and reopen the Wizard.");print(10,"A : Start automatic sweep");print(11,"B : Exit");gui::present();break;}
        case Stage::RamSweepResult:{v.stageTitle="RAM Sweep Result";v.fullWidthLayout=true;gui::begin(v);if(g.ramFailedMHz>0){print(2,"Errors detected at "+std::to_string(g.ramFailedMHz)+" MHz");print(4,"Last stable RAM clock: "+std::to_string(g.ramStableMaxMHz)+" MHz");print(5,"Max clock candidate for now: "+std::to_string(g.ramStableMaxMHz)+" MHz");}else{print(2,"RAM sweep completed without errors.");print(4,"Maximum tested RAM clock: "+std::to_string(g.ramStableMaxMHz)+" MHz");print(5,"Max clock candidate for now: "+std::to_string(g.ramStableMaxMHz)+" MHz");}print(7,"Temporary Overrides cleared.");print(11,"A : Continue to RAM tuning");print(12,"B : Exit");gui::present();break;}
        case Stage::RamDvb:{v.stageTitle="RAM DVB Optimization";v.instructionTitle=g.dvbApplied?("Test DVB Shift "+std::to_string(g.dvbCandidate)):("Continue to apply DVB Shift "+std::to_string(g.dvbCandidate)+" and reboot");v.instructionLine1=g.dvbApplied?"Run the stability test for the active DVB value.":"The Wizard will change only the DVB Shift.";v.instructionLine2="";gui::begin(v);print(1,"The Wizard will now find the lowest stable DVB Shift for your RAM.");print(3,"Last good DVB: "+std::to_string(g.dvbGood));print(4,"Next DVB candidate to test: "+std::to_string(g.dvbCandidate));print(8,"A : "+std::string(g.dvbApplied?"Run candidate test":"Apply DVB Shift + reboot"));print(9,"X : Keep last good DVB");print(10,"B : Exit");gui::present();break;}
        case Stage::RamHpSet:{v.stageTitle="RAM HP Mode";v.instructionTitle="Enable HP Mode and reboot";v.instructionLine1="After reboot, the Wizard will test HP Mode.";v.instructionLine2="";gui::begin(v);print(1,"The Wizard will now test whether HP Mode is stable with your RAM settings.");print(8,"A : Enable HP Mode + reboot");print(9,"Y : Keep HP Mode OFF");print(10,"B : Exit");gui::present();break;}
        case Stage::RamHpTest:{v.stageTitle="RAM HP Mode";v.instructionTitle="Start the HP Mode stability test";v.instructionLine1="HP Mode is active and ready to test.";v.instructionLine2="";gui::begin(v);print(1,"HP Mode is active. Now it will be tested for stability.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStSet:{v.stageTitle="RAM Timing Validation";v.instructionTitle="Set Tight Timings and reboot";v.instructionLine1="After reboot, the Wizard will test the faster timings.";v.instructionLine2="";gui::begin(v);print(1,"So far, the Wizard used standard RAM timings.");print(3,"Now it will test whether faster timings are stable.");print(5,"Timing mode to test: Tight Timings");print(8,"A : Set Tight Timings + reboot");print(9,"Y : Keep Standard Timings");print(10,"B : Exit");gui::present();break;}
        case Stage::RamStTest:{v.stageTitle="RAM Timing Validation";v.instructionTitle="Start the Tight Timings stability test";v.instructionLine1="Tight Timings are active and ready to test.";v.instructionLine2="";gui::begin(v);print(1,"Tight Timings are active. Now they will be tested for stability.");print(3,"RAM: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(8,"A : Start validation");print(10,"B : Exit");gui::present();break;}
        case Stage::RamSoc:{v.stageTitle="RAM SoC Voltage";v.instructionTitle=g.socApplied?("Test SoC "+std::to_string(g.socCandidateMv)+" mV"):("Apply SoC "+std::to_string(g.socCandidateMv)+" mV and reboot");v.instructionLine1=g.socApplied?"Run the stability test for this voltage.":"The Wizard will lower SoC by one step.";v.instructionLine2="";gui::begin(v);print(1,"The Wizard will now lower SoC voltage step by step to find the lowest stable value.");print(3,"Last good: "+std::to_string(g.socGoodMv)+" mV");print(4,"Next candidate: "+std::to_string(g.socCandidateMv)+" mV");print(8,"A : Continue");print(9,"X : Keep last good SoC");print(10,"B : Exit");gui::present();break;}
        case Stage::RamGraph:{v.stageTitle="RAM Efficiency Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="RAM performance / electrical-cost curve";v.chartXLabel="RAM MHz";v.chartCostLabel="SoC electrical cost";v.chartPoints=chart(ramPoints);v.chartSummary="Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz   |   Recommended: "+std::to_string(g.ramRecommendedMHz)+" MHz";gui::begin(v);print(11,"Recommended RAM clock: "+std::to_string(g.ramRecommendedMHz)+" MHz");print(12,"A : Use this RAM clock and continue");print(13,"B : Exit");gui::present();break;}
        case Stage::RamVdd2:{v.stageTitle="RAM VDD2 Optimization";v.instructionTitle=g.vdd2Applied?("Test VDD2 "+fmtMvUv(g.vdd2CandidateUv)):("Apply VDD2 "+fmtMvUv(g.vdd2CandidateUv)+" and reboot");v.instructionLine1=g.vdd2Applied?"Run the stability test for this voltage.":"The Wizard will lower VDD2 by one step.";v.instructionLine2="";gui::begin(v);print(1,"The Wizard will now lower VDD2 step by step to find the lowest stable value.");print(3,"Last good: "+fmtMvUv(g.vdd2GoodUv));print(4,"Next candidate: "+fmtMvUv(g.vdd2CandidateUv));print(8,"A : Continue");print(9,"X : Keep last good VDD2");print(10,"B : Exit");gui::present();break;}
        case Stage::RamVddq:{v.stageTitle="RAM VDDQ Optimization";v.instructionTitle=g.vddqApplied?("Test VDDQ "+std::to_string(g.vddqCandidateMv)+" mV"):("Apply VDDQ "+std::to_string(g.vddqCandidateMv)+" mV and reboot");v.instructionLine1=g.vddqApplied?"Run the stability test for this voltage.":"The Wizard will lower VDDQ by one step.";v.instructionLine2="";gui::begin(v);print(1,"The Wizard will now lower VDDQ step by step to find the lowest stable value.");print(3,"Last good: "+std::to_string(g.vddqGoodMv)+" mV");print(4,"Next candidate: "+std::to_string(g.vddqCandidateMv)+" mV");print(8,"A : Continue");print(9,"X : Keep last good VDDQ");print(10,"B : Exit");gui::present();break;}
        case Stage::RamFinalGraph:{v.stageTitle="RAM Final Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartTitle="Final RAM efficiency curve";v.chartXLabel="RAM MHz";v.chartCostLabel="Electrical cost";v.chartPoints=chart(ramPoints);v.chartSummary="Selected Max: "+std::to_string(g.ramRecommendedMHz)+" MHz   |   VDD2: "+fmtMvUv(g.vdd2GoodUv)+"   |   VDDQ: "+std::to_string(g.vddqGoodMv)+" mV";gui::begin(v);print(12,"A : Continue to GPU tuning");print(13,"B : Exit");gui::present();break;}
'''
s=s[:ui_start]+ram_ui+s[ui_end:]

# Add input handling for the new result page. Existing automatic sweep behavior is retained.
input_marker='''        if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamSweepAutomatic();redraw=true;continue;}}'''
input_new=input_marker+'''\n        if(g.stage==Stage::RamSweepResult&&(k&HidNpadButton_A)){g.stage=Stage::RamDvb;saveState();redraw=true;continue;}'''
s=must_replace(s,input_marker,input_new,'RAM sweep result input')

p.write_text(s)

# Audit generated source before compiling.
m=Path('source/main_oc.cpp').read_text(); make=Path('Makefile').read_text()
checks={
 'version':'0.1.0-beta.21' in make,
 'result stage appended':'Complete,\n    RamSweepResult,' in m,
 'result page':'Errors detected at ' in m and 'Max clock candidate for now' in m,
 'override cleanup after pass':'clearOverrides();\n    if(g.ramSearchIndex' in m,
 'override cleanup after fail':'clearOverrides();g.ramFailedMHz=freq' in m,
 'DVB wording':'Next DVB candidate to test:' in m and 'Continue to apply DVB Shift ' in m,
 'simple sweep info':'All RAM frequencies will be tested to find your maximum stable RAM clock.' in m,
 'simple timing info':'So far, the Wizard used standard RAM timings.' in m and 'Set Tight Timings and reboot' in m,
 'timing actual values':'v.valueCount=8' in m and '"tREFI"' in m,
 'stage-specific HP':'setValue(0,"HP Mode"' in m,
 'stage-specific DVB':'setValue(0,"DVB Shift"' in m,
 'stage-specific rails':'setValue(0,"VDD2"' in m and 'setValue(0,"VDDQ"' in m,
 'old DVB developer text gone':'DVB is optimized before HP and timings' not in m,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta21 source audit failed: '+', '.join(bad))
