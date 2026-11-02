from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta35 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta35 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta35 opening brace missing: {signature}")
    depth=0;end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1;break
    if end is None: raise SystemExit(f"beta35 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.34','APP_VERSION := 0.1.0-beta.35','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()

# Persist whether an automatic RAM sweep session has actually started. This is
# separate from the exact candidate journal so reopening the app between points
# still asks the user what happened instead of guessing.
m=must_replace(m,
    '    int ramSweepCandidateInProgress = 0;\n',
    '    int ramSweepCandidateInProgress = 0;\n    int ramSweepSessionActive = 0;\n',
    'RAM sweep session field')
m=must_replace(m,
    'W(ramFailedMHz); W(ramSweepCandidateMHz); W(ramSweepCandidateInProgress);',
    'W(ramFailedMHz); W(ramSweepCandidateMHz); W(ramSweepCandidateInProgress); W(ramSweepSessionActive);',
    'save RAM sweep session')
m=must_replace(m,
    'R(ramFailedMHz) R(ramSweepCandidateMHz) R(ramSweepCandidateInProgress)',
    'R(ramFailedMHz) R(ramSweepCandidateMHz) R(ramSweepCandidateInProgress) R(ramSweepSessionActive)',
    'load RAM sweep session')

# Separate modal from generic interrupted-test recovery.
m=must_replace(m,
    'bool g_recoveryModal = false;\n',
    'bool g_recoveryModal = false;\nbool g_ramSweepResumeModal = false;\n',
    'RAM sweep resume modal flag')

# Explicitly remove the previous candidate override before committing PASS and
# before the next candidate can be armed. This creates a real no-override gap.
new_candidate=r'''void runRamCandidate(){
    OverrideCleanupScope overrideCleanup;
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;

    // Journal the exact candidate before any dangerous clock transition.
    g.ramSweepCandidateMHz=freq;
    g.ramSweepCandidateInProgress=1;
    saveState();

    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        clearOverrides();
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This candidate was not evaluated; verify the HOC settings and retry.");
        return;
    }

    const bool pass=runStress(stress::Kind::Ram,60,
        "RAM Clock Stability - "+std::to_string(freq)+" MHz",
        "Testing RAM: "+std::to_string(freq)+" MHz");

    // IMPORTANT: return to stock/no temporary override BEFORE committing the
    // result or arming the next RAM step. The previous point is therefore fully
    // closed even if the next clock transition freezes immediately afterwards.
    clearOverrides();
    svcSleepThread(200'000'000);

    if(!pass){
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
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
    if(!occonfig::getSocPoint(socTable,socConfigMv,se) || socConfigMv<=0){
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
        modalError("Could not read the SoC config point for RAM "+std::to_string(freq)+" MHz: "+se);return;
    }
    occonfig::RamConfig rc{};std::string re;if(!occonfig::getRamConfig(rc,re)){
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
        modalError("Could not read RAM config after stability test: "+re);return;
    }
    oc::SweepPoint point;point.domain=oc::Domain::Ram;point.requestedMHz=freq;point.realMHz=double(g_active.realHz[2])/1000000.0;point.railMv=std::uint32_t(socConfigMv);point.auxMv=std::uint32_t(rc.vdd2Uv/1000U);point.performance=0.0;point.latencyNs=0.0;point.bandwidthMBs=0.0;point.batteryPowerW=0.0;point.powerReliable=false;point.stable=true;point.context="Capability pass / Common / HP off / DVB8 / 66MHz Step Mode";
    recordPoint(ramPoints,point);
    g.ramStableMaxMHz=freq;

    // Commit PASS, clear the old candidate journal and persist the NEXT index as
    // one transaction while no temporary RAM override is active.
    g.ramSweepCandidateInProgress=0;
    g.ramSweepCandidateMHz=0;
    if(g.ramSearchIndex>=g.ramSearchEndIndex){
        saveState();
        finishRamSweep();
        return;
    }
    ++g.ramSearchIndex;
    saveState();
    svcSleepThread(400'000'000); // deliberate no-override handoff gap
}'''
m=replace_function(m,'void runRamCandidate()',new_candidate)

# A user-confirmed crash must fail the candidate that was actually armed. If the
# crash occurred in the safe handoff gap, there is no armed candidate; the dialog
# shows the persisted next candidate and lets the user decide whether it was the
# one that crashed.
new_recovery=r'''int interruptedRamSweepCandidateMHz(){
    if(g.ramSweepCandidateInProgress && g.ramSweepCandidateMHz>0)
        return g.ramSweepCandidateMHz;
    if(g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex)
        return int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
    return 0;
}

void recoverInterruptedRamSweep(){
    clearOverrides();
    const int failed=interruptedRamSweepCandidateMHz();
    if(failed<=0){
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;g.testRunning=0;g.testStage=-1;saveState();
        return;
    }

    int lastStable=0;
    for(auto& point:ramPoints){
        if(int(point.requestedMHz)>=failed) point.stable=false;
        if(point.stable && int(point.requestedMHz)<failed)
            lastStable=std::max(lastStable,int(point.requestedMHz));
    }
    if(lastStable<=0 && g.ramStableMaxMHz>0 && g.ramStableMaxMHz<failed)
        lastStable=g.ramStableMaxMHz;

    g.ramFailedMHz=failed;
    g.ramStableMaxMHz=lastStable;
    g.ramRecommendedMHz=lastStable;
    g.ramSweepCandidateInProgress=0;
    g.ramSweepCandidateMHz=0;
    g.testRunning=0;g.testStage=-1;
    savePoints();
    saveState();
    finishRamSweep();
}'''
m=replace_function(m,'void recoverInterruptedRamSweep()',new_recovery)

# finishRamSweep ends the session. This prevents a normal completed/stopped sweep
# from asking the resume question on the next launch.
m=must_replace(m,
    'void finishRamSweep(){\n    clearOverrides();',
    'void finishRamSweep(){\n    g.ramSweepSessionActive=0;\n    clearOverrides();',
    'finish sweep clears session')

# Starting the automatic sweep creates the session before the first candidate.
m=must_replace(m,
    'if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamSweepAutomatic();redraw=true;continue;}',
    'if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){g.ramSweepSessionActive=1;saveState();runRamSweepAutomatic();redraw=true;continue;}',
    'start RAM sweep session')

# On a beta35-created interrupted session, always ask the user instead of making
# an automatic judgement. Old beta34 state files (no session field) keep the old
# recovery behavior for compatibility.
m=must_replace(m,
    'if(g.testRunning || (g.stage==Stage::RamSweep && g.ramSweepCandidateInProgress))g_recoveryModal=true;',
    'if(g.stage==Stage::RamSweep && g.ramSweepSessionActive)g_ramSweepResumeModal=true;\n    else if(g.testRunning || (g.stage==Stage::RamSweep && g.ramSweepCandidateInProgress))g_recoveryModal=true;',
    'startup RAM sweep prompt')

# Render explicit yes/no prompt. It deliberately distinguishes the last fully
# committed PASS from the candidate that was armed/next at interruption.
render_marker='    if(g_recoveryModal && g.stage==Stage::RamSweep && g.ramSweepCandidateInProgress){'
render_block=r'''    if(g_ramSweepResumeModal){
        int candidate=g.ramSweepCandidateInProgress?g.ramSweepCandidateMHz:0;
        if(candidate<=0 && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex)
            candidate=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
        gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="RAM SWEEP RESUME";m.title="Was the RAM sweep interrupted by a freeze/crash?";
        m.body={"Last completed stable: "+(g.ramStableMaxMHz>0?std::to_string(g.ramStableMaxMHz)+" MHz":"none"),
                "Candidate at/after interruption: "+(candidate>0?std::to_string(candidate)+" MHz":"unknown"),
                "Choose YES only if the console froze/crashed while that candidate was being entered or tested."};
        m.primaryAction="A  YES - mark candidate failed";
        m.secondaryAction="X  NO - retry/resume candidate     B  Exit";
        m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;
    }
'''
m=must_replace(m,render_marker,render_block+render_marker,'RAM sweep resume modal render')

# Input handling for the explicit prompt comes before the generic recovery modal.
input_marker='        if(g_recoveryModal){if(k&HidNpadButton_A){g_recoveryModal=false;recoverInterrupted();redraw=true;}else if(k&HidNpadButton_B)break;continue;}'
input_block=r'''        if(g_ramSweepResumeModal){
            if(k&HidNpadButton_A){
                g_ramSweepResumeModal=false;
                recoverInterruptedRamSweep();
                redraw=true;continue;
            }
            if(k&HidNpadButton_X){
                g_ramSweepResumeModal=false;
                clearOverrides();
                g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;
                g.testRunning=0;g.testStage=-1;
                g.ramSweepSessionActive=1;saveState();
                runRamSweepAutomatic();
                redraw=true;continue;
            }
            if(k&HidNpadButton_B){saveState();break;}
            continue;
        }
'''
m=must_replace(m,input_marker,input_block+input_marker,'RAM sweep resume modal input')

p.write_text(m)

# Audit
main=Path('source/main_oc.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text()
rcs=main.find('void runRamCandidate()'); rce=main.find('\n}',rcs)+2; candidate=main[rcs:rce]
checks={
 'beta35 version':'0.1.0-beta.35' in Path('Makefile').read_text(),
 'session persisted':'ramSweepSessionActive' in main and 'W(ramSweepSessionActive)' in main and 'R(ramSweepSessionActive)' in main,
 'session starts before automatic sweep':'g.ramSweepSessionActive=1;saveState();runRamSweepAutomatic()' in main,
 'explicit override clear after stress':candidate.find('clearOverrides();',candidate.find('runStress('))>candidate.find('runStress('),
 'pass recorded after override clear':candidate.find('recordPoint(ramPoints,point)')>candidate.find('clearOverrides();',candidate.find('runStress(')),
 'next index after pass commit':candidate.find('++g.ramSearchIndex')>candidate.find('recordPoint(ramPoints,point)'),
 'no override handoff gap':"svcSleepThread(400'000'000)" in candidate,
 'resume prompt startup':'g_ramSweepResumeModal=true' in main,
 'resume prompt shows last stable':'Last completed stable:' in main,
 'resume prompt shows candidate':'Candidate at/after interruption:' in main,
 'yes marks failed':'recoverInterruptedRamSweep();' in main[main.find('if(g_ramSweepResumeModal)'):],
 'no retries same next':'HidNpadButton_X' in main[main.find('if(g_ramSweepResumeModal)'):main.find('if(g_recoveryModal)',main.find('if(g_ramSweepResumeModal)'))] and 'runRamSweepAutomatic();' in main[main.find('if(g_ramSweepResumeModal)'):],
 'finish clears session':'g.ramSweepSessionActive=0' in main[main.find('void finishRamSweep()'):main.find('void runRamCandidate()')],
 'exact candidate preferred':'if(g.ramSweepCandidateInProgress && g.ramSweepCandidateMHz>0)' in main,
 'fallback next candidate':'oc::RAM_STEPS_MHZ[g.ramSearchIndex]' in main[main.find('int interruptedRamSweepCandidateMHz()'):main.find('void recoverInterruptedRamSweep()')],
 '60 second sweep retained':'runStress(stress::Kind::Ram,60' in candidate,
 '1h confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 retained':'DVB8 / 66MHz Step Mode' in candidate,
 'RAM immediate cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
 'beta32 composite retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
 'beta33 preparation retained':'AUTOMATIC BASELINE' in Path('source/gui_console.cpp').read_text(),
 'target explanation retained':'Read the explanation before choosing your RAM target' in main,
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta35 source audit failed: '+', '.join(bad))
