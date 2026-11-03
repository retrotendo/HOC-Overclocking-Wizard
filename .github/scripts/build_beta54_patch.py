from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta54 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0:
        raise SystemExit(f"beta54 braced marker missing: {marker}")
    brace=src.find('{',pos)
    if brace<0:
        raise SystemExit(f"beta54 opening brace missing: {marker}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None:
        raise SystemExit(f"beta54 unbalanced marker: {marker}")
    return src[:pos]+replacement+src[end:]

p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.53','APP_VERSION := 0.1.0-beta.54','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()

# Presentation-only rewrite: same two-page explanation, now grouped visually.
# Headings stay left aligned; their explanatory text is deliberately indented.
new_explanation=r'''case Stage::RamTargetExplanation:{
            refreshRamSuggestedTarget();
            v.fullWidthLayout=true;
            v.hideValuesCard=true;
            v.instructionTitle="";v.instructionLine1="";v.instructionLine2="";
            if(g_ramTargetExplanationPage==0){
                v.stageTitle="Choosing Your RAM Target (1/2)";
                gui::begin(v);
                print(1,"The Wizard found two recommended RAM targets:");
                print(3,"EFFICIENCY - "+std::to_string(g.ramEfficiencyRecommendedMHz)+" MHz");
                print(4,"    Best balance between RAM performance and voltage.");
                print(5,"    Choosing this target can allow lower VDD2 and VDDQ");
                print(6,"    in the next steps.");
                print(8,"PERFORMANCE - "+std::to_string(g.ramRecommendedMHz)+" MHz");
                print(9,"    A higher RAM target focused on performance.");
                print(10,"    It stays close to the highest stable RAM clock while avoiding");
                print(11,"    steps where voltage rises too much for the additional");
                print(12,"    measured gain.");
                print(15,"A : Next page");
                print(16,"X : Back to graph");
                print(17,"B : Exit");
            }else{
                v.stageTitle="Choosing Your RAM Target (2/2)";
                gui::begin(v);
                print(1,"YOUR SELECTED TARGET");
                print(2,"    Your choice sets the maximum RAM clock for this profile.");
                print(4,"NEXT STEPS");
                print(5,"    In the next steps, VDD2 and VDDQ will be tuned specifically");
                print(6,"    for the target you choose.");
                print(8,"IMPORTANT");
                print(9,"    After VDD2/VDDQ tuning, RAM clocks above your selected target");
                print(10,"    should no longer be used.");
                print(12,"    Optimized voltages may make higher RAM clocks unstable.");
                print(13,"    To use a higher RAM clock later, VDD2/VDDQ must be tuned again");
                print(14,"    for that higher target.");
                print(15,"A : Continue to RAM Target Selection");
                print(16,"X : Previous page");
                print(17,"B : Exit");
            }
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamTargetExplanation:',new_explanation)
p.write_text(m)

# UI-only source audit. Tuning and recommendation algorithms must remain unchanged.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta54 version':'0.1.0-beta.54' in Path('Makefile').read_text(),
    'page 1 title':'Choosing Your RAM Target (1/2)' in main,
    'page 2 title':'Choosing Your RAM Target (2/2)' in main,
    'efficiency heading':'EFFICIENCY - ' in main,
    'efficiency indent':'    Best balance between RAM performance and voltage.' in main,
    'performance heading':'PERFORMANCE - ' in main,
    'performance indent':'    A higher RAM target focused on performance.' in main,
    'selected target heading':'YOUR SELECTED TARGET' in main,
    'next steps heading':'NEXT STEPS' in main,
    'important heading':'IMPORTANT' in main,
    'page 2 indent':'    Your choice sets the maximum RAM clock for this profile.' in main,
    'warning retained':'RAM clocks above your selected target' in main and 'should no longer be used.' in main,
    'retune retained':'VDD2/VDDQ must be tuned again' in main and 'for that higher target.' in main,
    'paging retained':'A : Next page' in main and 'A : Continue to RAM Target Selection' in main and 'X : Previous page' in main,
    'task retained':'Use the Left / Right buttons' in main and 'to inspect a stable RAM point.' in main,
    'score formula retained':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'graph retained':'gh=190' in gui and 'Recommended for:' in gui,
    'raw composite retained':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta54 source audit failed: '+', '.join(bad))
