from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta55 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0:
        raise SystemExit(f"beta55 braced marker missing: {marker}")
    brace=src.find('{',pos)
    if brace<0:
        raise SystemExit(f"beta55 opening brace missing: {marker}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None:
        raise SystemExit(f"beta55 unbalanced marker: {marker}")
    return src[:pos]+replacement+src[end:]

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.54','APP_VERSION := 0.1.0-beta.55','version')
p.write_text(s)

# Rebuild the two explanation pages using renderer indentation markers instead of spaces.
p=Path('source/main_oc.cpp'); m=p.read_text()
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
                print(4,"@INDENT@Best balance between RAM performance and voltage. Choosing this target can allow lower VDD2 and VDDQ in the next steps.");
                print(7,"PERFORMANCE - "+std::to_string(g.ramRecommendedMHz)+" MHz");
                print(8,"@INDENT@A higher RAM target focused on performance. It stays close to the highest stable RAM clock while avoiding steps where voltage rises disproportionately for only negligible additional performance.");
                print(15,"A : Next page");
                print(16,"X : Back to graph");
                print(17,"B : Exit");
            }else{
                v.stageTitle="Choosing Your RAM Target (2/2)";
                gui::begin(v);
                print(1,"YOUR SELECTED TARGET");
                print(2,"@INDENT@Your choice sets the maximum RAM clock for this profile.");
                print(5,"NEXT STEPS");
                print(6,"@INDENT@VDD2 and VDDQ will be tuned specifically for the target you choose.");
                print(9,"IMPORTANT");
                print(10,"@INDENT@After VDD2/VDDQ tuning, RAM clocks above your selected target should no longer be used. Optimized voltages may make higher RAM clocks unstable.");
                print(13,"@INDENT@To use a higher RAM clock later, VDD2/VDDQ must be tuned again for that higher target.");
                print(15,"A : Continue to RAM Target Selection");
                print(16,"X : Previous page");
                print(17,"B : Exit");
            }
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamTargetExplanation:',new_explanation)
p.write_text(m)

# Teach the graphical renderer a real indentation marker. Leading spaces are trimmed by design,
# so indentation must be an actual x-coordinate change rather than string whitespace.
p=Path('source/gui_console.cpp'); g=p.read_text()
old_heading='''            const bool heading = raw == "Objective:" || raw == "Test:" || raw == "Keys:" ||\n                                 raw == "Required test clocks:" || raw == "Current Temporary Overrides:" ||\n                                 raw == "Final values:" || raw == "Temporary Overrides:";'''
new_heading='''            const bool heading = raw == "Objective:" || raw == "Test:" || raw == "Keys:" ||\n                                 raw == "Required test clocks:" || raw == "Current Temporary Overrides:" ||\n                                 raw == "Final values:" || raw == "Temporary Overrides:" ||\n                                 startsWith(raw, "EFFICIENCY - ") || startsWith(raw, "PERFORMANCE - ") ||\n                                 raw == "YOUR SELECTED TARGET" || raw == "NEXT STEPS" || raw == "IMPORTANT";'''
g=must_replace(g,old_heading,new_heading,'explanation block headings')
marker='''            const bool numberedRow = raw.size() >= 3 && std::isdigit(static_cast<unsigned char>(raw[0])) &&\n                                     raw[1] == '.' && raw[2] == ' ';'''
replacement='''            if (startsWith(raw, "@INDENT@")) {\n                const std::string indented = trim(raw.substr(8));\n                by = drawWrappedText(x + 68, by, 17, C_TEXT, indented, w - 110, 25, 5);\n                by += 8;\n                ++shown;\n                continue;\n            }\n\n            const bool numberedRow = raw.size() >= 3 && std::isdigit(static_cast<unsigned char>(raw[0])) &&\n                                     raw[1] == '.' && raw[2] == ' ';'''
g=must_replace(g,marker,replacement,'real indent rendering')
p.write_text(g)

# Audit presentation and preserve tuning logic.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta55 version':'0.1.0-beta.55' in Path('Makefile').read_text(),
    'page 1':'Choosing Your RAM Target (1/2)' in main,
    'page 2':'Choosing Your RAM Target (2/2)' in main,
    'real indent markers':main.count('@INDENT@') >= 6,
    'renderer strips marker':'raw.substr(8)' in gui,
    'renderer x offset':'drawWrappedText(x + 68' in gui,
    'eff heading colored':'startsWith(raw, "EFFICIENCY - ")' in gui,
    'perf heading colored':'startsWith(raw, "PERFORMANCE - ")' in gui,
    'page2 headings colored':'raw == "YOUR SELECTED TARGET"' in gui and 'raw == "NEXT STEPS"' in gui and 'raw == "IMPORTANT"' in gui,
    'negligible wording':'only negligible additional performance' in main,
    'warning retained':'RAM clocks above your selected target should no longer be used' in main,
    'retune retained':'VDD2/VDDQ must be tuned again for that higher target' in main,
    'task retained':'Use the Left / Right buttons' in main and 'to inspect a stable RAM point.' in main,
    'score formula retained':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'raw composite retained':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta55 source audit failed: '+', '.join(bad))
