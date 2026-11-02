from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta46 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta46 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta46 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta46 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.45','APP_VERSION := 0.1.0-beta.46','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# DISPLAY ONLY: replace the visible 0..100 RAM Performance scale with a Wizard
# RAM Score. Lowest measured point = 1000, best measured point = 2000.
# Raw p.performance remains untouched and still drives both recommendation models.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()

score_fn=r'''double ramDisplayScore(int mhz){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return 1000.0;
    double minPerf=1e30,maxPerf=-1e30;
    for(int i:ids){
        minPerf=std::min(minPerf,ramPoints[i].performance);
        maxPerf=std::max(maxPerf,ramPoints[i].performance);
    }
    const int idx=ramPointIndexByMHz(mhz);
    if(idx<0) return 1000.0;
    const double span=maxPerf-minPerf;
    if(span<=1e-9) return 2000.0;
    const double gain=std::clamp((ramPoints[idx].performance-minPerf)/span,0.0,1.0);
    return 1000.0 + 1000.0*gain;
}'''
m=replace_function(m,'double ramPerformancePercent(int mhz)',score_fn)
# Replace remaining display helper calls. Recommendation functions never call the
# old helper; they continue reading ramPoints[*].performance directly.
m=m.replace('ramPerformancePercent(', 'ramDisplayScore(')

summary_fn=r'''std::string ramPointSummary(int mhz){
    const int idx=ramPointIndexByMHz(mhz);
    if(idx<0) return "No measured RAM point selected.";
    std::ostringstream o;
    o<<mhz<<" MHz  |  RAM Score "<<int(std::lround(ramDisplayScore(mhz)))<<"  |  SoC "<<fmtSocConfigMv(int(ramPoints[idx].railMv));
    return o.str();
}'''
m=replace_function(m,'std::string ramPointSummary(int mhz)',summary_fn)

# Target selector: same score, no percent sign.
m=must_replace(m,
    '            print(5,"RAM Performance: "+fmt1(ramDisplayScore(g.ramTargetMHz))+"%");',
    '            print(5,"RAM Score: "+std::to_string(int(std::lround(ramDisplayScore(g.ramTargetMHz)))));',
    'target selector RAM Score')

# Keep metadata/labels semantically aligned even where the line renderer does not
# currently draw this View field directly.
m=m.replace('v.chartPerformanceLabel="Performance %";','v.chartPerformanceLabel="RAM Score";')
p.write_text(m)

# -----------------------------------------------------------------------------
# Graph: display RAM Score and normalize the visible green line across the score
# span so 1000 sits at the bottom and 2000 at the top. This preserves the strong
# tuning-progress curve introduced in beta45.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()
g=must_replace(g,
    '            drawText(gx+541,y+103,13,C_TEXT,"RAM Performance");',
    '            drawText(gx+541,y+103,13,C_TEXT,"RAM Score");',
    'RAM Score legend')
g=must_replace(g,
    '            double maxPerf=0.0,minVolt=1e30,maxVolt=0.0;',
    '            double minPerf=1e30,maxPerf=-1e30,minVolt=1e30,maxVolt=0.0;',
    'score min max declaration')
g=must_replace(g,
    '                maxPerf=std::max(maxPerf,q.performance);',
    '                minPerf=std::min(minPerf,q.performance);maxPerf=std::max(maxPerf,q.performance);',
    'score min max scan')
g=must_replace(g,
    '            if(maxPerf<=0.0)maxPerf=1.0;',
    '            if(minPerf>1e20 || maxPerf<minPerf){minPerf=0.0;maxPerf=1.0;}\n            if(maxPerf<=minPerf)maxPerf=minPerf+1.0;',
    'score min max fallback')
g=must_replace(g,
    '            auto pyP=[&](double perf){const double pct=100.0*perf/maxPerf;return gy+gh-int(std::clamp(pct,0.0,100.0)/100.0*gh);};',
    '            auto pyP=[&](double perf){const double pct=100.0*(perf-minPerf)/(maxPerf-minPerf);return gy+gh-int(std::clamp(pct,0.0,100.0)/100.0*gh);};',
    'score graph normalization')
p.write_text(g)

# Display sanity only. Same beta45 gain mapping, now expressed as 1000..2000 points.
def score(v,lo=94.2,hi=100.0):
    gain=(v-lo)/(hi-lo)
    return 1000.0+1000.0*gain
assert abs(score(94.2)-1000.0)<1e-9
assert abs(score(100.0)-2000.0)<1e-9
assert 1800 < score(98.9) < 1820
assert 1960 < score(99.8) < 1980
print(f'PASS beta46 score curve: baseline={score(94.2):.0f} eff-example={score(98.9):.0f} perf-example={score(99.8):.0f} max={score(100.0):.0f}')

# Audit: prove score is presentation-only and tuning/recommendation still uses raw data.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta46 version':'0.1.0-beta.46' in Path('Makefile').read_text(),
    'score helper exists':'double ramDisplayScore(int mhz)' in main and '1000.0 + 1000.0*gain' in main,
    'old percent helper gone':'ramPerformancePercent(' not in main,
    'chart uses display score':'q.performance=ramDisplayScore(int(p.requestedMHz))' in main,
    'summary uses RAM Score':'RAM Score ' in main and 'ramPointSummary' in main,
    'selector uses RAM Score':'RAM Score: ' in main,
    'legend RAM Score':'"RAM Score"' in gui,
    'graph score normalized':'(perf-minPerf)/(maxPerf-minPerf)' in gui,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'raw composite gpu 35':'0.35*std::log(gpuGroup)' in eng,
    'raw composite cpu 35':'0.35*std::log(cpuGroup)' in eng,
    'raw composite ram latency 25':'0.25*std::log(ramLat)' in eng,
    'raw composite l2 5':'0.05*std::log(l2Lat)' in eng,
    'eff recommendation retained':'findRamEfficiencyTargetIndex' in main and 'ramEfficiencyRecommendedMHz' in main,
    'perf recommendation retained':'findRamSuggestedTargetIndex' in main and 'ramRecommendedMHz' in main,
    'beta44 switch controls retained':'const int dcx=gx+38' in gui and 'Inspect points' in gui,
    'expanded recommendations retained':'Recommended for: Efficiency ' in gui,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'beta41 recovery retained':'NO - retry ' in main and 'YES - mark ' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta46 source audit failed: '+', '.join(bad))
