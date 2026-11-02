from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta39 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta39 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta39 opening brace missing: {signature}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None: raise SystemExit(f"beta39 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]


# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.38','APP_VERSION := 0.1.0-beta.39','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()

# Final RAM recommendation:
# - Work top-down from Stable Max, never search globally for a low-frequency sweet spot.
# - Compare marginal SoC cost per 100 MHz with recent lower steps.
# - Performance remains important: an expensive voltage step is rejected only when its
#   performance gain per 100 MHz / performance-per-mV return is not exceptional.
# - Stop at the first upper point whose step returns to the local trend.
new_suggest=r'''int findRamSuggestedTargetIndex(){
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

    // Evaluate only the marginal transition into the current high-end candidate.
    // If that step is clearly worse than the local history, back off one measured
    // point and repeat. This allows a temporary expensive step lower in the curve
    // without incorrectly making that lower point the daily recommendation.
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
            // Zero-voltage plateaus are excellent electrically, but cannot form a
            // stable denominator for the local mV trend. Keep their performance
            // information while excluding them from voltage/value medians.
            prevPerfRate.push_back(pg/f*100.0);
            if(v>1e-9){
                prevCost.push_back(v/f*100.0);
                prevValue.push_back(pg/v);
            }
        }

        // Need a real local history before rejecting a proven Stable Max point.
        if(prevCost.size()<2 || prevPerfRate.size()<2 || prevValue.size()<2) break;
        const double medCost=median(prevCost);
        const double medPerf=median(prevPerfRate);
        const double medValue=median(prevValue);
        if(medCost<=1e-9) break;

        // Electrical knee: the next MHz became markedly more expensive than the
        // same console's recent steps. Performance can save an expensive step only
        // when its measured gain is genuinely exceptional relative to local history.
        const bool meaningfulVoltage=dV>=12.0;
        const bool expensiveStep=costPer100>=medCost*1.60;
        const bool performanceNotExceptional=(medPerf<=1e-9) || (perfPer100<=medPerf*1.35);
        const bool poorCombinedReturn=(medValue<=1e-9) || (valuePerMv<=medValue*0.80);

        if(meaningfulVoltage && expensiveStep && performanceNotExceptional && poorCombinedReturn){
            --pos;
            continue;
        }
        break;
    }
    return ids[pos];
}'''
m=replace_function(m,'int findRamSuggestedTargetIndex()',new_suggest)

# Explanation: tell the user what is actually being compared now.
old_exp='''            print(3,"The Wizard suggests a high-performance point before SoC voltage starts rising disproportionately for the remaining performance gain.");'''
new_exp='''            print(3,"The Wizard compares each high-end step's performance gain per MHz with its additional SoC mV per MHz and the recent local trend.");'''
m=must_replace(m,old_exp,new_exp,'target explanation')

# Make the automatic recommendation unmistakable in the manual target selector.
old_select='''            print(3,"Selected Target: "+std::to_string(g.ramTargetMHz)+" MHz");
            print(5,"Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"% of Stable Max");
            print(7,"SoC: "+(idx>=0?fmtSocConfigMv(int(ramPoints[idx].railMv)):std::string("unavailable")));
            print(9,"Wizard Suggested: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");'''
new_select='''            const bool selectedRecommended=(g.ramTargetMHz==g.ramRecommendedMHz);
            print(3,"Selected Target: "+std::to_string(g.ramTargetMHz)+" MHz"+(selectedRecommended?std::string("   [ RECOMMENDED ]"):std::string("")));
            print(5,"Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"% of Stable Max");
            print(7,"SoC: "+(idx>=0?fmtSocConfigMv(int(ramPoints[idx].railMv)):std::string("unavailable")));
            print(9,"Recommended: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");'''
m=must_replace(m,old_select,new_select,'recommended target highlight')

# Graph wording only: keep the same two curves and markers, but use the final term.
m=m.replace('"  |  Suggested "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max "',
            '"  |  Recommended "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max "',1)

p.write_text(m)

# Deterministic sanity check using the user's beta32/36 debug series. The logic
# must identify 2933 MHz without any hardcoded runtime frequency.
def py_median(v):
    v=sorted(v); n=len(v)
    return v[n//2] if n%2 else (v[n//2-1]+v[n//2])/2

def py_suggest(freq,soc,perf):
    pos=len(freq)-1
    while pos>1:
        dm=freq[pos]-freq[pos-1]; dv=max(0.0,soc[pos]-soc[pos-1]); dp=max(0.0,perf[pos]-perf[pos-1])
        cost=dv/dm*100; pr=dp/dm*100; val=dp/dv if dv>1e-9 else 1e9
        costs=[]; prs=[]; vals=[]
        for j in range(max(1,pos-4),pos):
            f=freq[j]-freq[j-1]; v=max(0.0,soc[j]-soc[j-1]); pg=max(0.0,perf[j]-perf[j-1])
            if f<=0: continue
            prs.append(pg/f*100)
            if v>1e-9:
                costs.append(v/f*100); vals.append(pg/v)
        if len(costs)<2 or len(prs)<2 or len(vals)<2: break
        mc,mp,mv=py_median(costs),py_median(prs),py_median(vals)
        if dv>=12 and cost>=mc*1.60 and (mp<=1e-9 or pr<=mp*1.35) and (mv<=1e-9 or val<=mv*0.80):
            pos-=1; continue
        break
    return freq[pos]

# Values transcribed from the final debug pages; only used by the build audit.
freq=[1866,1933,2000,2133,2200,2266,2400,2466,2533,2666,2733,2800,2933,3000]
soc =[637.5,637.5,637.5,662.5,662.5,687.5,712.5,725.0,750.0,787.5,812.5,850.0,887.5,925.0]
perf=[92.101,92.702,93.356,95.004,95.255,96.027,96.597,97.164,97.774,98.538,98.735,99.224,99.703,100.000]
if py_suggest(freq,soc,perf)!=2933:
    raise SystemExit('Beta39 synthetic debug-curve audit failed: expected 2933 MHz')
print('PASS beta39 real debug curve -> 2933 MHz')

main=Path('source/main_oc.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text()
fn=main[main.find('int findRamSuggestedTargetIndex()'):main.find('void refreshRamSuggestedTarget()')]
checks={
    'beta39 version':'0.1.0-beta.39' in Path('Makefile').read_text(),
    'top down recommendation':'while(pos>1)' in fn and '--pos;' in fn,
    'mV per 100 MHz':'costPer100=dV/dMHz*100.0' in fn,
    'performance per 100 MHz':'perfPer100=dPerf/dMHz*100.0' in fn,
    'performance per mV':'valuePerMv=dV>1e-9?dPerf/dV' in fn,
    'local median history':'medCost=median(prevCost)' in fn and 'medPerf=median(prevPerfRate)' in fn and 'medValue=median(prevValue)' in fn,
    'electrical outlier':'costPer100>=medCost*1.60' in fn,
    'performance can save step':'perfPer100<=medPerf*1.35' in fn,
    'combined return':'valuePerMv<=medValue*0.80' in fn,
    'recommended highlight':'[ RECOMMENDED ]' in main and 'selectedRecommended' in main,
    'recommended selector label':'Recommended: ' in main,
    'graph retained':'chartRamLines=true' in main and 'Performance %' in gui and 'SoC mV' in gui,
    'mandatory explanation':'Read the explanation before choosing your RAM target' in main,
    'free target arrows':'moveRamTarget(-1)' in main and 'moveRamTarget(1)' in main,
    'beta32 index retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
    'beta37 transition retained':'Next RAM candidate: ' in main and 'Temporary RAM override is OFF.' in main,
    'beta38 recovery retained':'MHz confirmation did not finish' in main and 'm.primaryAction="Recover last good value"' in main,
    'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta39 source audit failed: '+', '.join(bad))
