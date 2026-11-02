from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta36 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta36 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta36 opening brace missing: {signature}")
    depth=0;end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1;break
    if end is None: raise SystemExit(f"beta36 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# -----------------------------------------------------------------------------
# Version.
# -----------------------------------------------------------------------------
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.35','APP_VERSION := 0.1.0-beta.36','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# Stress controller: publish a duration-complete checkpoint BEFORE worker stop/join.
# This matters for RAM because the memtester cleanup can still be executing while
# the visible timer is already at 99/100%. A completed 60s test with zero detected
# errors is a provisional sweep PASS even if later cleanup/transition freezes.
# -----------------------------------------------------------------------------
p=Path('source/stress_tests.hpp'); h=p.read_text()
h=must_replace(h,'#include <cstdint>\n#include <string>\n','#include <cstdint>\n#include <functional>\n#include <string>\n','functional include')
h=must_replace(h,
    'Result run(Kind kind, int durationSeconds, const std::string& displayTitle = {}, const std::string& displayContext = {});',
    'Result run(Kind kind, int durationSeconds, const std::string& displayTitle = {}, const std::string& displayContext = {}, const std::function<void()>& onDurationReached = {});',
    'stress callback declaration')
p.write_text(h)

p=Path('source/stress_tests.cpp'); st=p.read_text()
st=must_replace(st,
    'Result run(Kind kind, int durationSeconds, const std::string& displayTitle, const std::string& displayContext) {',
    'Result run(Kind kind, int durationSeconds, const std::string& displayTitle, const std::string& displayContext, const std::function<void()>& onDurationReached) {',
    'stress callback definition')
st=must_replace(st,
    '''        if (elapsed >= std::int64_t(durationSeconds) * 1000LL)\n            break;''',
    '''        if (elapsed >= std::int64_t(durationSeconds) * 1000LL) {\n            // Publish the completed-duration checkpoint before c.stop / worker join.\n            // The RAM sweep uses this to persist the PASS boundary before memtester\n            // teardown or the following clock transition can hard-freeze the console.\n            renderProgress(kind, durationSeconds, std::uint64_t(durationSeconds) * 1000ULL, c, displayTitle, displayContext);\n            if (onDurationReached) onDurationReached();\n            break;\n        }''',
    'duration checkpoint before cleanup')
p.write_text(st)

# -----------------------------------------------------------------------------
# Main wrapper accepts an optional duration checkpoint callback without changing
# any existing caller. Charger retry and outcome tracking remain intact.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()
m=must_replace(m,'#include <fstream>\n','#include <fstream>\n#include <functional>\n','main functional include')
m=must_replace(m,
    'bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx){',
    'bool runStress(stress::Kind k,int seconds,const std::string&title,const std::string&ctx,const std::function<void()>& onDurationReached = {}){',
    'main runStress callback signature')
m=must_replace(m,
    'auto r=stress::run(k,seconds,title,ctx);',
    'auto r=stress::run(k,seconds,title,ctx,onDurationReached);',
    'main runStress callback forwarding')

# -----------------------------------------------------------------------------
# RAM sweep PASS commit helper. It is idempotent so private forced-PASS can still
# commit after runStress returns even though the timed callback did not fire.
# The next index is persisted, but the next candidate is NOT marked in-progress
# until runRamCandidate actually starts applying that clock.
# -----------------------------------------------------------------------------
helper_marker='void runRamCandidate(){'
helpers=r'''
bool ramSweepPointIsCommitted(int mhz){
    for(const auto& p:ramPoints)
        if(p.stable && int(p.requestedMHz)==mhz) return true;
    return false;
}

void commitRamSweepPass(int freq,int socConfigMv,const occonfig::RamConfig& rc){
    if(!ramSweepPointIsCommitted(freq)){
        oc::SweepPoint point;point.domain=oc::Domain::Ram;point.requestedMHz=freq;
        point.realMHz=double(g_active.realHz[2])/1000000.0;
        point.railMv=std::uint32_t(socConfigMv);point.auxMv=std::uint32_t(rc.vdd2Uv/1000U);
        point.performance=0.0;point.latencyNs=0.0;point.bandwidthMBs=0.0;point.batteryPowerW=0.0;
        point.powerReliable=false;point.stable=true;
        point.context="Capability pass / Common / HP off / DVB8 / 66MHz Step Mode";
        recordPoint(ramPoints,point);
    }
    g.ramStableMaxMHz=std::max(g.ramStableMaxMHz,freq);
    g.ramSweepCandidateInProgress=0;
    g.ramSweepCandidateMHz=0;

    // Move the persistent cursor to the NEXT clock as part of the PASS commit.
    // This does not arm/apply that clock. runRamCandidate does that later.
    if(g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex &&
       int(oc::RAM_STEPS_MHZ[g.ramSearchIndex])==freq && g.ramSearchIndex<g.ramSearchEndIndex)
        ++g.ramSearchIndex;
    saveState();
}

'''
m=must_replace(m,helper_marker,helpers+helper_marker,'RAM pass commit helper')

# -----------------------------------------------------------------------------
# Candidate flow: pre-read config, arm exact candidate, stress with pre-cleanup
# PASS checkpoint, then remove override. Never advance twice.
# -----------------------------------------------------------------------------
new_candidate=r'''void runRamCandidate(){
    OverrideCleanupScope overrideCleanup;
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;

    // Read the metadata needed for a PASS before touching a marginal RAM clock.
    const int socTable=socTableForRamMHz(freq);int socConfigMv=0;std::string se;
    if(!occonfig::getSocPoint(socTable,socConfigMv,se) || socConfigMv<=0){
        modalError("Could not read the SoC config point for RAM "+std::to_string(freq)+" MHz: "+se);return;
    }
    occonfig::RamConfig rc{};std::string re;
    if(!occonfig::getRamConfig(rc,re)){
        modalError("Could not read RAM config before stability test: "+re);return;
    }

    // Only from here is this frequency allowed to be blamed for a hard crash.
    g.ramSweepCandidateMHz=freq;
    g.ramSweepCandidateInProgress=1;
    saveState();

    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        clearOverrides();
        // A hard freeze inside setRamOverrides never reaches this line, so the
        // exact candidate journal survives. A returned technical failure is retryable.
        g.ramSweepCandidateInProgress=0;g.ramSweepCandidateMHz=0;saveState();
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This candidate was not evaluated; verify the HOC settings and retry.");
        return;
    }

    const bool pass=runStress(stress::Kind::Ram,60,
        "RAM Clock Stability - "+std::to_string(freq)+" MHz",
        "Testing RAM: "+std::to_string(freq)+" MHz",
        [&](){ commitRamSweepPass(freq,socConfigMv,rc); });

    // If the normal 60s path returned, the callback already committed the point.
    // Private forced-PASS returns before the timer callback, so commit it here too.
    if(pass && !ramSweepPointIsCommitted(freq)) commitRamSweepPass(freq,socConfigMv,rc);

    clearOverrides();
    svcSleepThread(500'000'000); // explicit no-override boundary between RAM clocks

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

    if(freq==int(oc::RAM_STEPS_MHZ[g.ramSearchEndIndex])){
        finishRamSweep();
        return;
    }
    // g.ramSearchIndex already points to the next clock from commitRamSweepPass().
}'''
m=replace_function(m,'void runRamCandidate()',new_candidate)

# -----------------------------------------------------------------------------
# Recovery UI: one candidate only. If no candidate was actually armed, this was
# an interruption between clocks and must NEVER mark the next clock failed.
# -----------------------------------------------------------------------------
old_modal=r'''    if(g_ramSweepResumeModal){
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
    }'''
new_modal=r'''    if(g_ramSweepResumeModal){
        int candidate=g.ramSweepCandidateInProgress?g.ramSweepCandidateMHz:0;
        if(candidate<=0 && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex)
            candidate=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
        gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="RAM SWEEP RESUME";
        if(g.ramSweepCandidateInProgress){
            m.title="Did RAM "+std::to_string(candidate)+" MHz freeze/crash?";
            m.body={"This RAM candidate was active when the Wizard was interrupted."};
            m.primaryAction="A  YES - mark "+std::to_string(candidate)+" MHz failed";
            m.secondaryAction="X  NO - retry "+std::to_string(candidate)+" MHz     B  Exit";
        }else{
            m.title="Continue RAM sweep at "+std::to_string(candidate)+" MHz?";
            m.body={"The previous RAM test completed before the interruption."};
            m.primaryAction="A  Continue with "+std::to_string(candidate)+" MHz";
            m.secondaryAction="B  Exit";
        }
        m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;
    }'''
m=must_replace(m,old_modal,new_modal,'simple RAM resume modal')

old_input=r'''        if(g_ramSweepResumeModal){
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
        }'''
new_input=r'''        if(g_ramSweepResumeModal){
            if(k&HidNpadButton_A){
                g_ramSweepResumeModal=false;
                if(g.ramSweepCandidateInProgress){
                    recoverInterruptedRamSweep();
                }else{
                    clearOverrides();g.testRunning=0;g.testStage=-1;
                    g.ramSweepSessionActive=1;saveState();
                    runRamSweepAutomatic();
                }
                redraw=true;continue;
            }
            if((k&HidNpadButton_X) && g.ramSweepCandidateInProgress){
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
        }'''
m=must_replace(m,old_input,new_input,'RAM resume input modes')

# Recovery helper is only a FAIL path for a genuinely armed candidate.
old_helper='''void recoverInterruptedRamSweep(){\n    clearOverrides();\n    const int failed=interruptedRamSweepCandidateMHz();'''
new_helper='''void recoverInterruptedRamSweep(){\n    clearOverrides();\n    if(!g.ramSweepCandidateInProgress){saveState();return;}\n    const int failed=interruptedRamSweepCandidateMHz();'''
m=must_replace(m,old_helper,new_helper,'armed candidate recovery guard')

# -----------------------------------------------------------------------------
# 1-hour confirmation screen: show one current candidate only. Do not show the
# previously rejected clock or any second candidate in the explanatory text.
# -----------------------------------------------------------------------------
old_confirm=r'''                if(g.ramConfirmLastFailedMHz>0){
                    print(1,"The previous 1-hour candidate failed or did not complete.");
                    print(3,"Rejected RAM clock: "+std::to_string(g.ramConfirmLastFailedMHz)+" MHz");
                    print(5,"Next candidate: "+std::to_string(g.ramConfirmMHz)+" MHz");
                }else{
                    print(1,"The short sweep found a temporary Max Clock candidate.");
                    print(3,"Before DVB tuning, this clock is validated for 1 hour with the unchanged baseline.");
                    print(5,"Candidate: "+std::to_string(g.ramConfirmMHz)+" MHz");
                }
                print(7,"On RAM errors/mismatches, temporary overrides are removed immediately.");'''
new_confirm=r'''                print(1,"Confirm this RAM clock for 1 hour before RAM tuning continues.");
                print(3,"RAM candidate: "+std::to_string(g.ramConfirmMHz)+" MHz");
                print(5,"The test must complete with zero detected RAM errors or mismatches.");
                print(7,"Temporary overrides are removed immediately on detected RAM errors.");'''
m=must_replace(m,old_confirm,new_confirm,'simple one-hour confirmation UI')

p.write_text(m)

# -----------------------------------------------------------------------------
# Audit.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text(); sth=Path('source/stress_tests.hpp').read_text();
rcs=main.find('void runRamCandidate()'); rce=main.find('\n}',rcs)+2; candidate=main[rcs:rce]
checks={
 'beta36 version':'0.1.0-beta.36' in Path('Makefile').read_text(),
 'stress callback API':'onDurationReached' in sth and 'onDurationReached' in stress,
 'checkpoint before join':stress.find('if (onDurationReached) onDurationReached();') < stress.find('for (auto& t : workers)'),
 '100 percent final render':'std::uint64_t(durationSeconds) * 1000ULL' in stress,
 'main forwards callback':'stress::run(k,seconds,title,ctx,onDurationReached)' in main,
 'pass helper':'commitRamSweepPass' in main,
 'pass callback used':'[&](){ commitRamSweepPass(freq,socConfigMv,rc); }' in candidate,
 'pass advances persistent cursor':'++g.ramSearchIndex' in main[main.find('void commitRamSweepPass'):main.find('void runRamCandidate')],
 'next not armed by pass helper':'ramSweepCandidateInProgress=0' in main[main.find('void commitRamSweepPass'):main.find('void runRamCandidate')],
 'candidate armed before override':candidate.find('g.ramSweepCandidateInProgress=1') < candidate.find('setRamOverrides('),
 'explicit no override gap':"svcSleepThread(500'000'000)" in candidate,
 'active popup one frequency':'Did RAM ' in main and 'This RAM candidate was active' in main,
 'no last stable popup':'Last completed stable:' not in main,
 'between candidate does not fail':'The previous RAM test completed before the interruption.' in main,
 'recovery fail requires armed':'if(!g.ramSweepCandidateInProgress){saveState();return;}' in main,
 'simple confirm':'RAM candidate: ' in main and 'Rejected RAM clock:' not in main,
 '60 second sweep':'runStress(stress::Kind::Ram,60' in candidate,
 'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 retained':'DVB8 / 66MHz Step Mode' in candidate,
 'beta32 index retained':'recalculateRamPerformanceIndex(ramPoints)' in main,
 'beta33 prep retained':'AUTOMATIC BASELINE' in Path('source/gui_console.cpp').read_text(),
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta36 source audit failed: '+', '.join(bad))
