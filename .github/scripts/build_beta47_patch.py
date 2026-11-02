from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta47 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta47 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta47 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta47 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.46','APP_VERSION := 0.1.0-beta.47','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# USER-FACING RAM SCORE ONLY.
# Replace beta46's arbitrary min->1000 / max->2000 presentation with a score
# derived directly from the persisted Membench measurements:
#
# bandwidth = geometric mean(CPU Read, CPU Copy, GPU Read, GPU Copy)
# raw score = bandwidth / Full-RAM latency
# RAM Score = 1000 * raw / baseline_raw
#
# Baseline is the lowest-frequency valid measured RAM point in this sweep.
# The internal 8-metric composite p.performance is NOT changed and still drives
# Efficiency/Performance recommendations exactly as in beta43.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()

score_fn=r'''double ramDisplayScore(int mhz){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return 1000.0;

    auto rawScore=[](const oc::SweepPoint& p)->double{
        if(p.ramCpuReadMBs<=0.0 || p.ramCpuCopyMBs<=0.0 ||
           p.ramGpuReadMBs<=0.0 || p.ramGpuCopyMBs<=0.0 ||
           p.latencyNs<=0.0) return 0.0;
        // Log-space geometric mean avoids large intermediate products and gives
        // CPU/GPU Read/Copy equal influence without mixing Write into the public score.
        const double logBw=(std::log(p.ramCpuReadMBs)+std::log(p.ramCpuCopyMBs)+
                            std::log(p.ramGpuReadMBs)+std::log(p.ramGpuCopyMBs))*0.25;
        const double bandwidth=std::exp(logBw);
        return bandwidth/p.latencyNs;
    };

    // Lowest-frequency valid raw point is the fixed reference for this tuning run.
    int baselineIdx=-1;
    for(int i:ids){
        if(rawScore(ramPoints[i])<=0.0) continue;
        if(baselineIdx<0 || ramPoints[i].requestedMHz<ramPoints[baselineIdx].requestedMHz)
            baselineIdx=i;
    }
    const int idx=ramPointIndexByMHz(mhz);
    if(baselineIdx<0 || idx<0) return 1000.0;
    const double base=rawScore(ramPoints[baselineIdx]);
    const double raw=rawScore(ramPoints[idx]);
    if(base<=1e-12 || raw<=0.0) return 1000.0;
    return std::max(0.0,1000.0*raw/base);
}'''
m=replace_function(m,'double ramDisplayScore(int mhz)',score_fn)
p.write_text(m)

# -----------------------------------------------------------------------------
# Point-navigation control: replace beta44's four tiny circles with a larger,
# separated Switch-like four-pad cluster. Top/Bottom are deliberately blank and
# muted; only Left/Right are blue and contain minimalist chevrons.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()
old_cluster='''            // Compact Switch-like directional legend in place of the redundant
            // "RAM performance and SoC voltage" title. Only Left/Right are active.
            const int dcx=gx+38, dcy=y+114, dr=13;
            fillCircle(dcx,dcy-17,dr,C_BORDER); fillCircle(dcx,dcy-17,dr-2,C_PANEL_2);
            fillCircle(dcx,dcy+17,dr,C_BORDER); fillCircle(dcx,dcy+17,dr-2,C_PANEL_2);
            fillCircle(dcx-17,dcy,dr,C_BLUE);   fillCircle(dcx-17,dcy,dr-2,C_PANEL_2);
            fillCircle(dcx+17,dcy,dr,C_BLUE);   fillCircle(dcx+17,dcy,dr-2,C_PANEL_2);
            drawText(dcx-22,dcy-10,16,C_TEXT,"<");
            drawText(dcx+12,dcy-10,16,C_TEXT,">");
            drawText(dcx+42,dcy-9,14,C_TEXT,"Inspect points");'''
new_cluster='''            // Switch-like four-pad inspection control. The larger separated pads
            // mirror the physical four-button cluster without drawing a bulky D-pad.
            // Only Left/Right are active; Up/Down remain blank and muted.
            const int dcx=gx+46, dcy=y+116;
            const int sideW=34, sideH=26, vertW=26, vertH=34;
            const int lx=dcx-48, ly=dcy-sideH/2;
            const int rx=dcx+14, ry=ly;
            const int tx=dcx-vertW/2, ty=dcy-46;
            const int bx=tx, by=dcy+12;
            roundedBorder(tx,ty,vertW,vertH,11,C_BORDER,C_PANEL_2,1);
            roundedBorder(bx,by,vertW,vertH,11,C_BORDER,C_PANEL_2,1);
            roundedBorder(lx,ly,sideW,sideH,11,C_BLUE,C_PANEL_2,2);
            roundedBorder(rx,ry,sideW,sideH,11,C_BLUE,C_PANEL_2,2);
            // Minimal outlined chevrons instead of text glyphs.
            drawLine(lx+20,ly+7,lx+11,ly+13,C_TEXT,2);
            drawLine(lx+11,ly+13,lx+20,ly+19,C_TEXT,2);
            drawLine(rx+14,ry+7,rx+23,ry+13,C_TEXT,2);
            drawLine(rx+23,ry+13,rx+14,ry+19,C_TEXT,2);
            drawText(dcx+60,dcy-9,14,C_TEXT,"Inspect points");'''
g=must_replace(g,old_cluster,new_cluster,'larger Switch-like four-pad cluster')
p.write_text(g)

# -----------------------------------------------------------------------------
# Deterministic mathematical sanity: the public score is proportional to
# bandwidth/latency and normalized only to the baseline, not to the best point.
# -----------------------------------------------------------------------------
import math

def raw(cpu_r,cpu_c,gpu_r,gpu_c,lat):
    return math.exp((math.log(cpu_r)+math.log(cpu_c)+math.log(gpu_r)+math.log(gpu_c))/4.0)/lat
base=raw(4985.8,4172.3,8226.9,6539.4,152.3)
assert base>0
assert abs(1000.0*base/base-1000.0)<1e-9
# Better bandwidth and lower latency must raise score naturally beyond 1000.
fast=raw(6000.0,5200.0,10000.0,8000.0,110.0)
assert 1000.0*fast/base>1000.0
print(f'PASS beta47 score sanity: baseline=1000 faster-example={1000.0*fast/base:.1f}')

# Audit: visible score changed; recommendation/raw composite logic is untouched.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta47 version':'0.1.0-beta.47' in Path('Makefile').read_text(),
    'benchmark score helper':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'score uses CPU read copy':'ramCpuReadMBs' in score_fn and 'ramCpuCopyMBs' in score_fn,
    'score uses GPU read copy':'ramGpuReadMBs' in score_fn and 'ramGpuCopyMBs' in score_fn,
    'score excludes public write':'ramCpuWriteMBs' not in score_fn and 'ramGpuWriteMBs' not in score_fn,
    'score excludes public L2':'ramL2LatencyNs' not in score_fn,
    'baseline lowest measured':'requestedMHz<ramPoints[baselineIdx].requestedMHz' in main,
    'no forced 2000 max':'2000.0' not in score_fn,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'raw composite gpu 35':'0.35*std::log(gpuGroup)' in eng,
    'raw composite cpu 35':'0.35*std::log(cpuGroup)' in eng,
    'raw composite ram latency 25':'0.25*std::log(ramLat)' in eng,
    'raw composite l2 5':'0.05*std::log(l2Lat)' in eng,
    'larger four-pad control':'const int sideW=34, sideH=26, vertW=26, vertH=34' in gui,
    'blank top bottom':'roundedBorder(tx,ty' in gui and 'roundedBorder(bx,by' in gui,
    'active side pads':'roundedBorder(lx,ly' in gui and 'roundedBorder(rx,ry' in gui,
    'chevrons are lines':'drawLine(lx+20' in gui and 'drawLine(rx+14' in gui,
    'inspection text retained':'Inspect points' in gui,
    'expanded recommendations retained':'Recommended for: Efficiency ' in gui,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'beta41 recovery retained':'NO - retry ' in main and 'YES - mark ' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta47 source audit failed: '+', '.join(bad))
