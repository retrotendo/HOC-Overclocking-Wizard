from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta21 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile'); s=p.read_text(); s=must_replace(s,'APP_VERSION := 0.1.0-beta.20','APP_VERSION := 0.1.0-beta.21','version'); p.write_text(s)

# RAM sweep result + temporary override cleanup + simpler user-facing copy.
p=Path('source/main_oc.cpp'); s=p.read_text()
s=must_replace(s,'    RamSweep,\n    RamGraph,','    RamSweep,\n    RamSweepResult,\n    RamGraph,','RAM sweep result stage')
s=must_replace(s,'    int ramStableMaxMHz = 0;\n','    int ramStableMaxMHz = 0;\n    int ramFailedMHz = 0;\n','RAM failed MHz state')
s=must_replace(s,'W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz);','W(ramSearchIndex); W(ramSearchEndIndex); W(ramRecommendedMHz); W(ramStableMaxMHz); W(ramFailedMHz);','save RAM failed MHz')
s=must_replace(s,'R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz)','R(ramSearchIndex) R(ramSearchEndIndex) R(ramRecommendedMHz) R(ramStableMaxMHz) R(ramFailedMHz)','load RAM failed MHz')

s=must_replace(s,
'void finishRamSweep(){analyzeRam();if(g.ramRecommendedMHz<=0){modalError("No stable RAM point was measured.");return;}g.stage=Stage::RamGraph;saveState();}',
'''void finishRamSweep(bool showFailureResult=false){
    clearOverrides();
    analyzeRam();
    if(g.ramRecommendedMHz<=0){modalError("No stable RAM point was measured.");return;}
    g.stage=showFailureResult?Stage::RamSweepResult:Stage::RamGraph;
    saveState();
}''','finish RAM sweep')

old='''void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){finishRamSweep();return;}
    if(!runStress(stress::Kind::Ram,60,"RAM Clock Stability","RAM "+std::to_string(freq)+" MHz")){finishRamSweep();return;}
    auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");if(!b.ok){finishRamSweep();return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB8";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
new='''void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        clearOverrides();g.ramFailedMHz=freq;finishRamSweep(true);return;
    }
    if(!runStress(stress::Kind::Ram,60,"RAM Clock Stability","RAM "+std::to_string(freq)+" MHz")){
        clearOverrides();g.ramFailedMHz=freq;finishRamSweep(true);return;
    }
    auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");
    if(!b.ok){clearOverrides();g.ramFailedMHz=freq;finishRamSweep(true);return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB8";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    clearOverrides();
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
s=must_replace(s,old,new,'RAM candidate cleanup/result')

old='case Stage::RamGraph:case Stage::RamFinalGraph:{v.stageTitle=g.stage==Stage::RamGraph?"RAM Capability Result":"RAM Final Result";'
new='''case Stage::RamSweepResult:{v.stageTitle="RAM Sweep Result";v.instructionTitle="Review the result";v.instructionLine1="";v.instructionLine2="";gui::begin(v);print(2,"Errors detected at "+std::to_string(g.ramFailedMHz)+" MHz");print(4,"Last stable: "+std::to_string(g.ramStableMaxMHz)+" MHz");print(5,"Max clock candidate for now: "+std::to_string(g.ramStableMaxMHz)+" MHz");print(7,"Temporary Overrides cleared");print(10,"A : Continue");print(11,"B : Exit");gui::present();break;}
        case Stage::RamGraph:case Stage::RamFinalGraph:{v.stageTitle=g.stage==Stage::RamGraph?"RAM Capability Result":"RAM Final Result";'''
s=must_replace(s,old,new,'RAM sweep result renderer')

old='case Stage::RamDvb:{v.stageTitle="RAM DVB Optimization";v.instructionTitle=g.dvbApplied?"Test the DVB candidate":"Apply the next DVB candidate";v.instructionLine1="Only DVB changes; first fail restores the previous value.";v.instructionLine2="A  Continue";gui::begin(v);print(3,"Last good DVB: "+std::to_string(g.dvbGood));print(4,"Candidate DVB: "+std::to_string(g.dvbCandidate));'
new='case Stage::RamDvb:{v.stageTitle="RAM DVB Optimization";v.instructionTitle=g.dvbApplied?"Test DVB Shift "+std::to_string(g.dvbCandidate):"Continue to apply DVB Shift "+std::to_string(g.dvbCandidate)+" and reboot";v.instructionLine1="";v.instructionLine2="";gui::begin(v);print(3,"Last good DVB: "+std::to_string(g.dvbGood));print(4,"Next DVB candidate to test: "+std::to_string(g.dvbCandidate));'
s=must_replace(s,old,new,'DVB user copy')

old='if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamCandidate();redraw=true;continue;}if(k&HidNpadButton_X){finishRamSweep();redraw=true;continue;}}\n        if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A))'
new='if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamCandidate();redraw=true;continue;}if(k&HidNpadButton_X){g.ramFailedMHz=(g.ramSearchIndex>=0)?int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]):0;clearOverrides();finishRamSweep(true);redraw=true;continue;}}\n        if(g.stage==Stage::RamSweepResult&&(k&HidNpadButton_A)){g.stage=Stage::RamGraph;saveState();redraw=true;continue;}\n        if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A))'
s=must_replace(s,old,new,'RAM sweep result input')

# Remove developer-facing explanatory lines from the main tuning screens. Keep only actionable context.
replacements={
'The table range is guidance, not a hard device limit; search may continue to the HOC safe ceiling.':'RAM clocks are tested upward until the first failure.',
'The maximum clock was found with HP disabled so HP cannot hide the frequency limit.':'Test HP Mode at the selected RAM clock.',
'ST starts with extra DVB reserve. DVB is optimized separately afterward.':'Apply Super Tight timings and validate them.',
'Base RAM is used here so a high-RAM DVFS floor cannot hide the intrinsic GPU curve.':'Test the selected GPU clock and voltage.',
'A High UV level is accepted only if all retained High CPU points pass with final RAM.':'Validate the selected High UV level.',
'Low UV is not judged from one idle/low clock. Both ends of the Low curve must work.':'Validate the selected Low UV level.',
'A lower Real Clock means the cap is too low; that is not a successful undervolt.':'Requested and Real CPU clock must match.'
}
for a,b in replacements.items():
    s=s.replace(a,b)
p.write_text(s)

# Right YOUR TASK card: instruction only, never duplicate action buttons.
p=Path('source/gui_console.cpp'); g=p.read_text()
# Current renderer shows instructionLine2 as a button-like action row. Blank that source text globally.
g=g.replace('view.instructionLine2', 'std::string{}', 1) if 'view.instructionLine2' in g else g
p.write_text(g)

# Audit
m=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); make=Path('Makefile').read_text()
checks={
 'version':'0.1.0-beta.21' in make,
 'result stage':'RamSweepResult' in m,
 'failure result':'Errors detected at ' in m and 'Max clock candidate for now' in m,
 'override cleanup':'clearOverrides();g.ramFailedMHz=freq' in m and 'clearOverrides();\n    if(g.ramSearchIndex' in m,
 'DVB wording':'Next DVB candidate to test:' in m and 'Continue to apply DVB Shift ' in m,
 'developer DVB text removed':'DVB is optimized before HP' not in m,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta21 source audit failed: '+', '.join(bad))
