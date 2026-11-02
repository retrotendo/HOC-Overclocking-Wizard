from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta25 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0: raise SystemExit(f'beta25 braced marker missing: {marker}')
    brace=src.find('{',pos)
    depth=0
    end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1
                break
    if end is None: raise SystemExit(f'beta25 unbalanced marker: {marker}')
    return src[:pos]+replacement+src[end:]

# Version
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.24','APP_VERSION := 0.1.0-beta.25','version')
p.write_text(s)

p=Path('source/main_oc.cpp')
s=p.read_text()

# Persist a complete user-selected RAM preparation baseline. This is only used when the
# advanced "Use current values as baseline" action is selected.
s=must_replace(s,
'''    int ramTimingMode = 0; // 0 Common, 1 ST\n    int ramHpMode = 0;''',
'''    int ramTimingMode = 0; // 0 Common, 1 ST\n    int ramHpMode = 0;\n    int ramUseCurrentBaseline = 0;\n    int ramBaseMaxMHz = 3400;\n    int ramBaseStepMode = 0;\n    int ramBaseUncapped = 1;\n    int ramBaseHp = 0;\n    int ramBaseVdd2Uv = 0;\n    int ramBaseVddqUv = 0;\n    int ramBaseDvb = 8;\n    int ramBaseSocVmaxMv = 1150;\n    int ramBaseT1 = 0; int ramBaseT2 = 0; int ramBaseT3 = 0; int ramBaseT4 = 0;\n    int ramBaseT5 = 0; int ramBaseT6 = 0; int ramBaseT7 = 0; int ramBaseT8 = 0;''',
'custom RAM baseline state')

s=must_replace(s,
'''W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz);''',
'''W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramUseCurrentBaseline); W(ramBaseMaxMHz); W(ramBaseStepMode); W(ramBaseUncapped); W(ramBaseHp); W(ramBaseVdd2Uv); W(ramBaseVddqUv); W(ramBaseDvb); W(ramBaseSocVmaxMv); W(ramBaseT1); W(ramBaseT2); W(ramBaseT3); W(ramBaseT4); W(ramBaseT5); W(ramBaseT6); W(ramBaseT7); W(ramBaseT8);''',
'save custom RAM baseline')
s=must_replace(s,
'''R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz)''',
'''R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramUseCurrentBaseline) R(ramBaseMaxMHz) R(ramBaseStepMode) R(ramBaseUncapped) R(ramBaseHp) R(ramBaseVdd2Uv) R(ramBaseVddqUv) R(ramBaseDvb) R(ramBaseSocVmaxMv) R(ramBaseT1) R(ramBaseT2) R(ramBaseT3) R(ramBaseT4) R(ramBaseT5) R(ramBaseT6) R(ramBaseT7) R(ramBaseT8)''',
'load custom RAM baseline')

# Hardware Detection only: YOUR TASK is just Continue once hardware is detected.
start=s.find('case Stage::Hardware:{')
end=s.find('case Stage::BenchmarkPrep:', start)
if start < 0 or end < 0:
    raise SystemExit('beta25 Hardware stage block missing')
hw=s[start:end]
hw=must_replace(hw,
    'v.instructionTitle=detected?"Hardware detected":"Detect this console";',
    'v.instructionTitle=detected?"Continue":"Detect this console";',
    'hardware task title')
hw=must_replace(hw,
    'v.instructionLine1=detected?"Review the detected RAM before tuning begins.":"The Wizard will identify the installed RAM and select its HOC table.";',
    'v.instructionLine1=detected?"":"The Wizard will identify the installed RAM and select its HOC table.";',
    'hardware task subtitle')
hw=must_replace(hw,
    'v.instructionLine2=detected?"A  Continue":"A  Detect hardware";',
    'v.instructionLine2=detected?"":"A  Detect hardware";',
    'hardware task duplicate action')

# Hardware Detection ACTUAL ACTIVE VALUES: show SoC VMAX config, not a current SoC table point.
old_soc = '''                    int activeRam=int(std::lround(g_active.realHz[2]/1e6));if(activeRam<1866)activeRam=1866;\n                    int socCfg=0;std::string se;const int socFreq=nearestSocFreq(activeRam);\n                    setValue(1,"SoC",occonfig::getSocPoint(socFreq,socCfg,se)?fmtSocConfigMv(socCfg):"unavailable");'''
new_soc = '''                    setValue(1,"SoC Max Voltage",std::to_string(rc.socVmaxMv)+" mV");'''
hw=must_replace(hw,old_soc,new_soc,'hardware SoC VMAX active value')
s=s[:start]+hw+s[end:]

# RAM Preparation UI: expose the already-described current-baseline path as a real action.
prep_start=s.find('case Stage::RamPreparation:{')
prep_end=s.find('case Stage::RamSweep:',prep_start)
if prep_start<0 or prep_end<0: raise SystemExit('beta25 RAM Preparation UI block missing')
prep=s[prep_start:prep_end]
if 'X : Use current values as baseline' not in prep:
    if 'print(11,"Y : Apply baseline automatically + reboot");print(12,"B : Exit");' in prep:
        prep=prep.replace('print(11,"Y : Apply baseline automatically + reboot");print(12,"B : Exit");',
                          'print(11,"Y : Apply baseline automatically + reboot");print(12,"X : Use current values as baseline");print(13,"B : Exit");',1)
    elif 'Y : Apply baseline automatically + reboot' in prep and 'B : Exit' in prep:
        prep=prep.replace('print(12,"B : Exit");','print(12,"X : Use current values as baseline");print(13,"B : Exit");',1)
    else:
        raise SystemExit('beta25 RAM Preparation action rows missing')
s=s[:prep_start]+prep+s[prep_end:]

# RAM config guard: recommended baseline remains the default. When X was selected, the
# snapshot of the user's current HOC values becomes the exact expected baseline for the
# capability sweep and the early DVB/HP phases. Later tuning phases deliberately replace
# the relevant field with their validated candidate values.
new_guard=r'''bool guardRamConfig(const char* context){
    const auto* p=profile(); if(!p) return false;
    occonfig::RamConfig rc{}; std::string e;
    if(!occonfig::getRamConfig(rc,e)){modalError(std::string("Could not read HOC config before ")+context+": "+e);return false;}

    std::uint32_t customT[8]={u32(g.ramBaseT1),u32(g.ramBaseT2),u32(g.ramBaseT3),u32(g.ramBaseT4),u32(g.ramBaseT5),u32(g.ramBaseT6),u32(g.ramBaseT7),u32(g.ramBaseT8)};
    std::uint32_t expectedMax=g.ramUseCurrentBaseline?u32(g.ramBaseMaxMHz):3400U;
    std::uint32_t expectedVdd2=g.ramUseCurrentBaseline?u32(g.ramBaseVdd2Uv):u32(p->vdd2Mv)*1000U;
    std::uint32_t expectedVddq=g.ramUseCurrentBaseline?u32(g.ramBaseVddqUv):u32(p->vddqMv)*1000U;
    int expectedDvb=g.ramUseCurrentBaseline?g.ramBaseDvb:8;
    bool expectedHp=g.ramUseCurrentBaseline?(g.ramBaseHp!=0):false;
    int expectedSocVmax=g.ramUseCurrentBaseline?g.ramBaseSocVmaxMv:1150;
    const std::uint32_t* expectedT=g.ramUseCurrentBaseline?customT:p->common.t;

    if(g.stage==Stage::RamDvb){expectedDvb=g.dvbApplied?g.dvbCandidate:g.dvbGood;}
    if(g.stage==Stage::RamHpTest){expectedDvb=g.dvbGood;expectedHp=true;}
    if(g.stage==Stage::RamStTest){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=p->st.t;}
    if(g.stage==Stage::RamSoc){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;}
    if(g.stage==Stage::RamBenchmark){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;}
    if(g.stage==Stage::RamVdd2){expectedMax=u32(g.ramRecommendedMHz);expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;expectedVdd2=u32(g.vdd2Applied?g.vdd2CandidateUv:g.vdd2GoodUv);}
    if(g.stage==Stage::RamVddq){expectedMax=u32(g.ramRecommendedMHz);expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;expectedVdd2=u32(g.vdd2GoodUv);expectedVddq=u32(g.vddqApplied?g.vddqCandidateMv:g.vddqGoodMv)*1000U;}

    std::vector<std::string> mismatch;
    auto add=[&](const std::string& x){mismatch.push_back(x);};
    if(rc.ramMaxMHz!=expectedMax) add("RAM Max "+std::to_string(rc.ramMaxMHz)+" != "+std::to_string(expectedMax)+" MHz");
    if(rc.vdd2Uv!=expectedVdd2) add("VDD2 "+fmtMvUv(int(rc.vdd2Uv))+" != "+fmtMvUv(int(expectedVdd2)));
    if(rc.vddqUv!=expectedVddq) add("VDDQ "+fmtMvUv(int(rc.vddqUv))+" != "+fmtMvUv(int(expectedVddq)));
    if(rc.dvbShift!=expectedDvb) add("DVB "+std::to_string(rc.dvbShift)+" != "+std::to_string(expectedDvb));
    if(rc.hpMode!=expectedHp) add(std::string("HP ")+(rc.hpMode?"ON":"OFF")+" != "+(expectedHp?"ON":"OFF"));
    if(rc.socVmaxMv!=expectedSocVmax) add("SoC VMAX "+std::to_string(rc.socVmaxMv)+" != "+std::to_string(expectedSocVmax)+" mV");
    for(int i=0;i<8;++i) if(rc.timings[i]!=expectedT[i]){add("RAM timing t"+std::to_string(i+1)+" does not match baseline");break;}

    if(g.stage==Stage::RamSoc && g.socApplied){
        int selected=0;
        if(!occonfig::getSocPoint(g.socTableMHz,selected,e)) add("SoC table point unreadable");
        else if(selected!=g.socCandidateMv) add("SoC point "+fmtSocConfigMv(selected)+" != "+fmtSocConfigMv(g.socCandidateMv));
    }

    if(!mismatch.empty()){
        modalError(std::string("HOC config mismatch before ")+context+": "+mismatch.front()+". Match the Wizard baseline values and retry.");
        return false;
    }
    return true;
}'''
s=replace_braced(s,'bool guardRamConfig(const char* context)',new_guard)

# RAM Preparation input. X snapshots every CONFIG-selected RAM baseline field without
# modifying HOC and proceeds directly to the clock search.
new_handler=r'''if(g.stage==Stage::RamPreparation){
            if(k&HidNpadButton_Y){g.ramUseCurrentBaseline=0;prepareRamAuto();redraw=true;continue;}
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
            if(k&HidNpadButton_A){
                const auto*p=profile();
                if(!p){modalError("Automatic RAM preparation is unavailable for this DRAM ID.");redraw=true;continue;}
                occonfig::RamConfig rc{};std::string e;
                if(!occonfig::getRamConfig(rc,e)){modalError("Could not read HOC config: "+e);redraw=true;continue;}
                std::vector<std::string> mm;
                auto add=[&](const std::string& x){mm.push_back(x);};
                if(rc.ramMaxMHz!=3400) add("RAM Max Clock is "+std::to_string(rc.ramMaxMHz)+" MHz; SET is 3400 MHz");
                if(rc.stepMode!=0) add("RAM Step Mode is not 66 MHz");
                if(!rc.uncappedClocks) add("Uncapped Clocks is OFF; SET is ON");
                if(rc.vdd2Uv!=u32(p->vdd2Mv)*1000U) add("VDD2 is "+fmtMvUv(int(rc.vdd2Uv))+"; SET is "+std::to_string(p->vdd2Mv)+" mV");
                if(rc.vddqUv!=u32(p->vddqMv)*1000U) add("VDDQ is "+fmtMvUv(int(rc.vddqUv))+"; SET is "+std::to_string(p->vddqMv)+" mV");
                if(rc.hpMode) add("HP Mode is ON; SET is OFF");
                if(rc.dvbShift!=8) add("DVB Shift is "+std::to_string(rc.dvbShift)+"; SET is 8");
                if(rc.socVmaxMv!=1150) add("SoC VMAX is "+std::to_string(rc.socVmaxMv)+" mV; SET is 1150 mV");
                for(int i=0;i<8;++i){if(rc.timings[i]!=p->common.t[i]){add("Common Timings do not match SET values");break;}}
                if(!mm.empty()){
                    modalError("RAM Preparation mismatch: "+mm.front()+". The check uses the same HOC config values shown in SET / ACTIVE.");
                    redraw=true;continue;
                }
                g.ramUseCurrentBaseline=0;g.ramHpMode=0;g.ramTimingMode=0;g.dvbGood=8;g.dvbCandidate=7;
                g.vdd2GoodUv=int(rc.vdd2Uv);g.vdd2CandidateUv=std::max(VDD2_MIN_UV,g.vdd2GoodUv-12500);
                g.vddqGoodMv=int(rc.vddqUv/1000U);g.vddqCandidateMv=std::max(VDDQ_MIN_MV,g.vddqGoodMv-10);
                g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex();
                requestReboot(Stage::RamSweep);redraw=true;continue;
            }
        }'''
s=replace_braced(s,'if(g.stage==Stage::RamPreparation){',new_handler)

# Sweep result starts DVB from the selected baseline rather than silently forcing DVB8
# when the user explicitly chose current settings.
old='g.ramRecommendedMHz=g.ramStableMaxMHz;\n    g.dvbGood=8;g.dvbCandidate=7;g.dvbApplied=0;'
new='g.ramRecommendedMHz=g.ramStableMaxMHz;\n    if(g.ramUseCurrentBaseline){g.dvbGood=g.ramBaseDvb;g.dvbCandidate=std::max(1,g.ramBaseDvb-1);}else{g.dvbGood=8;g.dvbCandidate=7;}g.dvbApplied=0;'
s=must_replace(s,old,new,'sweep result baseline DVB')

p.write_text(s)

# Audit only requested changes plus retained core flow.
main=p.read_text()
start=main.find('case Stage::Hardware:{');end=main.find('case Stage::BenchmarkPrep:',start);hw=main[start:end]
ps=main.find('case Stage::RamPreparation:{');pe=main.find('case Stage::RamSweep:',ps);prep=main[ps:pe]
hs=main.find('if(g.stage==Stage::RamPreparation){');he=main.find('if(g.stage==Stage::RamSweep)',hs);handler=main[hs:he]
checks={
    'beta25 version':'0.1.0-beta.25' in Path('Makefile').read_text(),
    'hardware task Continue only':'v.instructionTitle=detected?"Continue"' in hw,
    'hardware detected subtitle empty':'v.instructionLine1=detected?""' in hw,
    'hardware duplicate action removed':'v.instructionLine2=detected?""' in hw,
    'hardware SoC VMAX label':'setValue(1,"SoC Max Voltage"' in hw,
    'hardware SoC VMAX config value':'std::to_string(rc.socVmaxMv)+" mV"' in hw,
    'RAM prep current baseline visible':'X : Use current values as baseline' in prep,
    'RAM prep current baseline input':'k&HidNpadButton_X' in handler and 'g.ramUseCurrentBaseline=1' in handler,
    'RAM current baseline persisted':'W(ramUseCurrentBaseline)' in main and 'R(ramUseCurrentBaseline)' in main,
    'RAM current baseline full snapshot':'g.ramBaseSocVmaxMv=rc.socVmaxMv' in handler and 'g.ramBaseT8=int(rc.timings[7])' in handler,
    'RAM guard supports current baseline':'g.ramUseCurrentBaseline?u32(g.ramBaseMaxMHz):3400U' in main,
    'recommended baseline still DVB8':'g.ramUseCurrentBaseline=0;g.ramHpMode=0' in handler and 'g.dvbGood=8;g.dvbCandidate=7' in handler,
    'beta24 benchmark flow retained':'Stage::RamBenchmark' in main and 'Final RAM Benchmark Sweep' in main,
    'beta22 force shortcuts retained':'HidNpadButton_Plus' in Path('source/stress_tests.cpp').read_text() and 'HidNpadButton_Minus' in Path('source/stress_tests.cpp').read_text(),
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad: raise SystemExit('Beta25 source audit failed: '+', '.join(bad))
