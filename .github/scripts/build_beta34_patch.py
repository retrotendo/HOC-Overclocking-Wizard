from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta34 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta34 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta34 opening brace missing: {signature}")
    depth=0;end=None
    for i in range(brace,len(src)):
        if src[i]=='{':depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1;break
    if end is None: raise SystemExit(f"beta34 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]


# Version.
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.33','APP_VERSION := 0.1.0-beta.34','version')
p.write_text(s)

p=Path('source/main_oc.cpp')
m=p.read_text()

# -----------------------------------------------------------------------------
# Persist the exact RAM sweep candidate BEFORE its temporary clock is applied.
# testRunning is too late for this purpose because a marginal RAM clock can hard
# crash while the override is still settling, before stress::run() begins.
# -----------------------------------------------------------------------------
m=must_replace(
    m,
    '    int ramFailedMHz = 0;\n',
    '    int ramFailedMHz = 0;\n    int ramSweepCandidateMHz = 0;\n    int ramSweepCandidateInProgress = 0;\n',
    'RAM sweep crash marker fields')

m=must_replace(
    m,
    'W(ramFailedMHz);',
    'W(ramFailedMHz); W(ramSweepCandidateMHz); W(ramSweepCandidateInProgress);',
    'save RAM sweep crash marker')
m=must_replace(
    m,
    'R(ramFailedMHz)',
    'R(ramFailedMHz) R(ramSweepCandidateMHz) R(ramSweepCandidateInProgress)',
    'load RAM sweep crash marker')

# -----------------------------------------------------------------------------
# Max-clock sweep candidate.
# Marker lifetime covers BOTH override activation/settling and the 60s stress.
# It is cleared only after the attempt returns normally. A hard freeze/reboot
# therefore leaves an unambiguous persisted candidate for boot recovery.
# -----------------------------------------------------------------------------
new_candidate=r'''void runRamCandidate(){
    OverrideCleanupScope overrideCleanup;
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;

    // Crash journal: save the exact candidate before touching the MEM override.
    g.ramSweepCandidateMHz=freq;
    g.ramSweepCandidateInProgress=1;
    saveState();

    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This candidate was not evaluated; verify the HOC settings and retry.");
        return;
    }

    const bool pass=runStress(stress::Kind::Ram,60,
        "RAM Clock Stability - "+std::to_string(freq)+" MHz",
        "Testing RAM: "+std::to_string(freq)+" MHz");

    // If execution reached here, this was not a hard crash. Clear the crash
    // journal before handling PASS/FAIL/cancel/technical outcomes.
    g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();

    if(!pass){
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
    oc::SweepPoint point;point.domain=oc::Domain::Ram;point.requestedMHz=freq;point.realMHz=double(g_active.realHz[2])/1000000.0;point.railMv=std::uint32_t(socConfigMv);point.auxMv=std::uint32_t(rc.vdd2Uv/1000U);point.performance=0.0;point.latencyNs=0.0;point.bandwidthMBs=0.0;point.batteryPowerW=0.0;point.powerReliable=false;point.stable=true;point.context="Capability pass / Common / HP off / DVB8 / 66MHz Step Mode";recordPoint(ramPoints,point);g.ramStableMaxMHz=freq;

    // Only a fully returned PASS is allowed to advance the persistent sweep index.
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
m=replace_function(m,'void runRamCandidate()',new_candidate)

# -----------------------------------------------------------------------------
# Interrupted RAM sweep recovery.
# A hard crash is itself a stability failure. Reject that exact candidate,
# discard any stale point at/above it, restore the last genuinely completed
# stable point, and end the sweep. Never continue to the next higher frequency.
# -----------------------------------------------------------------------------
recover_marker='void recoverInterrupted(){'
helper=r'''
void recoverInterruptedRamSweep(){
    clearOverrides();
    const int failed=g.ramSweepCandidateMHz;
    if(failed<=0){
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
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
    savePoints();
    saveState();

    // First hard-crash candidate defines the capability limit. Do not ever
    // advance to the next clock after recovery.
    finishRamSweep();
}

'''
m=must_replace(m,recover_marker,helper+recover_marker,'RAM sweep recovery helper')

# Add sweep handling before the existing tuning-stage recovery cases.
switch_marker='''    switch(g.stage){\n        case Stage::RamDvb:'''
switch_repl='''    switch(g.stage){\n        case Stage::RamSweep:\n            if(g.ramSweepCandidateInProgress){recoverInterruptedRamSweep();return;}\n            break;\n        case Stage::RamDvb:'''
m=must_replace(m,switch_marker,switch_repl,'RamSweep recovery switch case')

# -----------------------------------------------------------------------------
# Boot detection must not depend only on testRunning. The new crash journal also
# catches freezes during setRamOverrides()/clock settling before stress starts.
# -----------------------------------------------------------------------------
m=must_replace(
    m,
    'if(g.testRunning)g_recoveryModal=true;',
    'if(g.testRunning || (g.stage==Stage::RamSweep && g.ramSweepCandidateInProgress))g_recoveryModal=true;',
    'boot recovery detection')

# Show the exact interrupted clock so the user knows what happened. The existing
# A handler still calls recoverInterrupted(); B still exits without mutating it.
modal_marker='''    if(g_recoveryModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED TEST";'''
modal_repl='''    if(g_recoveryModal && g.stage==Stage::RamSweep && g.ramSweepCandidateInProgress){\n        gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED RAM SWEEP";m.title="RAM "+std::to_string(g.ramSweepCandidateMHz)+" MHz did not complete";\n        m.body={"A crash, freeze or reboot occurred while this RAM candidate was active.","The candidate cannot be considered stable and will be rejected.","The Wizard will return to the last fully completed stable RAM clock and will NOT test a higher clock."};\n        m.primaryAction="A  Mark candidate failed / recover";m.secondaryAction="B  Exit";m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;}\n    if(g_recoveryModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED TEST";'''
m=must_replace(m,modal_marker,modal_repl,'RAM sweep recovery modal')

p.write_text(m)

# -----------------------------------------------------------------------------
# Audit the generated source. This beta changes crash recovery only.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text();stress=Path('source/stress_tests.cpp').read_text();eng=Path('source/oc_engine.cpp').read_text()
rc_start=main.find('void runRamCandidate()');rc_end=main.find('\n}',rc_start)+2;candidate=main[rc_start:rc_end]
recovery_start=main.find('void recoverInterruptedRamSweep()');recovery_end=main.find('void recoverInterrupted()',recovery_start);recovery=main[recovery_start:recovery_end]
checks={
 'beta34 version':'0.1.0-beta.34' in Path('Makefile').read_text(),
 'candidate journal persisted':'ramSweepCandidateMHz' in main and 'ramSweepCandidateInProgress' in main and 'W(ramSweepCandidateMHz)' in main and 'R(ramSweepCandidateMHz)' in main,
 'journal set before override':candidate.find('g.ramSweepCandidateInProgress=1') < candidate.find('setRamOverrides('),
 'journal exact frequency':'g.ramSweepCandidateMHz=freq' in candidate,
 'journal survives hard crash':'g.ramSweepCandidateInProgress=0' in candidate[candidate.find('setRamOverrides('):],
 'index advances only after pass':candidate.find('++g.ramSearchIndex') > candidate.find('recordPoint(ramPoints,point)'),
 'boot sees pre-stress crash':'g.testRunning || (g.stage==Stage::RamSweep && g.ramSweepCandidateInProgress)' in main,
 'recovery names candidate':'INTERRUPTED RAM SWEEP' in main and 'did not complete' in main,
 'hard crash rejected':'g.ramFailedMHz=failed' in recovery,
 'higher points invalidated':'int(point.requestedMHz)>=failed' in recovery and 'point.stable=false' in recovery,
 'last completed stable restored':'lastStable=std::max' in recovery and 'g.ramStableMaxMHz=lastStable' in recovery,
 'no higher continuation':'finishRamSweep();' in recovery and 'NOT test a higher clock' in main,
 'RamSweep recover switch':'case Stage::RamSweep:' in main[main.find('void recoverInterrupted()'):main.find('saveState();',main.find('void recoverInterrupted()'))+20],
 '60 second sweep retained':'runStress(stress::Kind::Ram,60' in candidate,
 'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 retained':'DVB8 / 66MHz Step Mode' in candidate,
 'RAM immediate error cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
 'beta32 composite retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
 'beta33 prep summary retained':'AUTOMATIC BASELINE' in Path('source/gui_console.cpp').read_text() and 'SoC table' in main and 'Stock' in main,
 'target explanation retained':'Read the explanation before choosing your RAM target' in main,
}
for name,ok in checks.items():print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad:raise SystemExit('Beta34 source audit failed: '+', '.join(bad))
