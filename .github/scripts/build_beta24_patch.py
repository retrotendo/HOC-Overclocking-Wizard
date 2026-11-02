from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta24 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta24 function missing: {signature}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta24 opening brace missing: {signature}")
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
        raise SystemExit(f"beta24 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# -----------------------------------------------------------------------------
# Version.
# -----------------------------------------------------------------------------
p = Path('Makefile')
s = p.read_text()
s = must_replace(s, 'APP_VERSION := 0.1.0-beta.23', 'APP_VERSION := 0.1.0-beta.24', 'version')
p.write_text(s)


# -----------------------------------------------------------------------------
# RAM methodology: capability sweep first, performance benchmark only after
# DVB -> HP -> timings -> per-frequency SoC curve are finalized.
# -----------------------------------------------------------------------------
p = Path('source/main_oc.cpp')
m = p.read_text()

# Append a new stage so existing persisted stage numbers remain unchanged.
m = must_replace(m, '    RamSweepResult,\n};', '    RamSweepResult,\n    RamBenchmark,\n};', 'RAM benchmark stage')
m = must_replace(m, '    int ramFailedMHz = 0;\n', '    int ramFailedMHz = 0;\n    int ramBenchmarkIndex = 0;\n', 'RAM benchmark state')
m = must_replace(
    m,
    'W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramFailedMHz);',
    'W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramFailedMHz); W(ramBenchmarkIndex);',
    'save benchmark state')
m = must_replace(
    m,
    'R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramFailedMHz)',
    'R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramFailedMHz) R(ramBenchmarkIndex)',
    'load benchmark state')
m = must_replace(
    m,
    'if(s==Stage::RamSweepResult) return 2;',
    'if(s==Stage::RamSweepResult) return 2;\n    if(s==Stage::RamBenchmark) return 3;',
    'benchmark progress step')

# The post-SoC benchmark uses the already validated DVB/HP/timing settings.
old_guard = 'if(g.stage==Stage::RamSoc){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;}'
new_guard = old_guard + '\n    if(g.stage==Stage::RamBenchmark){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;}'
m = must_replace(m, old_guard, new_guard, 'benchmark config guard')

# Max-clock sweep: stability/capability only. No performance benchmark here.
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
    const int socTable=socTableForRamMHz(freq);int socConfigMv=0;std::string se;
    if(!occonfig::getSocPoint(socTable,socConfigMv,se) || socConfigMv<=0){modalError("Could not read the SoC config point for RAM "+std::to_string(freq)+" MHz: "+se);return;}
    occonfig::RamConfig rc{};std::string re;if(!occonfig::getRamConfig(rc,re)){modalError("Could not read RAM config after stability test: "+re);return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=double(g_active.realHz[2])/1000000.0;p.railMv=std::uint32_t(socConfigMv);p.auxMv=std::uint32_t(rc.vdd2Uv/1000U);p.performance=0.0;p.latencyNs=0.0;p.bandwidthMBs=0.0;p.batteryPowerW=0.0;p.powerReliable=false;p.stable=true;p.context="Capability pass / Common / HP off / DVB8 / 66MHz Step Mode";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
m = replace_function(m, 'void runRamCandidate()', new_ram_candidate)

# finishRamSweep cannot analyze performance anymore because that benchmark intentionally moved later.
new_finish_ram = r'''void finishRamSweep(){
    clearOverrides();
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
m = replace_function(m, 'void finishRamSweep()', new_finish_ram)

# HP and timing validation are stability decisions only. Their performance is measured later under
# the final combined RAM configuration.
new_hp = r'''void validateHp(){
    OverrideCleanupScope overrideCleanup;
    std::string e;if(!guardRamConfig("HP validation"))return;if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    const bool pass=runStress(stress::Kind::Ram,60,"RAM HP Mode Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | DVB "+std::to_string(g.dvbGood));
    if(pass){g.ramHpMode=1;g.stage=Stage::RamStSet;saveState();}
    else{if(!occonfig::setHpMode(false,e)){modalError(e);return;}g.ramHpMode=0;saveState();requestReboot(Stage::RamStSet);}
}'''
m = replace_function(m, 'void validateHp()', new_hp)

new_st = r'''void validateSt(){
    OverrideCleanupScope overrideCleanup;
    std::string e;if(!guardRamConfig("ST validation"))return;if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)){modalError(e);return;}
    const bool pass=runStress(stress::Kind::Ram,60,"RAM Super Tight Validation","RAM "+std::to_string(g.ramRecommendedMHz)+" MHz | DVB "+std::to_string(g.dvbGood));
    if(pass){g.ramTimingMode=1;g.socApplied=0;g.stage=Stage::RamSoc;saveState();}
    else{
        const auto*pr=profile();if(!pr){modalError("Cannot restore Common timings.");return;}
        std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];
        if(!occonfig::setRamTimings(t,e)){modalError(e);return;}
        g.ramTimingMode=0;g.socApplied=0;saveState();requestReboot(Stage::RamSoc);
    }
}'''
m = replace_function(m, 'void validateSt()', new_st)

# After the complete per-frequency SoC curve, prepare a dedicated final performance benchmark sweep.
new_finish_soc = r'''void finishSocAndAnalyze(){
    savePoints();
    g.ramBenchmarkIndex=0;
    g.socTuneIndex=-1;g.socTargetRamMHz=0;g.socApplied=0;
    g.stage=Stage::RamBenchmark;saveState();
}'''
m = replace_function(m, 'void finishSocAndAnalyze()', new_finish_soc)

# Any reboot needed after restoring the last-good final SoC point must return to the benchmark page,
# not skip straight to the graph.
count_reboot_graph = m.count('requestReboot(Stage::RamGraph)')
if count_reboot_graph != 2:
    raise SystemExit(f'beta24 expected 2 SoC->graph reboot markers, found {count_reboot_graph}')
m = m.replace('requestReboot(Stage::RamGraph)', 'requestReboot(Stage::RamBenchmark)')

# Dedicated final benchmark helpers. Every point is measured with the already optimized SoC curve,
# final DVB, final HP decision and final timing decision. Only these measurements feed analyzeRam().
bench_helpers = r'''
int nextRamBenchmarkPoint(int from){
    for(int i=std::max(0,from);i<int(ramPoints.size());++i)
        if(ramPoints[i].stable && int(ramPoints[i].requestedMHz)<=g.ramStableMaxMHz) return i;
    return -1;
}

bool runFinalRamBenchmarkPoint(int index){
    if(index<0 || index>=int(ramPoints.size())) return false;
    auto& p=ramPoints[index];
    const int freq=int(p.requestedMHz);std::string e;
    if(!guardRamConfig("final RAM benchmark"))return false;
    const int table=socTableForRamMHz(freq);int activeSoc=0;
    if(!occonfig::getSocPoint(table,activeSoc,e)){modalError("Could not read the tuned SoC point before RAM benchmark: "+e);return false;}
    if(activeSoc!=int(p.railMv)){
        modalError("RAM benchmark config mismatch at "+std::to_string(freq)+" MHz: SoC is "+fmtSocConfigMv(activeSoc)+", expected tuned value "+fmtSocConfigMv(int(p.railMv))+".");return false;
    }
    OverrideCleanupScope overrideCleanup;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){modalError(e);return false;}
    auto b=ocbench::runRam("Final RAM benchmark: "+std::to_string(freq)+" MHz");
    if(!b.ok){modalError("Final RAM benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" This point was not measured; retry the benchmark sweep.");return false;}
    p.realMHz=b.telemetry.realRamMHz;
    p.performance=b.score;
    p.latencyNs=b.ramNs;
    p.bandwidthMBs=b.cpuRead+b.gpuRead;
    p.batteryPowerW=b.telemetry.batteryPowerW;
    p.powerReliable=false;
    p.context="Final RAM benchmark / tuned SoC / validated DVB-HP-timings";
    savePoints();
    return true;
}

void finishFinalRamBenchmarkSweep(){
    clearOverrides();
    analyzeRam();
    if(g.ramRecommendedMHz<=0){modalError("Could not determine a RAM sweet spot from the final benchmark curve.");return;}
    g.socTableMHz=socTableForRamMHz(g.ramRecommendedMHz);
    g.socGoodMv=0;
    for(const auto& p:ramPoints)if(int(p.requestedMHz)==g.ramRecommendedMHz){g.socGoodMv=int(p.railMv);break;}
    g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
    g.stage=Stage::RamGraph;saveState();
}

void runFinalRamBenchmarkSweepAutomatic(){
    while(g.stage==Stage::RamBenchmark){
        const int idx=nextRamBenchmarkPoint(g.ramBenchmarkIndex);
        if(idx<0){finishFinalRamBenchmarkSweep();return;}
        g.ramBenchmarkIndex=idx;saveState();
        if(!runFinalRamBenchmarkPoint(idx))return;
        g.ramBenchmarkIndex=idx+1;saveState();
    }
}
'''
marker = 'void finishSocAndAnalyze(){'
m = must_replace(m, marker, bench_helpers + '\n' + marker, 'final RAM benchmark helpers')

# RAM benchmark input page: one A press starts the automatic final sweep.
old_input = 'if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setRamMax(g.ramRecommendedMHz,e))modalError(e);else requestReboot(Stage::RamVdd2);redraw=true;continue;}'
new_input = 'if(g.stage==Stage::RamBenchmark&&(k&HidNpadButton_A)){runFinalRamBenchmarkSweepAutomatic();redraw=true;continue;}\n        ' + old_input
m = must_replace(m, old_input, new_input, 'benchmark input handler')

# Add benchmark page immediately before the graph page. Actions remain only on the left.
ui_marker = '        case Stage::RamGraph:{'
bench_ui = r'''        case Stage::RamBenchmark:{v.stageTitle="Final RAM Benchmark Sweep";v.instructionTitle="Start the final RAM performance benchmark sweep";v.instructionLine1="";v.instructionLine2="";gui::begin(v);print(1,"DVB, HP Mode, timings and the per-frequency SoC curve are now fixed.");print(3,"The Wizard will benchmark every stable RAM frequency with those final settings.");print(5,"These measurements are used for the RAM performance / electrical-cost graph.");print(9,"A : Start automatic benchmark sweep");print(10,"B : Exit");gui::present();break;}
'''
m = must_replace(m, ui_marker, bench_ui + ui_marker, 'benchmark UI')

# ACTUAL ACTIVE VALUES must also exist on the appended benchmark stage.
m = must_replace(
    m,
    'if(g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph){',
    'if((g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph) || g.stage==Stage::RamBenchmark){',
    'benchmark active-values range')
branch_marker = '            if(g.stage==Stage::RamStSet || g.stage==Stage::RamStTest){'
branch = r'''            if(g.stage==Stage::RamBenchmark){
                v.valueCount=4;
                int bf=0;const int bi=nextRamBenchmarkPoint(g.ramBenchmarkIndex);if(bi>=0)bf=int(ramPoints[bi].requestedMHz);
                setValue(0,"Benchmark RAM",bf>0?std::to_string(bf)+" MHz":"complete");
                setValue(1,"DVB Shift",std::to_string(rc.dvbShift));
                setValue(2,"HP Mode",rc.hpMode?"ON":"OFF");
                int sv=0;std::string se;const int sf=socTableForRamMHz(std::max(1866,bf>0?bf:g.ramStableMaxMHz));
                setValue(3,"SoC",occonfig::getSocPoint(sf,sv,se)&&sv>0?fmtSocConfigMv(sv):"unavailable");
            }else if(g.stage==Stage::RamStSet || g.stage==Stage::RamStTest){'''
m = must_replace(m, branch_marker, branch, 'benchmark active-values branch')

p.write_text(m)


# -----------------------------------------------------------------------------
# Test UI heartbeat: spinner stays, redundant RUNNING text goes away.
# -----------------------------------------------------------------------------
p = Path('source/gui_console.cpp')
g = p.read_text()
g = must_replace(g, '        drawText(cx - 100, y + 61, 14, C_GREEN, "RUNNING");\n', '', 'remove RUNNING heartbeat label')
g = g.replace('"Running - keep the USB charger connected"', '"Keep the USB charger connected"')
p.write_text(g)


# -----------------------------------------------------------------------------
# Audit the generated source before compiling.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text()
gui=Path('source/gui_console.cpp').read_text()
stress=Path('source/stress_tests.cpp').read_text()

def fn(src, sig, next_sig=None):
    a=src.find(sig)
    if a<0:return ''
    if next_sig:
        b=src.find(next_sig,a+len(sig))
        return src[a:b if b>=0 else len(src)]
    brace=src.find('{',a);depth=0
    for i in range(brace,len(src)):
        if src[i]=='{':depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:return src[a:i+1]
    return src[a:]

candidate=fn(main,'void runRamCandidate()')
hp=fn(main,'void validateHp()')
st=fn(main,'void validateSt()')
soc=fn(main,'void runSoc()')
finish_sweep=fn(main,'void finishRamSweep()')
finish_soc=fn(main,'void finishSocAndAnalyze()')
checks={
    'beta24 version':'0.1.0-beta.24' in Path('Makefile').read_text(),
    'benchmark stage appended':'RamSweepResult,\n    RamBenchmark,' in main,
    'benchmark state persisted':'ramBenchmarkIndex' in main and 'W(ramBenchmarkIndex)' in main and 'R(ramBenchmarkIndex)' in main,
    'max sweep no RAM benchmark':'ocbench::runRam' not in candidate and 'p.performance=0.0' in candidate,
    'max sweep still 60s':'runStress(stress::Kind::Ram,60,' in candidate,
    'finish sweep no performance analysis':'analyzeRam()' not in finish_sweep,
    'HP no benchmark':'ocbench::runRam' not in hp,
    'timings no benchmark':'ocbench::runRam' not in st,
    'SoC no benchmark':'ocbench::runRam' not in soc,
    'SoC transitions to benchmark':'g.stage=Stage::RamBenchmark' in finish_soc,
    'final benchmark automatic':'runFinalRamBenchmarkSweepAutomatic' in main and 'runFinalRamBenchmarkPoint' in main,
    'final benchmark exact tuned SoC':'activeSoc!=int(p.railMv)' in main,
    'final benchmark updates performance':'p.performance=b.score' in main and 'p.latencyNs=b.ramNs' in main,
    'graph analysis after final benchmark':'finishFinalRamBenchmarkSweep' in main and 'analyzeRam();' in fn(main,'void finishFinalRamBenchmarkSweep()'),
    'benchmark guard final RAM settings':'g.stage==Stage::RamBenchmark' in fn(main,'bool guardRamConfig(const char* context)'),
    'benchmark task no duplicate action':'v.instructionTitle="Start the final RAM performance benchmark sweep"' in main and 'v.instructionLine1=""' in main,
    'private force PASS retained':'developerForcePass' in stress,
    'private force FAIL retained':'developerForceFail' in stress,
    'spinner retained':'const int active = int((tick / stepTicks) % 8ULL);' in gui,
    'RUNNING label removed':'"RUNNING"' not in gui,
    'bottom running text removed':'Running - keep the USB charger connected' not in gui,
    'charger reminder retained':'Keep the USB charger connected' in gui,
}
for name,ok in checks.items():print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad:raise SystemExit('Beta24 source audit failed: '+', '.join(bad))
