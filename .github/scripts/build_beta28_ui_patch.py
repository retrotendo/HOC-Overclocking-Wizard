from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta28 ui marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta28 ui function missing: {signature}")
    brace=src.find('{',pos)
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta28 ui unbalanced function: {signature}")
    return src[:pos]+replacement+src[end:]


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0: raise SystemExit(f"beta28 ui braced marker missing: {marker}")
    brace=src.find('{',pos)
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta28 ui unbalanced marker: {marker}")
    return src[:pos]+replacement+src[end:]

p=Path('source/main_oc.cpp')
m=p.read_text()
m=must_replace(m,'bool g_recoveryModal = false;\n','bool g_recoveryModal = false;\nbool g_autoBaselineWarning = false;\n','warning state')

new_prepare=r'''bool prepareRamAuto(){
    const auto*p=profile();
    if(!p){modalError("No automatic RAM profile is available for this memory.");return false;}
    if(!backupOriginal())return false;
    std::string e;
    if(!occonfig::resetHocTuningToDefaults(e)){
        modalError("Could not reset Horizon OC tuning settings to defaults: "+e);return false;
    }
    std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=p->common.t[i];
    if(!occonfig::setRamPreparation(false,3400,p->vdd2Mv,p->vddqMv,8,1150,t,e)){
        modalError("Horizon OC defaults were restored, but the Wizard RAM baseline could not be applied: "+e);return false;
    }
    g.ramUseCurrentBaseline=0;
    g.ramBaseMaxMHz=3400;g.ramBaseStepMode=0;g.ramBaseUncapped=1;g.ramBaseHp=0;
    g.ramBaseVdd2Uv=int(p->vdd2Mv*1000U);g.ramBaseVddqUv=int(p->vddqMv*1000U);
    g.ramBaseDvb=8;g.ramBaseSocVmaxMv=1150;
    g.ramBaseT1=int(t[0]);g.ramBaseT2=int(t[1]);g.ramBaseT3=int(t[2]);g.ramBaseT4=int(t[3]);
    g.ramBaseT5=int(t[4]);g.ramBaseT6=int(t[5]);g.ramBaseT7=int(t[6]);g.ramBaseT8=int(t[7]);
    g.ramHpMode=0;g.ramTimingMode=0;g.dvbGood=8;g.dvbCandidate=7;g.dvbApplied=0;
    g.vdd2GoodUv=int(p->vdd2Mv*1000U);g.vdd2CandidateUv=std::max(VDD2_MIN_UV,g.vdd2GoodUv-12500);
    g.vddqGoodMv=int(p->vddqMv);g.vddqCandidateMv=std::max(VDDQ_MIN_MV,g.vddqGoodMv-10);
    g.socTuneIndex=-1;g.socTargetRamMHz=0;g.socApplied=0;
    g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex();
    saveState();return requestReboot(Stage::RamSweep);
}'''
m=replace_function(m,'bool prepareRamAuto()',new_prepare)

prep_ui=r'''case Stage::RamPreparation:{
            v.stageTitle="RAM Preparation";v.preparationLayout=true;v.hideValuesCard=true;
            const auto*p=profile();
            if(g_autoBaselineWarning){
                v.instructionTitle="Confirm automatic baseline reset";v.instructionLine1="";v.instructionLine2="";
                gui::begin(v);
                print(1,"WARNING");
                print(3,"Automatic baseline will reset all Horizon OC tuning settings and custom voltage tables.");
                print(5,"CPU, GPU, RAM and SoC tuning will return to HOC defaults before the Wizard baseline is applied.");
                print(7,"Wizard RAM baseline: Uncapped ON | RAM Max 3400 | Step 66 MHz | HP OFF | DVB 8 | SoC VMAX 1150.");
                print(9,"Existing custom CPU/GPU/RAM/SoC tuning values will be overwritten.");
                print(12,"A : Reset settings, apply baseline + reboot");
                print(13,"X : Cancel");
            }else{
                v.instructionTitle="Choose a baseline";v.instructionLine1="";v.instructionLine2="";
                gui::begin(v);
                if(!p){
                    print(1,"No safe automatic RAM profile is available for this DRAM ID.");
                    print(3,"You can still use the current HOC settings as the baseline.");
                    print(9,"X : Use my current settings as baseline");
                    print(12,"B : Exit");
                }else{
                    print(1,"Choose how the Wizard should establish its starting configuration.");
                    print(3,"Automatic baseline resets HOC tuning and custom voltage tables to defaults first, then applies the Wizard RAM baseline.");
                    print(5,"My current settings keeps the complete current HOC configuration unchanged and uses it as the baseline.");
                    print(9,"A : Automatic baseline");
                    print(10,"X : Use my current settings as baseline");
                    print(12,"B : Exit");
                }
            }
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamPreparation:',prep_ui)

prep_input=r'''if(g.stage==Stage::RamPreparation){
            if(g_autoBaselineWarning){
                if(k&HidNpadButton_X){g_autoBaselineWarning=false;redraw=true;continue;}
                if(k&HidNpadButton_A){g_autoBaselineWarning=false;g.ramUseCurrentBaseline=0;prepareRamAuto();redraw=true;continue;}
            }else{
                if((k&HidNpadButton_A)&&profile()){g_autoBaselineWarning=true;redraw=true;continue;}
                if(k&HidNpadButton_X){
                    const auto*p=profile();
                    if(!p){modalError("Current RAM baseline is unavailable for this DRAM ID.");redraw=true;continue;}
                    occonfig::RamConfig rc{};std::string e;
                    if(!occonfig::getRamConfig(rc,e)){modalError("Could not read HOC config: "+e);redraw=true;continue;}
                    g.ramUseCurrentBaseline=1;
                    g.ramBaseMaxMHz=int(rc.ramMaxMHz);g.ramBaseStepMode=rc.stepMode;g.ramBaseUncapped=rc.uncappedClocks?1:0;g.ramBaseHp=rc.hpMode?1:0;
                    g.ramBaseVdd2Uv=int(rc.vdd2Uv);g.ramBaseVddqUv=int(rc.vddqUv);g.ramBaseDvb=rc.dvbShift;g.ramBaseSocVmaxMv=rc.socVmaxMv;
                    g.ramBaseT1=int(rc.timings[0]);g.ramBaseT2=int(rc.timings[1]);g.ramBaseT3=int(rc.timings[2]);g.ramBaseT4=int(rc.timings[3]);
                    g.ramBaseT5=int(rc.timings[4]);g.ramBaseT6=int(rc.timings[5]);g.ramBaseT7=int(rc.timings[6]);g.ramBaseT8=int(rc.timings[7]);
                    g.ramHpMode=rc.hpMode?1:0;
                    bool st=true;for(int i=0;i<8;++i)if(rc.timings[i]!=p->st.t[i]){st=false;break;}g.ramTimingMode=st?1:0;
                    g.dvbGood=rc.dvbShift;g.dvbCandidate=std::max(1,rc.dvbShift-1);g.dvbApplied=0;
                    g.vdd2GoodUv=int(rc.vdd2Uv);g.vdd2CandidateUv=std::max(VDD2_MIN_UV,g.vdd2GoodUv-12500);
                    g.vddqGoodMv=int(rc.vddqUv/1000U);g.vddqCandidateMv=std::max(VDDQ_MIN_MV,g.vddqGoodMv-10);
                    g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex();
                    g.stage=Stage::RamSweep;saveState();redraw=true;continue;
                }
            }
        }'''
m=replace_braced(m,'if(g.stage==Stage::RamPreparation){',prep_input)
p.write_text(m)

main=Path('source/main_oc.cpp').read_text();stress=Path('source/stress_tests.cpp').read_text();gui=Path('source/gui_console.cpp').read_text()
prep=main[main.find('case Stage::RamPreparation:'):main.find('case Stage::RamSweep:',main.find('case Stage::RamPreparation:'))]
checks={
 'auto reset before overlay':main.find('resetHocTuningToDefaults(e)')<main.find('setRamPreparation(false,3400',main.find('bool prepareRamAuto()')),
 'wizard DVB8':'setRamPreparation(false,3400,p->vdd2Mv,p->vddqMv,8,1150' in main and 'g.dvbGood=8;g.dvbCandidate=7' in main,
 'wizard 66MHz':'g.ramBaseStepMode=0' in main,
 'wizard HP off':'g.ramBaseHp=0' in main and 'g.ramHpMode=0' in main,
 'warning visible':'Existing custom CPU/GPU/RAM/SoC tuning values will be overwritten.' in prep,
 'two choices':'A : Automatic baseline' in prep and 'X : Use my current settings as baseline' in prep,
 'old manual action gone':'Check manually set values' not in prep and 'Apply baseline automatically + reboot' not in prep,
 'task concise':'v.instructionTitle="Choose a baseline"' in prep,
 'current baseline retained':'g.ramUseCurrentBaseline=1' in main and 'g.ramBaseDvb=rc.dvbShift' in main,
 '1h confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'ram fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
 'final benchmark retained':'runFinalRamBenchmarkSweepAutomatic' in main,
 'global wrapping retained':'drawWrappedText' in gui,
 'private shortcuts retained':'developerForcePass' in stress and 'developerForceFail' in stress,
}
for name,ok in checks.items():print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad:raise SystemExit('Beta28 UI audit failed: '+', '.join(bad))
