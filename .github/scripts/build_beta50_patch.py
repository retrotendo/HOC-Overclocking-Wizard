from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta50 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0: raise SystemExit(f"beta50 braced marker missing: {marker}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta50 opening brace missing: {marker}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta50 unbalanced: {marker}")
    return src[:pos]+replacement+src[end:]

# Version only; tuning, score and recommendation math stay unchanged.
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.49','APP_VERSION := 0.1.0-beta.50','version')
p.write_text(s)

# RAM target explanation: same content, compact enough to fit the full-width page.
p=Path('source/main_oc.cpp'); m=p.read_text()
new_explanation=r'''case Stage::RamTargetExplanation:{
            refreshRamSuggestedTarget();
            v.stageTitle="Choosing Your RAM Target";
            v.fullWidthLayout=true;
            v.hideValuesCard=true;
            v.instructionTitle="";v.instructionLine1="";v.instructionLine2="";
            gui::begin(v);
            print(1,"The Wizard found two recommended RAM targets:");
            print(3,"Efficiency: "+std::to_string(g.ramEfficiencyRecommendedMHz)+" MHz");
            print(4,"Best balance of RAM performance and voltage. Allows lower VDD2/VDDQ in the next steps.");
            print(6,"Performance: "+std::to_string(g.ramRecommendedMHz)+" MHz");
            print(7,"Stays near Stable Max while avoiding steps that need much more voltage for only negligible additional performance.");
            print(9,"Your choice becomes this profile's maximum RAM clock.");
            print(10,"Next, VDD2 and VDDQ are tuned specifically for that target.");
            print(12,"After voltage tuning, do not use RAM clocks above the selected target; the optimized voltages may make them unstable.");
            print(13,"To use a higher RAM clock later, retune VDD2/VDDQ for that higher target.");
            print(15,"A : Continue to RAM Target Selection");
            print(16,"X : Back to graph");
            print(17,"B : Exit");
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamTargetExplanation:',new_explanation)
p.write_text(m)

# Presentation-only audit.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta50 version':'0.1.0-beta.50' in Path('Makefile').read_text(),
    'full width explanation':'case Stage::RamTargetExplanation' in main and 'v.fullWidthLayout=true' in main,
    'task box removed':'v.instructionTitle=""' in main,
    'efficiency concise':'Best balance of RAM performance and voltage' in main,
    'performance concise':'only negligible additional performance' in main,
    'profile maximum':'Your choice becomes this profile\'s maximum RAM clock' in main,
    'target voltage tuning':'VDD2 and VDDQ are tuned specifically for that target' in main,
    'higher clocks warning':'do not use RAM clocks above the selected target' in main,
    'retune warning':'retune VDD2/VDDQ for that higher target' in main,
    'no overflow placeholder':'More details continue in this step' not in main,
    'score retained':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'graph beta49 retained':'gh=190' in gui and 'Recommended for:' in gui,
    'raw composite retained':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta50 source audit failed: '+', '.join(bad))
