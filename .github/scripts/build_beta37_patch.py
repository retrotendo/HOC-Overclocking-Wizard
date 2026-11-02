from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta37 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta37 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta37 opening brace missing: {signature}")
    depth=0;end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1;break
    if end is None: raise SystemExit(f"beta37 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# -----------------------------------------------------------------------------
# Version.
# -----------------------------------------------------------------------------
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.36','APP_VERSION := 0.1.0-beta.37','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# Beta36 used the 60s timer edge as a provisional PASS callback. That is too
# early: reaching 100% does not prove the memtester worker returned cleanly.
# Keep the final 100% draw, but do NOT use the callback for RAM sweep PASS.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()

# A dedicated no-override transition screen is drawn BEFORE the next candidate
# is armed. If the next clock freezes during setRamOverrides(), the display
# therefore already names that next clock rather than the previous 100% screen.
helper_marker='void runRamCandidate(){'
transition_helper=r'''
void showNextRamCandidateTransition(int nextFreq){
    clearOverrides();
    gui::ModalView mv;
    mv.version=HOC_WIZARD_VERSION;
    mv.eyebrow="RAM MAX CLOCK SEARCH";
    mv.title="Next RAM candidate: "+std::to_string(nextFreq)+" MHz";
    mv.body={"Previous RAM test completed successfully.",
             "Temporary RAM override is OFF.",
             "Preparing the next RAM clock..."};
    mv.tone=gui::ModalTone::Amber;
    gui::presentModal(mv);
    svcSleepThread(800'000'000LL);
}

'''
m=must_replace(m,helper_marker,transition_helper+helper_marker,'next candidate transition helper')

new_candidate=r'''void runRamCandidate(){
    OverrideCleanupScope overrideCleanup;
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;

    // Read metadata before touching the candidate so a clean PASS can be
    // committed immediately after the stress engine returns normally.
    const int socTable=socTableForRamMHz(freq);int socConfigMv=0;std::string se;
    if(!occonfig::getSocPoint(socTable,socConfigMv,se) || socConfigMv<=0){
        modalError("Could not read the SoC config point for RAM "+std::to_string(freq)+" MHz: "+se);return;
    }
    occonfig::RamConfig rc{};std::string re;
    if(!occonfig::getRamConfig(rc,re)){
        modalError("Could not read RAM config before stability test: "+re);return;
    }

    // From this save onward, a hard freeze belongs to THIS exact clock.
    g.ramSweepCandidateMHz=freq;
    g.ramSweepCandidateInProgress=1;
    saveState();

    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        clearOverrides();
        // A hard freeze inside setRamOverrides never reaches this line and the
        // journal remains intact. A returned technical failure is retryable.
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This candidate was not evaluated; verify the HOC settings and retry.");
        return;
    }

    // IMPORTANT: 100% on screen is only the timer edge. Do not commit PASS
    // until runStress() itself has returned cleanly after memtester shutdown.
    const bool pass=runStress(stress::Kind::Ram,60,
        "RAM Clock Stability - "+std::to_string(freq)+" MHz",
        "Testing RAM: "+std::to_string(freq)+" MHz");

    clearOverrides();
    svcSleepThread(250'000'000LL);

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

    // Only a fully returned PASS is committed. This clears the active candidate
    // journal and advances the persistent cursor to the next RAM clock.
    commitRamSweepPass(freq,socConfigMv,rc);

    if(freq==int(oc::RAM_STEPS_MHZ[g.ramSearchEndIndex])){
        finishRamSweep();
        return;
    }

    // While no override is active, change the visible screen FIRST. The next
    // runRamCandidate() call will then arm/apply this exact clock. If that clock
    // hard-freezes during override activation, this screen remains visible and
    // correctly identifies the candidate the recovery popup will ask about.
    if(g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex){
        const int nextFreq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
        showNextRamCandidateTransition(nextFreq);
    }
}'''
m=replace_function(m,'void runRamCandidate()',new_candidate)

p.write_text(m)

# -----------------------------------------------------------------------------
# Audit: specifically prevent the beta36 regression where timer completion was
# treated as PASS. Preserve all downstream tuning behavior.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text()
cs=main.find('void runRamCandidate()'); ce=main.find('\n}',cs)+2; candidate=main[cs:ce]
checks={
 'beta37 version':'0.1.0-beta.37' in Path('Makefile').read_text(),
 'sweep no timer pass callback':'[&](){ commitRamSweepPass' not in candidate,
 'pass only after stress returns':candidate.find('commitRamSweepPass(freq,socConfigMv,rc)')>candidate.find('const bool pass=runStress'),
 'override cleared before pass commit':candidate.find('clearOverrides();',candidate.find('const bool pass=runStress'))<candidate.find('commitRamSweepPass(freq,socConfigMv,rc)'),
 'candidate armed before override':candidate.find('g.ramSweepCandidateInProgress=1')<candidate.find('setRamOverrides('),
 'hard crash journal survives':'A hard freeze inside setRamOverrides never reaches this line' in candidate,
 'next screen helper':'Next RAM candidate: ' in main and 'Temporary RAM override is OFF.' in main,
 'next screen before next activation':'showNextRamCandidateTransition(nextFreq)' in candidate,
 'transition no override':'void showNextRamCandidateTransition' in main and 'clearOverrides();' in main[main.find('void showNextRamCandidateTransition'):main.find('void runRamCandidate()')],
 'one candidate recovery retained':'Did RAM ' in main and 'Last completed stable:' not in main,
 'simple confirm retained':'RAM candidate: ' in main and 'Rejected RAM clock:' not in main,
 '60 second sweep retained':'runStress(stress::Kind::Ram,60' in candidate,
 'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
 'beta32 index retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
 'beta33 prep retained':'AUTOMATIC BASELINE' in gui,
 'target explanation retained':'Read the explanation before choosing your RAM target' in main,
 'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta37 source audit failed: '+', '.join(bad))
