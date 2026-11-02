from pathlib import Path
import re


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta53 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0:
        raise SystemExit(f"beta53 braced marker missing: {marker}")
    brace=src.find('{',pos)
    if brace<0:
        raise SystemExit(f"beta53 opening brace missing: {marker}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None:
        raise SystemExit(f"beta53 unbalanced marker: {marker}")
    return src[:pos]+replacement+src[end:]


def find_case_block(src, needle):
    pos=src.find(needle)
    if pos<0:
        raise SystemExit(f"beta53 target marker missing: {needle}")
    start=src.rfind('case Stage::',0,pos)
    brace=src.find('{',start)
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if start<0 or brace<0 or end is None:
        raise SystemExit('beta53 target block parse failed')
    return start,end,src[start:end]

# Version only. No tuning, score or recommendation math changes.
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.52','APP_VERSION := 0.1.0-beta.53','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()

# UI-only page state. It does not need persistence; reopening the app simply starts on page 1.
m=must_replace(m,'State g;\n','State g;\nint g_ramTargetExplanationPage = 0;\n','explanation page state')

# Full two-page explanation. Text is manually line-broken so nothing relies on wrapping.
new_explanation=r'''case Stage::RamTargetExplanation:{
            refreshRamSuggestedTarget();
            v.fullWidthLayout=true;
            v.hideValuesCard=true;
            v.instructionTitle="";v.instructionLine1="";v.instructionLine2="";
            if(g_ramTargetExplanationPage==0){
                v.stageTitle="Choosing Your RAM Target (1/2)";
                gui::begin(v);
                print(1,"The Wizard found two recommended RAM targets:");
                print(3,"Efficiency - "+std::to_string(g.ramEfficiencyRecommendedMHz)+" MHz");
                print(4,"Best balance between RAM performance and voltage.");
                print(5,"Choosing this target can allow lower VDD2 and VDDQ");
                print(6,"in the next steps.");
                print(8,"Performance - "+std::to_string(g.ramRecommendedMHz)+" MHz");
                print(9,"A higher RAM target focused on performance.");
                print(10,"It stays close to the highest stable RAM clock while avoiding");
                print(11,"steps where voltage rises too much for the additional");
                print(12,"measured gain.");
                print(15,"A : Next page");
                print(16,"X : Back to graph");
                print(17,"B : Exit");
            }else{
                v.stageTitle="Choosing Your RAM Target (2/2)";
                gui::begin(v);
                print(1,"Your choice sets the maximum RAM clock for this profile.");
                print(3,"In the next steps, VDD2 and VDDQ will be tuned specifically");
                print(4,"for the target you choose.");
                print(6,"Important:");
                print(7,"After VDD2/VDDQ tuning, RAM clocks above your selected target");
                print(8,"should no longer be used.");
                print(10,"The voltages will be optimized for your chosen maximum,");
                print(11,"so higher clocks may no longer be stable.");
                print(13,"To use a higher RAM clock later, VDD2/VDDQ must be tuned again");
                print(14,"for that higher target.");
                print(15,"A : Continue to RAM Target Selection");
                print(16,"X : Previous page");
                print(17,"B : Exit");
            }
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamTargetExplanation:',new_explanation)

# A pages forward; X pages backward, then returns to the graph.
new_input=r'''if(g.stage==Stage::RamTargetExplanation){
            if(k&HidNpadButton_X){
                if(g_ramTargetExplanationPage>0){g_ramTargetExplanationPage=0;redraw=true;continue;}
                g.stage=Stage::RamGraph;saveState();redraw=true;continue;
            }
            if(k&HidNpadButton_A){
                if(g_ramTargetExplanationPage==0){g_ramTargetExplanationPage=1;redraw=true;continue;}
                g.stage=Stage::RamTargetSelect;g.ramTargetMHz=g.ramRecommendedMHz;saveState();redraw=true;continue;
            }
        }'''
m=replace_braced(m,'if(g.stage==Stage::RamTargetExplanation){',new_input)

# Keep the RAM target task box short enough to fit without any automatic wrapping.
start,end,target=find_case_block(m,'Choose RAM Target')
target=re.sub(r'v\.instructionLine1\s*=\s*"[^"]*"\s*;','v.instructionLine1="Use the Left / Right buttons";',target,count=1)
target=re.sub(r'v\.instructionLine2\s*=\s*"[^"]*"\s*;','v.instructionLine2="to inspect a stable RAM point.";',target,count=1)
m=m[:start]+target+m[end:]

p.write_text(m)

# Presentation-only audit.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
_,_,target=find_case_block(main,'Choose RAM Target')
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta53 version':'0.1.0-beta.53' in Path('Makefile').read_text(),
    'page state':'g_ramTargetExplanationPage = 0' in main,
    'page 1 title':'Choosing Your RAM Target (1/2)' in main,
    'page 2 title':'Choosing Your RAM Target (2/2)' in main,
    'page 1 full efficiency text':'Choosing this target can allow lower VDD2 and VDDQ' in main,
    'page 1 full performance text':'steps where voltage rises too much for the additional' in main and 'measured gain.' in main,
    'page 2 profile maximum':'Your choice sets the maximum RAM clock for this profile.' in main,
    'page 2 target tuning':'VDD2 and VDDQ will be tuned specifically' in main,
    'page 2 higher clock warning':'RAM clocks above your selected target' in main and 'should no longer be used.' in main,
    'page 2 stability warning':'so higher clocks may no longer be stable.' in main,
    'page 2 retune':'VDD2/VDDQ must be tuned again' in main,
    'A paging':'A : Next page' in main and 'A : Continue to RAM Target Selection' in main,
    'X paging':'X : Previous page' in main and 'X : Back to graph' in main,
    'task title':'v.instructionTitle="Choose your RAM target"' in target,
    'task short line 1':'v.instructionLine1="Use the Left / Right buttons"' in target,
    'task short line 2':'v.instructionLine2="to inspect a stable RAM point."' in target,
    'efficiency row still removed':not any(('print(' in ln or 'drawText(' in ln) and ('"Efficiency"' in ln or 'ramEfficiencyRecommendedMHz' in ln) for ln in target.splitlines()),
    'back action retained':'Back to explanation and graph' in target,
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
if bad: raise SystemExit('Beta53 source audit failed: '+', '.join(bad))
