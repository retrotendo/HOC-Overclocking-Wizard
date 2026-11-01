from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta22 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta22 function missing: {signature}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta22 opening brace missing: {signature}")
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
        raise SystemExit(f"beta22 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# -----------------------------------------------------------------------------
# Version.
# -----------------------------------------------------------------------------
p = Path('Makefile')
s = p.read_text()
s = must_replace(s, 'APP_VERSION := 0.1.0-beta.21', 'APP_VERSION := 0.1.0-beta.22', 'version')
p.write_text(s)


# -----------------------------------------------------------------------------
# RAM sweep / per-frequency SoC curve.
# -----------------------------------------------------------------------------
p = Path('source/main_oc.cpp')
m = p.read_text()

# Persist which measured RAM point is currently being used for SoC tuning.
m = must_replace(
    m,
    '    int socApplied = 0;\n',
    '    int socApplied = 0;\n    int socTuneIndex = -1;\n    int socTargetRamMHz = 0;\n',
    'SoC curve state fields')
m = must_replace(
    m,
    'W(vdd2GoodUv); W(vdd2CandidateUv); W(vdd2Applied); W(vddqGoodMv); W(vddqCandidateMv); W(vddqApplied); W(socTableMHz); W(socGoodMv); W(socCandidateMv); W(socApplied);',
    'W(vdd2GoodUv); W(vdd2CandidateUv); W(vdd2Applied); W(vddqGoodMv); W(vddqCandidateMv); W(vddqApplied); W(socTableMHz); W(socGoodMv); W(socCandidateMv); W(socApplied); W(socTuneIndex); W(socTargetRamMHz);',
    'save SoC curve state')
m = must_replace(
    m,
    'R(vdd2GoodUv) R(vdd2CandidateUv) R(vdd2Applied) R(vddqGoodMv) R(vddqCandidateMv) R(vddqApplied) R(socTableMHz) R(socGoodMv) R(socCandidateMv) R(socApplied)',
    'R(vdd2GoodUv) R(vdd2CandidateUv) R(vdd2Applied) R(vddqGoodMv) R(vddqCandidateMv) R(vddqApplied) R(socTableMHz) R(socGoodMv) R(socCandidateMv) R(socApplied) R(socTuneIndex) R(socTargetRamMHz)',
    'load SoC curve state')

# Helpers are inserted immediately before finishRamSweep(), after the frequency/SoC helper
# functions already exist in the generated source.
helper_marker = 'void finishRamSweep(){'
helpers = r'''
int socTableForRamMHz(int ramMHz){
    return nearestSocFreq(std::max(1866, ramMHz));
}

int highestStableRamPointIndex(){
    for(int i=int(ramPoints.size())-1;i>=0;--i)
        if(ramPoints[i].stable && int(ramPoints[i].requestedMHz)<=g.ramStableMaxMHz) return i;
    return -1;
}

int previousUniqueSocPointIndex(int fromIndex,int currentTable){
    for(int i=std::min(fromIndex,int(ramPoints.size())-1);i>=0;--i){
        if(!ramPoints[i].stable) continue;
        const int table=socTableForRamMHz(int(ramPoints[i].requestedMHz));
        if(table==currentTable) continue;
        return i;
    }
    return -1;
}

void storeSocForTable(int tableMHz,int configMv){
    for(auto& p:ramPoints){
        if(!p.stable) continue;
        if(socTableForRamMHz(int(p.requestedMHz))==tableMHz) p.railMv=std::uint32_t(std::max(0,configMv));
    }
    savePoints();
}

bool refreshSweepSocBaselines(std::string& error){
    for(auto& p:ramPoints){
        if(!p.stable) continue;
        const int table=socTableForRamMHz(int(p.requestedMHz));
        int mv=0;
        if(!occonfig::getSocPoint(table,mv,error)) return false;
        if(mv<=0){error="HOC SoC table point "+std::to_string(table)+" MHz has no valid configured voltage.";return false;}
        p.railMv=std::uint32_t(mv);
    }
    savePoints();
    return true;
}

bool loadSocTargetFromPoint(int index,std::string& error){
    if(index<0 || index>=int(ramPoints.size()) || !ramPoints[index].stable){error="No stable RAM point is available for SoC tuning.";return false;}
    g.socTuneIndex=index;
    g.socTargetRamMHz=int(ramPoints[index].requestedMHz);
    g.socTableMHz=socTableForRamMHz(g.socTargetRamMHz);
    int mv=int(ramPoints[index].railMv);
    if(mv<=0 && !occonfig::getSocPoint(g.socTableMHz,mv,error)) return false;
    if(mv<=0){error="The SoC baseline for RAM "+std::to_string(g.socTargetRamMHz)+" MHz is invalid.";return false;}
    g.socGoodMv=mv;
    g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
    g.socApplied=0;
    storeSocForTable(g.socTableMHz,g.socGoodMv);
    saveState();
    return true;
}

bool beginSocCurve(std::string& error){
    return loadSocTargetFromPoint(highestStableRamPointIndex(),error);
}

bool advanceSocCurve(std::string& error){
    const int next=previousUniqueSocPointIndex(g.socTuneIndex-1,g.socTableMHz);
    if(next<0){
        g.socTuneIndex=-1;
        g.socTargetRamMHz=0;
        g.socApplied=0;
        saveState();
        return false;
    }
    return loadSocTargetFromPoint(next,error);
}
'''
m = must_replace(m, helper_marker, helpers + '\n' + helper_marker, 'SoC curve helpers')

# The sweep result now keeps every measured point's exact HOC-selected SoC table value and
# initializes the later curve search from the highest stable measured RAM point.
new_finish = r'''void finishRamSweep(){
    clearOverrides();
    analyzeRam();
    if(g.ramStableMaxMHz<=0){modalError("No stable RAM point was measured.");return;}
    if(g.ramFailedMHz<=0 && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex){
        const int current=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
        if(current>g.ramStableMaxMHz) g.ramFailedMHz=current;
    }
    std::string e;
    if(!refreshSweepSocBaselines(e)){modalError("Could not read the HOC SoC curve after the RAM sweep: "+e);return;}
    g.ramRecommendedMHz=g.ramStableMaxMHz;
    g.dvbGood=8;g.dvbCandidate=7;g.dvbApplied=0;
    if(!beginSocCurve(e)){modalError("Could not initialize the per-frequency SoC curve: "+e);return;}
    g.stage=Stage::RamSweepResult;saveState();
}'''
m = replace_function(m, 'void finishRamSweep()', new_finish)

# Each successful RAM sweep point stores the exact HOC config SoC table value, not rounded live
# telemetry. This is the baseline that will later be tuned independently for the curve.
new_ram_candidate = r'''void runRamCandidate(){
    OverrideCleanupScope overrideCleanup;
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This candidate was not evaluated; verify the HOC settings and retry.");
        return;
    }
    if(!runStress(stress::Kind::Ram,60,"RAM Clock Stability - "+std::to_string(freq)+" MHz","Testing RAM: "+std::to_string(freq)+" MHz")){
        if(g_lastStressOutcome==stress::Outcome::Fail){
            g.ramFailedMHz=freq;
            finishRamSweep();
        }else if(g_lastStressOutcome==stress::Outcome::Cancelled){
            modalError("RAM "+std::to_string(freq)+" MHz test was cancelled. This candidate was not evaluated; retry the same clock.");
        }else{
            modalError("RAM "+std::to_string(freq)+" MHz test did not complete. "+g_lastStressDetail+" This candidate was not evaluated; retry the same clock.");
        }
        return;
    }
    auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");
    if(!b.ok){modalError("Memory Benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" This candidate was not evaluated; retry the benchmark.");return;}
    const int socTable=socTableForRamMHz(freq);int socConfigMv=0;std::string se;
    if(!occonfig::getSocPoint(socTable,socConfigMv,se) || socConfigMv<=0){modalError("Could not read the SoC config point for RAM "+std::to_string(freq)+" MHz: "+se);return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(socConfigMv);p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB8 / 66MHz Step Mode";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
m = replace_function(m, 'void runRamCandidate()', new_ram_candidate)

# Timing validation must preserve the initialized SoC curve instead of resetting it to 0 mV.
new_validate_st = r'''void validateSt(){
    OverrideCleanupScope overrideCleanup;
    std::string e;if(!guardRamConfig("ST validation"))return;if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    bool pass=runStress(stress::Kind::Ram,60,"RAM Super Tight Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | DVB "+std::to_string(g.dvbGood));auto b=pass?ocbench::runRam("RAM ST validation"):ocbench::RamResult{};
    if(pass&&b.ok){g.ramTimingMode=1;g.socApplied=0;g.stage=Stage::RamSoc;saveState();}
    else{
        const auto*pr=profile();if(!pr){modalError("Cannot restore Common timings.");return;}
        std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];
        if(!occonfig::setRamTimings(t,e)){modalError(e);return;}
        g.ramTimingMode=0;g.socApplied=0;saveState();requestReboot(Stage::RamSoc);
    }
}'''
m = replace_function(m, 'void validateSt()', new_validate_st)

# Completing the SoC phase now means all retained RAM points already contain their tuned SoC
# table value. Analyze the whole curve only after every unique HOC table point has been handled.
new_finish_soc = r'''void finishSocAndAnalyze(){
    savePoints();analyzeRam();
    if(g.ramRecommendedMHz<=0){modalError("Could not determine a RAM sweet spot from the measured curve.");return;}
    g.socTableMHz=socTableForRamMHz(g.ramRecommendedMHz);
    g.socGoodMv=0;
    for(const auto& p:ramPoints)if(int(p.requestedMHz)==g.ramRecommendedMHz){g.socGoodMv=int(p.railMv);break;}
    if(g.socGoodMv<=0){std::string e;occonfig::getSocPoint(g.socTableMHz,g.socGoodMv,e);}
    g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
    g.socTuneIndex=-1;g.socTargetRamMHz=g.ramRecommendedMHz;g.socApplied=0;
    g.stage=Stage::RamGraph;saveState();
}'''
m = replace_function(m, 'void finishSocAndAnalyze()', new_finish_soc)

# Tune unique HOC SoC table points from the highest measured RAM point downward. Multiple RAM
# sweep frequencies that map to the same HOC table entry all receive the same tuned value.
new_run_soc = r'''void runSoc(){
    OverrideCleanupScope overrideCleanup;
    std::string e;
    if(g.socTuneIndex<0 || g.socTargetRamMHz<=0 || g.socGoodMv<=0){
        if(!beginSocCurve(e)){modalError("Could not initialize the per-frequency SoC curve: "+e);return;}
    }
    if(!g.socApplied){
        if(g.socCandidateMv<=0 || g.socCandidateMv<637){
            storeSocForTable(g.socTableMHz,g.socGoodMv);
            if(!advanceSocCurve(e)){finishSocAndAnalyze();}
            return;
        }
        if(!occonfig::setSocPoint(g.socTableMHz,g.socCandidateMv,e)){modalError(e);return;}
        g.socApplied=1;saveState();requestReboot(Stage::RamSoc);return;
    }
    if(!guardRamConfig("SoC test"))return;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.socTargetRamMHz)*1000000U,e)){modalError(e);return;}
    const bool pass=runStress(stress::Kind::Ram,60,"SoC Voltage Stability","RAM "+std::to_string(g.socTargetRamMHz)+" MHz | SoC "+fmtSocConfigMv(g.socCandidateMv));
    if(pass){
        g.socGoodMv=g.socCandidateMv;
        storeSocForTable(g.socTableMHz,g.socGoodMv);
        g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
        g.socApplied=0;saveState();
        return;
    }
    if(!occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e)){modalError(e);return;}
    g.socApplied=0;
    storeSocForTable(g.socTableMHz,g.socGoodMv);
    if(g_lastStressOutcome!=stress::Outcome::Fail){
        saveState();requestReboot(Stage::RamSoc);return;
    }
    if(advanceSocCurve(e)){
        requestReboot(Stage::RamSoc);
    }else{
        finishSocAndAnalyze();
        if(!g_errorModal)requestReboot(Stage::RamGraph);
    }
}'''
m = replace_function(m, 'void runSoc()', new_run_soc)

# X on the SoC page means keep the last-good value for this table point and continue with the
# next frequency/table point, rather than ending the complete SoC phase.
keep_soc_helper = r'''
void keepCurrentSocAndAdvance(){
    std::string e;
    if(g.socGoodMv<=0){modalError("No valid last-good SoC value is available for this RAM point.");return;}
    const bool needsReboot=g.socApplied!=0;
    if(needsReboot && !occonfig::setSocPoint(g.socTableMHz,g.socGoodMv,e)){modalError(e);return;}
    g.socApplied=0;storeSocForTable(g.socTableMHz,g.socGoodMv);
    if(advanceSocCurve(e)){
        if(needsReboot)requestReboot(Stage::RamSoc);else saveState();
    }else{
        finishSocAndAnalyze();
        if(needsReboot && !g_errorModal)requestReboot(Stage::RamGraph);
    }
}
'''
marker = 'void runSoc(){'
m = must_replace(m, marker, keep_soc_helper + '\n' + marker, 'keep SoC point helper')

# Skipping Tight timings must not wipe the already captured SoC baselines.
m = must_replace(
    m,
    'if(g.stage==Stage::RamStSet){if(k&HidNpadButton_Y){g.ramTimingMode=0;g.socGoodMv=0;g.socApplied=0;g.stage=Stage::RamSoc;saveState();redraw=true;continue;}',
    'if(g.stage==Stage::RamStSet){if(k&HidNpadButton_Y){g.ramTimingMode=0;g.socApplied=0;g.stage=Stage::RamSoc;saveState();redraw=true;continue;}',
    'ST skip preserves SoC curve')

m = must_replace(
    m,
    'if(g.stage==Stage::RamSoc){if(k&HidNpadButton_X){finishSocAndAnalyze();redraw=true;continue;}if(k&HidNpadButton_A){runSoc();redraw=true;continue;}}',
    'if(g.stage==Stage::RamSoc){if(k&HidNpadButton_X){keepCurrentSocAndAdvance();redraw=true;continue;}if(k&HidNpadButton_A){runSoc();redraw=true;continue;}}',
    'SoC X advances one point')

# Clearer per-frequency SoC page and exact .5 mV config formatting.
old_soc_ui = 'case Stage::RamSoc:{v.stageTitle="RAM SoC Voltage";v.instructionTitle=g.socApplied?("Test SoC "+std::to_string(g.socCandidateMv)+" mV"):("Apply SoC "+std::to_string(g.socCandidateMv)+" mV and reboot");v.instructionLine1=g.socApplied?"Run the stability test for this voltage.":"The Wizard will lower SoC by one step.";v.instructionLine2="";gui::begin(v);print(1,"The Wizard will now lower SoC voltage step by step to find the lowest stable value.");print(3,"Last good: "+std::to_string(g.socGoodMv)+" mV");print(4,"Next candidate: "+std::to_string(g.socCandidateMv)+" mV");print(8,"A : Continue");print(9,"X : Keep last good SoC");print(10,"B : Exit");gui::present();break;}'
new_soc_ui = 'case Stage::RamSoc:{v.stageTitle="RAM SoC Curve Tuning";v.instructionTitle=g.socApplied?("Test "+std::to_string(g.socTargetRamMHz)+" MHz at "+fmtSocConfigMv(g.socCandidateMv)):("Apply "+fmtSocConfigMv(g.socCandidateMv)+" and reboot");v.instructionLine1="This SoC table point belongs to the shown RAM frequency.";v.instructionLine2="";gui::begin(v);print(1,"Each measured RAM frequency keeps its own SoC curve value.");print(3,"RAM frequency to validate: "+std::to_string(g.socTargetRamMHz)+" MHz");print(4,"HOC SoC table point: "+std::to_string(g.socTableMHz)+" MHz");print(5,"Last good: "+fmtSocConfigMv(g.socGoodMv));print(6,"Next candidate: "+(g.socCandidateMv>0?fmtSocConfigMv(g.socCandidateMv):std::string("floor reached")));print(9,"A : Continue");print(10,"X : Keep this value / next SoC point");print(11,"B : Exit");gui::present();break;}'
m = must_replace(m, old_soc_ui, new_soc_ui, 'per-frequency SoC UI')

p.write_text(m)


# -----------------------------------------------------------------------------
# Private developer-only stress shortcuts for Pascal's beta testing.
# ZL+ZR+Plus = force PASS, ZL+ZR+Minus = force FAIL.
# They are intentionally absent from normal UI text.
# -----------------------------------------------------------------------------
p = Path('source/stress_tests.cpp')
st = p.read_text()
st = must_replace(
    st,
    '    bool cancelled = false;\n    bool powerLost = false;',
    '    bool cancelled = false;\n    bool powerLost = false;\n    bool developerForcePass = false;\n    bool developerForceFail = false;',
    'developer shortcut state')
st = must_replace(
    st,
    '''        padUpdate(&pad);\n        const u64 down = padGetButtonsDown(&pad);\n        if (down & HidNpadButton_B) {\n            cancelled = true;\n            break;\n        }''',
    '''        padUpdate(&pad);\n        const u64 down = padGetButtonsDown(&pad);\n        const u64 held = padGetButtons(&pad);\n        const u64 developerChord = HidNpadButton_ZL | HidNpadButton_ZR;\n        if ((held & developerChord) == developerChord && (down & HidNpadButton_Plus)) {\n            developerForcePass = true;\n            break;\n        }\n        if ((held & developerChord) == developerChord && (down & HidNpadButton_Minus)) {\n            developerForceFail = true;\n            break;\n        }\n        if (down & HidNpadButton_B) {\n            cancelled = true;\n            break;\n        }''',
    'developer shortcut input')
st = must_replace(
    st,
    '''    if (powerLost) {\n        out.outcome = Outcome::PowerLost;\n        out.detail = chargerError.empty() ? powerguard::kDisconnected : chargerError;\n    } else if (cancelled) {''',
    '''    if (powerLost) {\n        out.outcome = Outcome::PowerLost;\n        out.detail = chargerError.empty() ? powerguard::kDisconnected : chargerError;\n    } else if (developerForcePass) {\n        out.outcome = Outcome::Pass;\n        out.errors = 0;\n        out.mismatches = 0;\n        out.detail = "Private beta shortcut: forced PASS.";\n    } else if (developerForceFail) {\n        out.outcome = Outcome::Fail;\n        out.errors = 1;\n        out.detail = "Private beta shortcut: forced FAIL.";\n    } else if (cancelled) {''',
    'developer shortcut result')
p.write_text(st)


# -----------------------------------------------------------------------------
# Build-time audit.
# -----------------------------------------------------------------------------
main = Path('source/main_oc.cpp').read_text()
stress = Path('source/stress_tests.cpp').read_text()
make = Path('Makefile').read_text()
checks = {
    'beta22 version': '0.1.0-beta.22' in make,
    'SoC curve state persisted': 'socTuneIndex' in main and 'socTargetRamMHz' in main,
    'sweep reads config SoC': 'occonfig::getSocPoint(socTable,socConfigMv,se)' in main,
    'sweep no rounded SoC telemetry': 'p.railMv=std::uint32_t(socConfigMv)' in main,
    'all sweep SoC baselines refreshed': 'refreshSweepSocBaselines' in main,
    'per-frequency SoC target': 'g.socTargetRamMHz' in main and 'RAM frequency to validate:' in main,
    'unique table points iterate': 'previousUniqueSocPointIndex' in main and 'advanceSocCurve' in main,
    'optimized SoC stored back to points': 'storeSocForTable(g.socTableMHz,g.socGoodMv)' in main,
    'SoC zero reset removed from finish sweep': 'g.socGoodMv=0;g.socCandidateMv=0;g.socApplied=0;' not in main[main.find('void finishRamSweep'):main.find('void runRamCandidate')],
    'ST skip preserves curve': 'g.ramTimingMode=0;g.socApplied=0;g.stage=Stage::RamSoc' in main,
    'SoC exact half-step UI': 'fmtSocConfigMv(g.socGoodMv)' in main and 'fmtSocConfigMv(g.socCandidateMv)' in main,
    'private force PASS': 'developerForcePass' in stress and 'HidNpadButton_Plus' in stress,
    'private force FAIL': 'developerForceFail' in stress and 'HidNpadButton_Minus' in stress,
    'shortcuts require both triggers': 'HidNpadButton_ZL | HidNpadButton_ZR' in stress,
    'charger wins over shortcuts': stress.find('if (powerLost)') < stress.find('else if (developerForcePass)'),
    'shortcuts hidden from wizard UI': 'Private beta shortcut' not in main,
    '60 second RAM retained': 'runStress(stress::Kind::Ram,60,"RAM Clock Stability - "' in main,
    'DVB8 retained': 'g.dvbGood=8;g.dvbCandidate=7' in main,
    'result page retained': 'RAM Sweep Result' in main and 'Errors detected at ' in main,
    'task card cleanup retained': 'Next DVB Candidate to Test' in main,
    'audio retained': 'attention::tick(false)' in main,
    'charger guard retained': 'waitForChargerRetry' in main,
}
for name, ok in checks.items():
    print(('PASS ' if ok else 'FAIL ') + name)
bad = [name for name, ok in checks.items() if not ok]
if bad:
    raise SystemExit('Beta22 source audit failed: ' + ', '.join(bad))
