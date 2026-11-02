from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta27 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta27 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta27 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta27 unbalanced function: {signature}")
    return src[:pos]+replacement+src[end:]


p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.26','APP_VERSION := 0.1.0-beta.27','version')
p.write_text(s)

# Immediate RAM failure safety.
p=Path('source/stress_tests.cpp')
st=p.read_text()
old_fail='''        if (c.failed.load(std::memory_order_acquire) || c.initError.load(std::memory_order_acquire) != 0)\n            break;'''
new_fail='''        if (c.failed.load(std::memory_order_acquire) || c.initError.load(std::memory_order_acquire) != 0) {\n            // RAM safety: remove CPU/GPU/RAM temporary overrides immediately once\n            // the memory test reports an error/mismatch. Do this before joining the\n            // worker so a marginal RAM clock is not left active while result handling runs.\n            if ((kind == Kind::Ram || kind == Kind::Combined) &&\n                (c.errors.load(std::memory_order_relaxed) != 0 ||\n                 c.mismatches.load(std::memory_order_relaxed) != 0 ||\n                 c.failureKind.load(std::memory_order_relaxed) == FailureMemtester)) {\n                c.stop.store(true, std::memory_order_release);\n                powerguard::clearOverrides();\n            }\n            break;\n        }'''
st=must_replace(st,old_fail,new_fail,'immediate RAM error override cleanup')
p.write_text(st)

# RAM confirmation flow.
p=Path('source/main_oc.cpp')
m=p.read_text()
m=must_replace(m,'    RamSweepResult,\n    RamBenchmark,\n};','    RamSweepResult,\n    RamBenchmark,\n    RamConfirm,\n};','RAM confirmation stage')
m=must_replace(m,
'''    int ramFailedMHz = 0;\n    int ramBenchmarkIndex = 0;''',
'''    int ramFailedMHz = 0;\n    int ramBenchmarkIndex = 0;\n    int ramConfirmMHz = 0;\n    int ramConfirmInProgress = 0;\n    int ramConfirmPassed = 0;\n    int ramConfirmLastFailedMHz = 0;''',
'RAM confirmation state')
# Beta25 inserted custom-baseline fields between the earlier sweep fields, so append
# confirmation persistence at the stable tail markers instead of matching the whole line.
m=must_replace(m,
'W(ramFailedMHz); W(ramBenchmarkIndex);',
'W(ramFailedMHz); W(ramBenchmarkIndex); W(ramConfirmMHz); W(ramConfirmInProgress); W(ramConfirmPassed); W(ramConfirmLastFailedMHz);',
'save RAM confirmation state')
m=must_replace(m,
'R(ramFailedMHz) R(ramBenchmarkIndex)',
'R(ramFailedMHz) R(ramBenchmarkIndex) R(ramConfirmMHz) R(ramConfirmInProgress) R(ramConfirmPassed) R(ramConfirmLastFailedMHz)',
'load RAM confirmation state')
m=must_replace(m,
'if(s==Stage::RamSweepResult) return 2;\n    if(s==Stage::RamBenchmark) return 3;',
'if(s==Stage::RamSweepResult) return 2;\n    if(s==Stage::RamConfirm) return 2;\n    if(s==Stage::RamBenchmark) return 3;',
'confirmation progress step')

new_finish=r'''void finishRamSweep(){
    clearOverrides();
    if(g.ramStableMaxMHz<=0){modalError("No stable RAM point was measured.");return;}
    if(g.ramFailedMHz<=0 && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex){
        const int current=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);
        if(current>g.ramStableMaxMHz) g.ramFailedMHz=current;
    }
    std::string e;
    if(!refreshSweepSocBaselines(e)){modalError("Could not read the HOC SoC curve after the RAM sweep: "+e);return;}
    g.ramRecommendedMHz=g.ramStableMaxMHz;
    g.dvbGood=g.ramUseCurrentBaseline?g.ramBaseDvb:8;
    g.dvbCandidate=std::max(1,g.dvbGood-1);g.dvbApplied=0;
    g.socTuneIndex=-1;g.socTargetRamMHz=0;g.socApplied=0;
    g.ramConfirmMHz=g.ramStableMaxMHz;
    g.ramConfirmInProgress=0;g.ramConfirmPassed=0;g.ramConfirmLastFailedMHz=0;
    g.stage=Stage::RamSweepResult;saveState();
}'''
m=replace_function(m,'void finishRamSweep()',new_finish)

marker='void runDvb(){'
helpers=r'''
int previousRamConfirmationStep(int mhz){
    const auto* pr=profile();
    const int first=pr?oc::firstRamSearchIndex(pr):0;
    int previous=0;
    for(int i=first;i<=g.ramSearchEndIndex;++i){
        const int f=int(oc::RAM_STEPS_MHZ[i]);
        if(f>=mhz) return previous;
        previous=f;
    }
    return previous;
}

void invalidateRamPointsAbove(int mhz){
    for(auto& p:ramPoints)
        if(int(p.requestedMHz)>mhz) p.stable=false;
    savePoints();
}

bool dropRamConfirmationCandidate(int failedMHz){
    const int next=previousRamConfirmationStep(failedMHz);
    g.ramConfirmLastFailedMHz=failedMHz;
    g.ramConfirmPassed=0;
    g.ramConfirmInProgress=0;
    if(next<=0){
        g.ramConfirmMHz=0;g.ramStableMaxMHz=0;g.ramRecommendedMHz=0;
        saveState();
        return false;
    }
    g.ramConfirmMHz=next;
    g.ramStableMaxMHz=next;
    g.ramRecommendedMHz=next;
    invalidateRamPointsAbove(next);
    saveState();
    return true;
}

void recoverInterruptedRamConfirmation(){
    if(g.stage!=Stage::RamConfirm || !g.ramConfirmInProgress) return;
    clearOverrides();
    const int interrupted=g.ramConfirmMHz;
    dropRamConfirmationCandidate(interrupted);
}

void runRamConfirmation(){
    OverrideCleanupScope overrideCleanup;
    if(g.ramConfirmMHz<=0){modalError("No RAM clock remains available for the one-hour confirmation test.");return;}
    std::string e;
    if(!guardRamConfig("RAM Max Clock confirmation"))return;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramConfirmMHz)*1000000U,e)){
        modalError("RAM "+std::to_string(g.ramConfirmMHz)+" MHz could not be activated for confirmation: "+e+" The candidate was not evaluated.");
        return;
    }
    g.ramConfirmInProgress=1;g.ramConfirmPassed=0;saveState();
    const int tested=g.ramConfirmMHz;
    const bool pass=runStress(stress::Kind::Ram,3600,
        "RAM Max Clock - 1 Hour Confirmation",
        "Confirming RAM: "+std::to_string(tested)+" MHz");
    g.ramConfirmInProgress=0;
    clearOverrides();

    if(pass){
        g.ramConfirmPassed=1;
        g.ramConfirmLastFailedMHz=0;
        g.ramStableMaxMHz=tested;
        g.ramRecommendedMHz=tested;
        invalidateRamPointsAbove(tested);
        if(!refreshSweepSocBaselines(e)){modalError("Could not refresh the HOC SoC curve after RAM confirmation: "+e);saveState();return;}
        if(!beginSocCurve(e)){modalError("Could not initialize the per-frequency SoC curve after RAM confirmation: "+e);saveState();return;}
        saveState();
        return;
    }

    if(g_lastStressOutcome==stress::Outcome::Fail){
        if(!dropRamConfirmationCandidate(tested)){
            modalError("The one-hour RAM confirmation failed and no lower tested RAM step remains. Overrides were removed.");
            return;
        }
        return;
    }

    // Cancel, charger removal or another technical abort does not reject this clock.
    g.ramConfirmPassed=0;
    saveState();
}
'''
m=must_replace(m,marker,helpers+'\n'+marker,'RAM confirmation helpers')

old_input='if(g.stage==Stage::RamSweepResult&&(k&HidNpadButton_A)){g.stage=Stage::RamDvb;saveState();redraw=true;continue;}'
new_input='''if(g.stage==Stage::RamSweepResult&&(k&HidNpadButton_A)){g.ramConfirmMHz=g.ramStableMaxMHz;g.ramConfirmInProgress=0;g.ramConfirmPassed=0;g.ramConfirmLastFailedMHz=0;g.stage=Stage::RamConfirm;saveState();redraw=true;continue;}\n        if(g.stage==Stage::RamConfirm&&(k&HidNpadButton_A)){if(g.ramConfirmPassed){g.stage=Stage::RamDvb;saveState();}else runRamConfirmation();redraw=true;continue;}'''
m=must_replace(m,old_input,new_input,'RAM confirmation input flow')
m=must_replace(m,'print(11,"A : Continue to RAM tuning");','print(11,"A : Continue to 1-hour confirmation");','sweep result action wording')

ui_marker='        case Stage::RamDvb:{'
confirm_ui=r'''        case Stage::RamConfirm:{
            recoverInterruptedRamConfirmation();
            if(g.ramConfirmPassed){
                v.stageTitle="RAM Max Clock Confirmed";
                v.instructionTitle="Continue to DVB optimization";
                v.instructionLine1="";v.instructionLine2="";
                gui::begin(v);
                print(1,"The 1-hour RAM confirmation completed with zero detected errors.");
                print(3,"Confirmed Max Clock: "+std::to_string(g.ramConfirmMHz)+" MHz");
                print(5,"The max-clock baseline is now confirmed before any DVB reduction.");
                print(9,"A : Continue to DVB optimization");print(10,"B : Exit");
            }else{
                v.stageTitle="RAM Max Clock Confirmation";
                v.instructionTitle="Run the 1-hour RAM Max Clock confirmation";
                v.instructionLine1="";v.instructionLine2="";
                gui::begin(v);
                if(g.ramConfirmLastFailedMHz>0){
                    print(1,"The previous 1-hour candidate failed or did not complete.");
                    print(3,"Rejected RAM clock: "+std::to_string(g.ramConfirmLastFailedMHz)+" MHz");
                    print(5,"Next candidate: "+std::to_string(g.ramConfirmMHz)+" MHz");
                }else{
                    print(1,"The short sweep found a temporary Max Clock candidate.");
                    print(3,"Before DVB tuning, this clock is validated for 1 hour with the unchanged baseline.");
                    print(5,"Candidate: "+std::to_string(g.ramConfirmMHz)+" MHz");
                }
                print(7,"On RAM errors/mismatches, temporary overrides are removed immediately.");
                print(9,"A : Start 1-hour confirmation");print(10,"B : Exit");
            }
            gui::present();break;}
'''
m=must_replace(m,ui_marker,confirm_ui+ui_marker,'RAM confirmation UI')
m=must_replace(m,
'if((g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph) || g.stage==Stage::RamBenchmark){',
'if((g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph) || g.stage==Stage::RamBenchmark || g.stage==Stage::RamConfirm){',
'confirmation active values range')
p.write_text(m)

main=Path('source/main_oc.cpp').read_text()
stress=Path('source/stress_tests.cpp').read_text()
checks={
    'beta27 version':'0.1.0-beta.27' in Path('Makefile').read_text(),
    'confirmation stage appended':'RamBenchmark,\n    RamConfirm,' in main,
    'confirmation state persisted':'ramConfirmInProgress' in main and 'W(ramConfirmMHz)' in main and 'R(ramConfirmMHz)' in main,
    'one hour test':'runStress(stress::Kind::Ram,3600' in main,
    'sweep result enters confirmation':'g.stage=Stage::RamConfirm' in main,
    'DVB only after confirmed':'if(g.ramConfirmPassed){g.stage=Stage::RamDvb' in main,
    'failed confirmation drops step':'dropRamConfirmationCandidate(tested)' in main and 'previousRamConfirmationStep' in main,
    'freeze recovery':'recoverInterruptedRamConfirmation' in main and 'if(g.stage!=Stage::RamConfirm || !g.ramConfirmInProgress)' in main,
    'confirmation invalidates higher points':'invalidateRamPointsAbove' in main,
    'SoC curve begins after confirmation':'beginSocCurve(e)' in main[main.find('void runRamConfirmation'):main.find('void runDvb')],
    'short sweep remains 60s':'runStress(stress::Kind::Ram,60,"RAM Clock Stability - "' in main,
    'immediate RAM failure cleanup':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress and 'powerguard::clearOverrides();' in stress,
    'charger guard retained':'powerLost' in stress and 'charger.connected' in stress,
    'private force pass retained':'developerForcePass' in stress and 'HidNpadButton_Plus' in stress,
    'private force fail retained':'developerForceFail' in stress and 'HidNpadButton_Minus' in stress,
    'final benchmark retained':'RamBenchmark' in main and 'runFinalRamBenchmarkSweepAutomatic' in main,
    'global beta26 task wrapping retained':'drawWrappedText' in Path('source/gui_console.cpp').read_text(),
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad: raise SystemExit('Beta27 source audit failed: '+', '.join(bad))
