from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta45 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta45 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta45 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta45 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.44','APP_VERSION := 0.1.0-beta.45','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# DISPLAY ONLY: map the measured composite index to visible RAM Performance.
# The lowest measured RAM point is 0%, the best measured point is 100%.
# The raw p.performance values remain untouched and continue to drive both
# Efficiency and Performance recommendation algorithms.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()

display_fn=r'''double ramPerformancePercent(int mhz){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return 0.0;
    double minPerf=1e30,maxPerf=-1e30;
    for(int i:ids){
        minPerf=std::min(minPerf,ramPoints[i].performance);
        maxPerf=std::max(maxPerf,ramPoints[i].performance);
    }
    const int idx=ramPointIndexByMHz(mhz);
    if(idx<0) return 0.0;
    const double span=maxPerf-minPerf;
    if(span<=1e-9) return 100.0;
    return std::clamp(100.0*(ramPoints[idx].performance-minPerf)/span,0.0,100.0);
}'''
m=replace_function(m,'double ramPerformancePercent(int mhz)',display_fn)

# The chart must plot the display-space RAM Performance, not the raw 94..100
# composite index. Recommendation code still reads ramPoints[*].performance.
m=must_replace(m,
    'q.x=p.requestedMHz;q.performance=p.performance;q.voltage=p.railMv;',
    'q.x=p.requestedMHz;q.performance=ramPerformancePercent(int(p.requestedMHz));q.voltage=p.railMv;',
    'chart uses display RAM performance')

# Target-selection page is also user-facing: show the same display metric and do
# not imply that this is percent-of-Stable-Max raw benchmark throughput.
m=must_replace(m,
    '            print(5,"Benchmark Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"% of Stable Max");',
    '            print(5,"RAM Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"%");',
    'target selector RAM Performance label')

p.write_text(m)

# Graph legend: name the visible green series simply RAM Performance.
p=Path('source/gui_console.cpp'); g=p.read_text()
g=must_replace(g,
    '            drawText(gx+541,y+103,13,C_TEXT,"Performance %");',
    '            drawText(gx+541,y+103,13,C_TEXT,"RAM Performance");',
    'RAM Performance legend')
p.write_text(g)

# -----------------------------------------------------------------------------
# Deterministic display sanity. This is display test data only; runtime has no
# hardcoded frequency or score. With the current observed endpoints, 94.2 -> 0
# and 100 -> 100, while upper tuning points become visibly separated.
# -----------------------------------------------------------------------------
def disp(v,lo=94.2,hi=100.0):
    return 100.0*(v-lo)/(hi-lo)
assert abs(disp(94.2)-0.0)<1e-9
assert abs(disp(100.0)-100.0)<1e-9
assert 80.0 < disp(98.9) < 82.0
assert 96.0 < disp(99.8) < 98.0
print(f'PASS beta45 display curve: baseline={disp(94.2):.1f}% eff-example={disp(98.9):.1f}% perf-example={disp(99.8):.1f}% max={disp(100.0):.1f}%')

# Audit: prove this is presentation-only and the hidden raw benchmark/recommendation
# model remains intact.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta45 version':'0.1.0-beta.45' in Path('Makefile').read_text(),
    'display rebased min max':'minPerf=std::min' in main and 'maxPerf=std::max' in main and '(ramPoints[idx].performance-minPerf)/span' in main,
    'chart uses display performance':'q.performance=ramPerformancePercent(int(p.requestedMHz))' in main,
    'legend RAM Performance':'"RAM Performance"' in gui,
    'selector RAM Performance':'RAM Performance: ' in main and '% of Stable Max' not in main[main.find('case Stage::RamTargetSelect'):main.find('gui::present();break;}',main.find('case Stage::RamTargetSelect'))],
    'recommendation remains raw':'ramPerformancePercent' not in rec_region and '.performance' in rec_region,
    'raw composite gpu 35':'0.35*std::log(gpuGroup)' in eng,
    'raw composite cpu 35':'0.35*std::log(cpuGroup)' in eng,
    'raw composite ram latency 25':'0.25*std::log(ramLat)' in eng,
    'raw composite l2 5':'0.05*std::log(l2Lat)' in eng,
    'eff recommendation retained':'findRamEfficiencyTargetIndex' in main and 'ramEfficiencyRecommendedMHz' in main,
    'perf recommendation retained':'findRamSuggestedTargetIndex' in main and 'ramRecommendedMHz' in main,
    'beta44 switch legend retained':'const int dcx=gx+38' in gui and 'Inspect points' in gui,
    'expanded recommendations retained':'Recommended for: Efficiency ' in gui,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'beta41 recovery retained':'NO - retry ' in main and 'YES - mark ' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta45 source audit failed: '+', '.join(bad))
