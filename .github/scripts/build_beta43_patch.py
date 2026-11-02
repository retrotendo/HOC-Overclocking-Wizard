from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta43 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta43 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta43 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta43 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.42','APP_VERSION := 0.1.0-beta.43','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()

# -----------------------------------------------------------------------------
# Performance Recommendation: start at Stable Max and reject only clearly bad
# final steps. This is deliberately top-down: a lower electrical knee must not
# pull the performance-oriented recommendation down if later steps recover.
# -----------------------------------------------------------------------------
perf_fn=r'''int findRamSuggestedTargetIndex(){
    auto ids=measuredRamPointIndices();
    if(ids.empty()) return -1;
    std::sort(ids.begin(),ids.end(),[](int a,int b){return ramPoints[a].requestedMHz<ramPoints[b].requestedMHz;});
    if(ids.size()==1) return ids.front();

    auto median=[](std::vector<double> v)->double{
        if(v.empty()) return 0.0;
        std::sort(v.begin(),v.end());
        const size_t n=v.size();
        return (n&1)?v[n/2]:0.5*(v[n/2-1]+v[n/2]);
    };

    int pos=int(ids.size())-1;
    constexpr int LOOKBACK=4;
    while(pos>1){
        const auto& a=ramPoints[ids[pos-1]];
        const auto& b=ramPoints[ids[pos]];
        const double dMHz=double(b.requestedMHz)-double(a.requestedMHz);
        if(dMHz<=0.0) break;
        const double dV=std::max(0.0,double(b.railMv)-double(a.railMv));
        const double dPerf=std::max(0.0,b.performance-a.performance);
        const double costPer100=dV/dMHz*100.0;
        const double perfPer100=dPerf/dMHz*100.0;
        const double valuePerMv=dV>1e-9?dPerf/dV:1e9;

        std::vector<double> prevCost,prevPerfRate,prevValue;
        const int first=std::max(1,pos-LOOKBACK);
        for(int j=first;j<pos;++j){
            const auto& p0=ramPoints[ids[j-1]];
            const auto& p1=ramPoints[ids[j]];
            const double f=double(p1.requestedMHz)-double(p0.requestedMHz);
            if(f<=0.0) continue;
            const double v=std::max(0.0,double(p1.railMv)-double(p0.railMv));
            const double pg=std::max(0.0,p1.performance-p0.performance);
            prevPerfRate.push_back(pg/f*100.0);
            if(v>1e-9){prevCost.push_back(v/f*100.0);prevValue.push_back(pg/v);}
        }
        if(prevCost.size()<2 || prevPerfRate.size()<2 || prevValue.size()<2) break;
        const double medCost=median(prevCost);
        const double medPerf=median(prevPerfRate);
        const double medValue=median(prevValue);
        if(medCost<=1e-9) break;

        // A Performance rejection needs BOTH a genuinely steep electrical step
        // and poor measured return. The 50 mV/100 MHz floor is frequency-agnostic
        // and prevents ordinary 25/37.5 mV HOC table steps from being rejected.
        const bool expensiveStep=costPer100>=50.0 && costPer100>=medCost*1.45;
        const bool performanceNotExceptional=(medPerf<=1e-9) || (perfPer100<=medPerf*1.20);
        const bool poorCombinedReturn=(medValue<=1e-9) || (valuePerMv<=medValue*0.90);
        if(dV>=12.0 && expensiveStep && performanceNotExceptional && poorCombinedReturn){--pos;continue;}
        break;
    }
    return ids[pos];
}'''
m=replace_function(m,'int findRamSuggestedTargetIndex()',perf_fn)

# -----------------------------------------------------------------------------
# Efficiency Recommendation: scan UP through the upper useful region and stop
# before the FIRST clear electrical knee. A later cheap step does not erase that
# earlier efficiency boundary because choosing Efficiency intentionally caps the
# entire RAM profile before the costly region. Performance can still save a step
# when its gain is exceptional compared with local history.
# -----------------------------------------------------------------------------
eff_fn=r'''int findRamEfficiencyTargetIndex(){
    auto ids=measuredRamPointIndices();
    if(ids.empty()) return -1;
    std::sort(ids.begin(),ids.end(),[](int a,int b){return ramPoints[a].requestedMHz<ramPoints[b].requestedMHz;});
    if(ids.size()==1) return ids.front();

    auto median=[](std::vector<double> v)->double{
        if(v.empty()) return 0.0;
        std::sort(v.begin(),v.end());
        const size_t n=v.size();
        return (n&1)?v[n/2]:0.5*(v[n/2-1]+v[n/2]);
    };

    const auto& top=ramPoints[ids.back()];
    const double maxMHz=std::max(1.0,double(top.requestedMHz));
    const double maxPerf=std::max(1e-9,top.performance);
    int startPos=0;
    for(int p=0;p<int(ids.size());++p){
        const auto& q=ramPoints[ids[p]];
        if(double(q.requestedMHz)>=maxMHz*0.85 && q.performance>=maxPerf*0.98){startPos=p;break;}
    }

    constexpr int LOOKBACK=4;
    for(int pos=std::max(2,startPos+1);pos<int(ids.size());++pos){
        const auto& a=ramPoints[ids[pos-1]];
        const auto& b=ramPoints[ids[pos]];
        const double dMHz=double(b.requestedMHz)-double(a.requestedMHz);
        if(dMHz<=0.0) continue;
        const double dV=std::max(0.0,double(b.railMv)-double(a.railMv));
        const double dPerf=std::max(0.0,b.performance-a.performance);
        const double costPer100=dV/dMHz*100.0;
        const double perfPer100=dPerf/dMHz*100.0;

        std::vector<double> prevCost,prevPerfRate;
        const int first=std::max(1,pos-LOOKBACK);
        for(int j=first;j<pos;++j){
            const auto& p0=ramPoints[ids[j-1]];
            const auto& p1=ramPoints[ids[j]];
            const double f=double(p1.requestedMHz)-double(p0.requestedMHz);
            if(f<=0.0) continue;
            const double v=std::max(0.0,double(p1.railMv)-double(p0.railMv));
            const double pg=std::max(0.0,p1.performance-p0.performance);
            prevPerfRate.push_back(pg/f*100.0);
            if(v>1e-9) prevCost.push_back(v/f*100.0);
        }
        if(prevCost.size()<2 || prevPerfRate.size()<2) continue;
        const double medCost=median(prevCost);
        const double medPerf=median(prevPerfRate);
        if(medCost<=1e-9) continue;

        const bool expensiveStep=costPer100>=50.0 && costPer100>=medCost*1.45;
        const bool performanceNotExceptional=(medPerf<=1e-9) || (perfPer100<=medPerf*1.25);
        if(dV>=12.0 && expensiveStep && performanceNotExceptional)
            return ids[pos-1];
    }
    return findRamSuggestedTargetIndex();
}'''
m=replace_function(m,'int findRamEfficiencyTargetIndex()',eff_fn)

# -----------------------------------------------------------------------------
# Hidden developer access to RAM Debug. Normal users see no Debug action.
# ZL + ZR held, Plus pressed while on the RAM result graph opens RamDebug.
# B returns from RamDebug to exactly this graph. X benchmark rerun stays available
# inside the hidden page for future diagnostics.
# -----------------------------------------------------------------------------
graph_anchor='''if(g.stage==Stage::RamGraph){
            if(k&HidNpadButton_Left){moveRamTarget(-1);redraw=true;continue;}'''
graph_new='''if(g.stage==Stage::RamGraph){
            const u64 held=padGetButtons(&pad);
            const u64 debugChord=HidNpadButton_ZL | HidNpadButton_ZR;
            if((held&debugChord)==debugChord && (k&HidNpadButton_Plus)){g_ramDebugPage=0;g.stage=Stage::RamDebug;saveState();redraw=true;continue;}
            if(k&HidNpadButton_Left){moveRamTarget(-1);redraw=true;continue;}'''
m=must_replace(m,graph_anchor,graph_new,'hidden RAM debug chord')

# Debug back input: keep B only; there is deliberately no visible/normal graph entry.
start=m.find('if(g.stage==Stage::RamDebug){')
end=m.find('\n        if(g.stage==Stage::RamTargetExplanation)',start)
if start<0 or end<0: raise SystemExit('beta43 RAM debug input region missing')
region=m[start:end]
region=region.replace('if((k&HidNpadButton_Y)||(k&HidNpadButton_B)){','if(k&HidNpadButton_B){')
m=m[:start]+region+m[end:]
# Debug screen wording itself may have either raw-data-complete branch.
m=m.replace('Y / B : Back','B : Back to RAM graph')

p.write_text(m)

# -----------------------------------------------------------------------------
# Graph cleanup.
# - Recommendation values move to the far right of the selected-point detail row.
# - Stable Max stays represented by the MAX marker only.
# - A more visible Left/Right navigation affordance sits on the chart-title row.
# - Remove the standalone right-edge "MHz" axis label that collided with 3000.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()

# Remove beta42 recommendation strip above the plot.
old_strip='''            // Recommendation values stay visible independently of the selected
            // inspection point and independently of the bottom action buttons.
            const std::string recLine=
                "Efficiency " + std::to_string(g_view.chartEfficiencyMHz) + " MHz   |   Performance " +
                std::to_string(g_view.chartPerformanceMHz) + " MHz   |   Stable Max " +
                std::to_string(g_view.chartStableMaxMHz) + " MHz";
            drawText(gx,y+126,14,C_TEXT,fitText(recLine,14,gw));
'''
g=must_replace(g,old_strip,'','remove top recommendation strip')

# Replace beta42's muted text-only navigation hint with small Switch-like arrow buttons.
old_hint='''            drawTextRight(gx+gw,y+103,12,C_MUTED,"Left / Right: inspect points");'''
new_hint='''            const int navX=gx+gw-220, navY=y+97;
            roundedBorder(navX,navY,28,28,8,C_BLUE,C_PANEL_2,1);
            roundedBorder(navX+36,navY,28,28,8,C_BLUE,C_PANEL_2,1);
            drawText(navX+9,navY+3,17,C_TEXT,"<");
            drawText(navX+45,navY+3,17,C_TEXT,">");
            drawText(navX+75,navY+4,13,C_TEXT,"Inspect points");'''
g=must_replace(g,old_hint,new_hint,'prominent graph navigation')

# Standalone MHz text at the far right overlapped the 3000 label. The axis values
# already make their unit clear via the selected summary and RAM title, so remove it.
g=must_replace(g,'            drawTextRight(gx+gw,gy+gh+6,10,C_MUTED,"MHz");\n','', 'remove colliding MHz axis unit')

# Bottom detail row: selected point left, two recommendations right. No Stable Max text.
old_summary='''            if(!g_view.chartSummary.empty())
                drawText(gx,gy+gh+27,13,C_TEXT,fitText(g_view.chartSummary,13,gw));'''
new_summary='''            if(!g_view.chartSummary.empty()){
                const int sy=gy+gh+27;
                const std::string rec="EFF "+std::to_string(g_view.chartEfficiencyMHz)+" MHz   |   PERF "+std::to_string(g_view.chartPerformanceMHz)+" MHz";
                drawText(gx,sy,13,C_TEXT,fitText(g_view.chartSummary,13,std::max(300,gw-330)));
                drawTextRight(gx+gw,sy,13,C_GREEN,rec);
            }'''
g=must_replace(g,old_summary,new_summary,'bottom recommendation row')
p.write_text(g)

# -----------------------------------------------------------------------------
# Deterministic build sanity with the current measured upper curve. These MHz are
# test data only; runtime logic contains no fixed recommendation frequency.
# -----------------------------------------------------------------------------
from statistics import median
freq=[1866,1933,2000,2133,2200,2266,2400,2466,2533,2600,2666,2733,2800,2866,2933,3000]
soc =[637.5,637.5,637.5,662.5,662.5,687.5,712.5,725.0,750.0,775.0,787.5,812.5,850.0,862.5,887.5,925.0]
perf=[92.1,92.7,93.36,95.0,95.25,96.03,96.6,97.16,97.77,98.2,98.6,98.9,99.2,99.3,99.8,100.0]

def py_perf():
    pos=len(freq)-1
    while pos>1:
        dm=freq[pos]-freq[pos-1];dv=max(0.0,soc[pos]-soc[pos-1]);dp=max(0.0,perf[pos]-perf[pos-1])
        cost=dv/dm*100;pr=dp/dm*100;val=dp/dv if dv>1e-9 else 1e9
        pc=[];pp=[];pv=[]
        for j in range(max(1,pos-4),pos):
            f=freq[j]-freq[j-1];v=max(0.0,soc[j]-soc[j-1]);pg=max(0.0,perf[j]-perf[j-1])
            if f<=0: continue
            pp.append(pg/f*100)
            if v>1e-9:pc.append(v/f*100);pv.append(pg/v)
        if len(pc)<2 or len(pp)<2 or len(pv)<2:break
        mc,mp,mv=median(pc),median(pp),median(pv)
        if dv>=12 and cost>=50 and cost>=mc*1.45 and pr<=mp*1.20 and val<=mv*0.90:
            pos-=1;continue
        break
    return freq[pos]

def py_eff():
    start=0
    for p in range(len(freq)):
        if freq[p]>=freq[-1]*0.85 and perf[p]>=perf[-1]*0.98:start=p;break
    for pos in range(max(2,start+1),len(freq)):
        dm=freq[pos]-freq[pos-1];dv=max(0.0,soc[pos]-soc[pos-1]);dp=max(0.0,perf[pos]-perf[pos-1])
        cost=dv/dm*100;pr=dp/dm*100
        pc=[];pp=[]
        for j in range(max(1,pos-4),pos):
            f=freq[j]-freq[j-1];v=max(0.0,soc[j]-soc[j-1]);pg=max(0.0,perf[j]-perf[j-1])
            if f<=0:continue
            pp.append(pg/f*100)
            if v>1e-9:pc.append(v/f*100)
        if len(pc)<2 or len(pp)<2:continue
        mc,mp=median(pc),median(pp)
        if dv>=12 and cost>=50 and cost>=mc*1.45 and pr<=mp*1.25:return freq[pos-1]
    return py_perf()

if py_eff()!=2733 or py_perf()!=2933:
    raise SystemExit(f'Beta43 measured-curve audit failed: EFF {py_eff()} PERF {py_perf()}')
print('PASS beta43 current measured curve -> EFF 2733 / PERF 2933')

# Audit
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
checks={
 'beta43 version':'0.1.0-beta.43' in Path('Makefile').read_text(),
 'performance top down':'costPer100>=50.0' in main[main.find('int findRamSuggestedTargetIndex()'):main.find('int findRamEfficiencyTargetIndex()')],
 'efficiency first knee':'return ids[pos-1]' in main[main.find('int findRamEfficiencyTargetIndex()'):main.find('void refreshRamSuggestedTarget()')],
 'hidden debug chord':'HidNpadButton_ZL | HidNpadButton_ZR' in main and 'HidNpadButton_Plus' in main and 'g.stage=Stage::RamDebug' in main,
 'debug B returns graph':'if(k&HidNpadButton_B)' in main[main.find('if(g.stage==Stage::RamDebug){'):main.find('if(g.stage==Stage::RamTargetExplanation)')],
 'debug hidden normal UI':'Y : Debug data' not in main[main.find('case Stage::RamGraph:'):main.find('case Stage::RamTargetExplanation:')],
 'prominent inspect controls':'Inspect points' in gui and 'roundedBorder(navX' in gui,
 'recommendations bottom right':'EFF ' in gui and 'PERF ' in gui and 'drawTextRight(gx+gw,sy' in gui,
 'stable max text omitted from graph recommendation row':'Stable Max ' not in gui[gui.find('const std::string rec="EFF '):gui.find('drawTextRight(gx+gw,sy',gui.find('const std::string rec="EFF '))],
 'colliding MHz axis unit removed':'drawTextRight(gx+gw,gy+gh+6,10,C_MUTED,"MHz")' not in gui,
 'EFF PERF MAX markers retained':'EFF+PERF' in gui and '"EFF"' in gui and '"PERF"' in gui and '"MAX"' in gui,
 'raw metrics retained':'ramCpuCopyMBs' in main and 'ramGpuWriteMBs' in main and 'ramL2LatencyNs' in main,
 'performance index retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
 'beta41 recovery retained':'NO - retry ' in main and 'YES - mark ' in main,
 'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
 'RAM cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta43 source audit failed: '+', '.join(bad))
