from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta40 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta40 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta40 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta40 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]


# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.39','APP_VERSION := 0.1.0-beta.40','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()

# Persist a second recommendation. ramRecommendedMHz remains the Performance
# Recommendation until the user commits a manual target, preserving downstream logic.
m=must_replace(m,
    '    int ramTargetMHz = 0;\n',
    '    int ramTargetMHz = 0;\n    int ramEfficiencyRecommendedMHz = 0;\n',
    'efficiency recommendation state')
m=must_replace(m,
    'W(ramConfirmMHz); W(ramConfirmInProgress); W(ramConfirmPassed); W(ramConfirmLastFailedMHz); W(ramTargetMHz);',
    'W(ramConfirmMHz); W(ramConfirmInProgress); W(ramConfirmPassed); W(ramConfirmLastFailedMHz); W(ramTargetMHz); W(ramEfficiencyRecommendedMHz);',
    'save efficiency recommendation')
m=must_replace(m,
    'R(ramConfirmMHz) R(ramConfirmInProgress) R(ramConfirmPassed) R(ramConfirmLastFailedMHz) R(ramTargetMHz)',
    'R(ramConfirmMHz) R(ramConfirmInProgress) R(ramConfirmPassed) R(ramConfirmLastFailedMHz) R(ramTargetMHz) R(ramEfficiencyRecommendedMHz)',
    'load efficiency recommendation')

# Efficiency Recommendation:
# - Separate goal from Beta39 Performance Recommendation.
# - Stay in the high-performance region, then scan upward for the FIRST clear
#   electrical knee. This deliberately values voltage efficiency more strongly.
# - Performance is still part of the decision: an expensive step is accepted if
#   its measured performance return is genuinely exceptional.
# - If there is no convincing efficiency knee, fall back to Performance Recommendation.
eff_fn=r'''
int findRamEfficiencyTargetIndex(){
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

    // Do not let an efficient low-frequency point become the recommendation.
    // Efficiency tuning starts only once we are already in the upper useful region.
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
            if(v>1e-9){
                prevCost.push_back(v/f*100.0);
                prevValue.push_back(pg/v);
            }
        }
        if(prevCost.size()<2 || prevPerfRate.size()<2 || prevValue.size()<2) continue;
        const double medCost=median(prevCost);
        const double medPerf=median(prevPerfRate);
        const double medValue=median(prevValue);
        if(medCost<=1e-9) continue;

        // Efficiency mode is intentionally stricter than Performance mode:
        // detect the first high-end electrical knee, but never reject an expensive
        // step whose measured performance return is clearly exceptional.
        const bool meaningfulVoltage=dV>=12.0;
        const bool expensiveStep=costPer100>=medCost*1.65;
        const bool performanceNotExceptional=(medPerf<=1e-9) || (perfPer100<=medPerf*1.25);
        const bool poorCombinedReturn=(medValue<=1e-9) || (valuePerMv<=medValue*0.90);
        if(meaningfulVoltage && expensiveStep && performanceNotExceptional && poorCombinedReturn)
            return ids[pos-1];
    }

    return findRamSuggestedTargetIndex();
}
'''
m=must_replace(m,'void refreshRamSuggestedTarget(){',eff_fn+'\nvoid refreshRamSuggestedTarget(){','efficiency recommendation function')

new_refresh=r'''void refreshRamSuggestedTarget(){
    const int perfIdx=findRamSuggestedTargetIndex();
    if(perfIdx<0) return;
    g.ramRecommendedMHz=int(ramPoints[perfIdx].requestedMHz);

    const int effIdx=findRamEfficiencyTargetIndex();
    g.ramEfficiencyRecommendedMHz=effIdx>=0?int(ramPoints[effIdx].requestedMHz):g.ramRecommendedMHz;
    // Efficiency may equal Performance on a very clean curve, but it should never
    // claim a higher target than the performance-oriented recommendation.
    if(g.ramEfficiencyRecommendedMHz>g.ramRecommendedMHz)
        g.ramEfficiencyRecommendedMHz=g.ramRecommendedMHz;

    if(ramPointIndexByMHz(g.ramTargetMHz)<0) g.ramTargetMHz=g.ramRecommendedMHz;
}'''
m=replace_function(m,'void refreshRamSuggestedTarget()',new_refresh)

# Chart data exposes both recommendation types.
old_chart='''        q.recommended=int(p.requestedMHz)==g.ramRecommendedMHz;
        q.stableMax=int(p.requestedMHz)==g.ramStableMaxMHz;
        q.sweetSpot=q.recommended;'''
new_chart='''        q.recommended=int(p.requestedMHz)==g.ramRecommendedMHz; // Performance Recommendation
        q.efficiencyRecommended=int(p.requestedMHz)==g.ramEfficiencyRecommendedMHz;
        q.stableMax=int(p.requestedMHz)==g.ramStableMaxMHz;
        q.sweetSpot=q.recommended || q.efficiencyRecommended;'''
m=must_replace(m,old_chart,new_chart,'dual chart recommendations')

# Helper for selection badges. A point may legitimately carry more than one role.
badge_marker='std::string ramPointSummary(int mhz){'
badge_fn=r'''
std::string ramTargetBadges(int mhz){
    std::vector<std::string> tags;
    if(mhz==g.ramEfficiencyRecommendedMHz) tags.push_back("EFFICIENCY");
    if(mhz==g.ramRecommendedMHz) tags.push_back("PERFORMANCE");
    if(mhz==g.ramStableMaxMHz) tags.push_back("STABLE MAX");
    if(tags.empty()) return {};
    std::string out="   [ ";
    for(size_t i=0;i<tags.size();++i){if(i)out+=" + ";out+=tags[i];}
    out+=" ]";
    return out;
}

'''
m=must_replace(m,badge_marker,badge_fn+badge_marker,'target badge helper')

# Graph summary: make the two meanings explicit while keeping both curves unchanged.
old_summary='''v.chartSummary=ramPointSummary(g.ramTargetMHz)+"  |  Recommended "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max "+std::to_string(g.ramStableMaxMHz)+" MHz";'''
new_summary='''v.chartSummary=ramPointSummary(g.ramTargetMHz)+"  |  Efficiency "+std::to_string(g.ramEfficiencyRecommendedMHz)+"  |  Performance "+std::to_string(g.ramRecommendedMHz)+"  |  Max "+std::to_string(g.ramStableMaxMHz)+" MHz";'''
m=must_replace(m,old_summary,new_summary,'dual graph summary')

# Mandatory explanation: describe the consequences of choosing the lower target.
m=must_replace(m,
    '            print(1,"The highest stable RAM clock is not automatically the best daily target.");',
    '            print(1,"The Wizard provides an Efficiency Recommendation and a Performance Recommendation.");',
    'explanation intro')
m=must_replace(m,
    '            print(3,"The Wizard compares each high-end step\'s performance gain per MHz with its additional SoC mV per MHz and the recent local trend.");',
    '            print(3,"Efficiency favors the first high-end point before voltage cost rises disproportionately, while still requiring strong measured performance.");',
    'efficiency explanation')
m=must_replace(m,
    '            print(5,"Lower RAM frequencies can still be used later. Your selected target only defines the highest RAM clock this profile is tuned to support.");',
    '            print(5,"Performance stays closer to Stable Max and backs off only when extra voltage is no longer justified by the measured performance return.");',
    'performance explanation')
m=must_replace(m,
    '            print(7,"VDD2 and VDDQ are global RAM voltages. Next, they are tuned for the maximum RAM clock you choose here and those voltages also apply at lower RAM frequencies.");',
    '            print(7,"Your selected target becomes this profile\'s maximum tuned RAM clock. VDD2/VDDQ are optimized for that target; higher clocks are not validated afterward.");',
    'selected target consequence')
m=must_replace(m,
    '            print(9,"Choosing a clock you never intend to use can therefore force unnecessarily high VDD2/VDDQ across the whole RAM profile.");',
    '            print(9,"Choosing Efficiency can therefore lower the voltage requirement of the whole RAM profile, at the cost of giving up the higher Performance target.");',
    'efficiency consequence')
m=must_replace(m,
    '            print(11,"Suggested Target: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");',
    '            print(11,"Efficiency: "+std::to_string(g.ramEfficiencyRecommendedMHz)+" MHz  |  Performance: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");',
    'dual explanation values')

# Target selector: highlight either recommendation (or both) and keep Stable Max explicit.
old_select='''            const bool selectedRecommended=(g.ramTargetMHz==g.ramRecommendedMHz);
            print(3,"Selected Target: "+std::to_string(g.ramTargetMHz)+" MHz"+(selectedRecommended?std::string("   [ RECOMMENDED ]"):std::string("")));
            print(5,"Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"% of Stable Max");
            print(7,"SoC: "+(idx>=0?fmtSocConfigMv(int(ramPoints[idx].railMv)):std::string("unavailable")));
            print(9,"Recommended: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");'''
new_select='''            print(3,"Selected Target: "+std::to_string(g.ramTargetMHz)+" MHz"+ramTargetBadges(g.ramTargetMHz));
            print(5,"Benchmark Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"% of Stable Max");
            print(7,"SoC: "+(idx>=0?fmtSocConfigMv(int(ramPoints[idx].railMv)):std::string("unavailable")));
            print(9,"Efficiency: "+std::to_string(g.ramEfficiencyRecommendedMHz)+" MHz  |  Performance: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");'''
m=must_replace(m,old_select,new_select,'dual target selector')

p.write_text(m)

# ChartPoint needs one additional role flag.
p=Path('source/gui_console.hpp'); h=p.read_text()
h=must_replace(h,
    '    bool recommended = false;\n',
    '    bool recommended = false; // Performance Recommendation\n    bool efficiencyRecommended = false;\n',
    'efficiency chart flag')
p.write_text(h)

# RAM graph markers: PERF and EFF instead of the old single SUG label.
p=Path('source/gui_console.cpp'); g=p.read_text()
old_marker='''                if(q.recommended){
                    drawText(std::max(gx,xx-18),gy-20,11,C_GREEN,"SUG");
                }
                if(q.stableMax){'''
new_marker='''                if(q.recommended && q.efficiencyRecommended){
                    drawText(std::max(gx,xx-30),gy-20,10,C_GREEN,"EFF+PERF");
                }else if(q.efficiencyRecommended){
                    drawText(std::max(gx,xx-16),gy-20,11,C_GREEN,"EFF");
                }else if(q.recommended){
                    drawText(std::max(gx,xx-18),gy-20,11,C_GREEN,"PERF");
                }
                if(q.stableMax){'''
g=must_replace(g,old_marker,new_marker,'dual graph markers')
p.write_text(g)

# -----------------------------------------------------------------------------
# Deterministic sanity tests using the measured debug curve. These test the
# algorithms only; runtime code contains no fixed 2733/2933 target.
# -----------------------------------------------------------------------------
def med(v):
    v=sorted(v); n=len(v)
    return v[n//2] if n%2 else 0.5*(v[n//2-1]+v[n//2])

def perf_rec(freq,soc,perf):
    pos=len(freq)-1
    while pos>1:
        dm=freq[pos]-freq[pos-1]; dv=max(0.0,soc[pos]-soc[pos-1]); dp=max(0.0,perf[pos]-perf[pos-1])
        cost=dv/dm*100; pr=dp/dm*100; val=dp/dv if dv>1e-9 else 1e9
        costs=[]; prs=[]; vals=[]
        for j in range(max(1,pos-4),pos):
            f=freq[j]-freq[j-1]; v=max(0.0,soc[j]-soc[j-1]); pg=max(0.0,perf[j]-perf[j-1])
            if f<=0: continue
            prs.append(pg/f*100)
            if v>1e-9: costs.append(v/f*100); vals.append(pg/v)
        if len(costs)<2 or len(prs)<2 or len(vals)<2: break
        mc,mp,mv=med(costs),med(prs),med(vals)
        if dv>=12 and cost>=mc*1.60 and (mp<=1e-9 or pr<=mp*1.35) and (mv<=1e-9 or val<=mv*0.80):
            pos-=1; continue
        break
    return freq[pos]

def eff_rec(freq,soc,perf):
    maxf=freq[-1]; maxp=perf[-1]
    start=0
    for p in range(len(freq)):
        if freq[p]>=maxf*0.85 and perf[p]>=maxp*0.98:
            start=p; break
    for pos in range(max(2,start+1),len(freq)):
        dm=freq[pos]-freq[pos-1]; dv=max(0.0,soc[pos]-soc[pos-1]); dp=max(0.0,perf[pos]-perf[pos-1])
        cost=dv/dm*100; pr=dp/dm*100; val=dp/dv if dv>1e-9 else 1e9
        costs=[]; prs=[]; vals=[]
        for j in range(max(1,pos-4),pos):
            f=freq[j]-freq[j-1]; v=max(0.0,soc[j]-soc[j-1]); pg=max(0.0,perf[j]-perf[j-1])
            if f<=0: continue
            prs.append(pg/f*100)
            if v>1e-9: costs.append(v/f*100); vals.append(pg/v)
        if len(costs)<2 or len(prs)<2 or len(vals)<2: continue
        mc,mp,mv=med(costs),med(prs),med(vals)
        if dv>=12 and cost>=mc*1.65 and (mp<=1e-9 or pr<=mp*1.25) and (mv<=1e-9 or val<=mv*0.90):
            return freq[pos-1]
    return perf_rec(freq,soc,perf)

freq=[1866,1933,2000,2133,2200,2266,2400,2466,2533,2666,2733,2800,2933,3000]
soc =[637.5,637.5,637.5,662.5,662.5,687.5,712.5,725.0,750.0,787.5,812.5,850.0,887.5,925.0]
perf=[92.101,92.702,93.356,95.004,95.255,96.027,96.597,97.164,97.774,98.538,98.735,99.224,99.703,100.000]
if eff_rec(freq,soc,perf)!=2733: raise SystemExit('Beta40 measured-curve Efficiency audit failed')
if perf_rec(freq,soc,perf)!=2933: raise SystemExit('Beta40 measured-curve Performance audit failed')
print('PASS beta40 measured curve -> Efficiency 2733 / Performance 2933 / Max 3000')

main=Path('source/main_oc.cpp').read_text(); hdr=Path('source/gui_console.hpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
eff=main[main.find('int findRamEfficiencyTargetIndex()'):main.find('void refreshRamSuggestedTarget()')]
perf_fn=main[main.find('int findRamSuggestedTargetIndex()'):main.find('int findRamEfficiencyTargetIndex()')]
checks={
 'beta40 version':'0.1.0-beta.40' in Path('Makefile').read_text(),
 'efficiency state persisted':'ramEfficiencyRecommendedMHz' in main and 'W(ramEfficiencyRecommendedMHz)' in main and 'R(ramEfficiencyRecommendedMHz)' in main,
 'separate efficiency algorithm':'findRamEfficiencyTargetIndex' in main and 'maxMHz*0.85' in eff and 'maxPerf*0.98' in eff,
 'efficiency first upper knee':'for(int pos=std::max(2,startPos+1)' in eff and 'return ids[pos-1]' in eff,
 'efficiency electrical weight':'costPer100>=medCost*1.65' in eff,
 'efficiency still uses performance':'perfPer100<=medPerf*1.25' in eff and 'valuePerMv<=medValue*0.90' in eff,
 'performance recommendation retained':'while(pos>1)' in perf_fn and 'costPer100>=medCost*1.60' in perf_fn,
 'efficiency not above performance':'g.ramEfficiencyRecommendedMHz>g.ramRecommendedMHz' in main,
 'graph dual summary':'Efficiency ' in main and 'Performance ' in main and 'Stable Max' in main,
 'graph dual markers':'efficiencyRecommended' in hdr and 'EFF+PERF' in gui and '"PERF"' in gui and '"EFF"' in gui,
 'selector badges':'ramTargetBadges' in main and 'EFFICIENCY' in main and 'PERFORMANCE' in main and 'STABLE MAX' in main,
 'selected target consequence':'higher clocks are not validated afterward' in main,
 'VDD target consequence':'VDD2/VDDQ are optimized for that target' in main,
 'free selection retained':'moveRamTarget(-1)' in main and 'moveRamTarget(1)' in main,
 'mandatory explanation retained':'Read the explanation before choosing your RAM target' in main,
 'beta32 index retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
 'beta37 transition retained':'Next RAM candidate: ' in main and 'Temporary RAM override is OFF.' in main,
 'beta38 recovery retained':'MHz confirmation did not finish' in main and 'm.primaryAction="Recover last good value"' in main,
 'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
 'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta40 source audit failed: '+', '.join(bad))
