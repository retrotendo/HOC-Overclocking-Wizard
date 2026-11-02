from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta52 marker missing: {name}")
    return s.replace(old, new, count)


def find_case_block(src, needle):
    pos=src.find(needle)
    if pos<0:
        raise SystemExit(f"beta52 target marker missing: {needle}")
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
        raise SystemExit('beta52 target block parse failed')
    return src[start:end]

p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.51','APP_VERSION := 0.1.0-beta.52','version')
p.write_text(s)

main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
target=find_case_block(main,'Choose RAM Target')
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta52 version':'0.1.0-beta.52' in Path('Makefile').read_text(),
    'task title':'v.instructionTitle="Choose your RAM target"' in target,
    'task left right buttons':'Use the Left / Right buttons to inspect and' in target and 'select another measured stable RAM point.' in target,
    'old content hint gone':'Use Left / Right to inspect' not in target,
    'efficiency content row gone':not any(('print(' in ln or 'drawText(' in ln) and ('"Efficiency"' in ln or 'ramEfficiencyRecommendedMHz' in ln) for ln in target.splitlines()),
    'back action':'Back to explanation and graph' in target,
    'selected target':'Selected Target' in target,
    'RAM score':'RAM Score' in target,
    'SoC':'SoC' in target,
    'beta50 explanation':'only negligible additional performance' in main and 'retune VDD2/VDDQ for that higher target' in main,
    'score formula':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'graph retained':'gh=190' in gui and 'Recommended for:' in gui,
    'raw composite':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta52 source audit failed: '+', '.join(bad))
