from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta30 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta30 function missing: {signature}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta30 opening brace missing: {signature}")
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == '{': depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"beta30 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


def replace_braced(src, marker, replacement):
    pos = src.find(marker)
    if pos < 0:
        raise SystemExit(f"beta30 braced marker missing: {marker}")
    brace = src.find('{', pos)
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == '{': depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"beta30 unbalanced marker: {marker}")
    return src[:pos] + replacement + src[end:]


# Version.
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.29','APP_VERSION := 0.1.0-beta.30','version')
p.write_text(s)


# RAM recommendation: only inspect the final 10% of the confirmed stable frequency range.
# A lower point is suggested only when the NEXT step shows a clear voltage/performance knee.
# If no clear knee exists in that end-range, Stable Max itself is the suggestion.
p=Path('source/main_oc.cpp')
m=p.read_text()
new_suggest=r'''int findRamSuggestedTargetIndex(){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return -1;
    if(ids.size()==1) return ids.front();

    const int maxIdx=ids.back();
    const int maxMHz=int(ramPoints[maxIdx].requestedMHz);
    const double maxPerf=std::max(1e-9,ramPoints[maxIdx].performance);
    const double minTargetMHz=double(maxMHz)*0.90;

    int startPos=int(ids.size())-1;
    for(int p=0;p<int(ids.size());++p){
        if(double(ramPoints[ids[p]].requestedMHz)>=minTargetMHz){startPos=p;break;}
    }

    // We deliberately need evidence ABOVE a candidate before backing off from it.
    // Compare each end-range step with the recent local steps. One isolated cheap
    // point earlier in the curve must never become a daily high-performance target.
    std::vector<double> priorPenalty;
    std::vector<double> priorDv;
    for(int p=startPos+1;p<int(ids.size());++p){
        const auto& a=ramPoints[ids[p-1]];
        const auto& b=ramPoints[ids[p]];
        const double dv=std::max(0.0,double(b.railMv)-double(a.railMv));
        const double perfGainPct=100.0*std::max(0.0,b.performance-a.performance)/maxPerf;
        const double penalty=dv/std::max(0.20,perfGainPct);

        double medPenalty=0.0,medDv=0.0;
        if(!priorPenalty.empty()){
            auto t=priorPenalty;std::sort(t.begin(),t.end());medPenalty=t[t.size()/2];
            auto v=priorDv;std::sort(v.begin(),v.end());medDv=v[v.size()/2];
        }

        // A knee requires a real SoC increase plus poor performance return.
        // With local history available, the new step must also be materially worse
        // than the recent end-range trend. This avoids false knees from normal HOC steps.
        const bool poorReturn=perfGainPct<=1.50;
        const bool meaningfulDv=dv>=12.0;
        const bool localJump=priorPenalty.empty()
            ? (dv>=25.0 && perfGainPct<=1.0)
            : (penalty>=std::max(20.0,medPenalty*1.75) && dv>=std::max(12.0,medDv+6.0));
        if(meaningfulDv && poorReturn && localJump) return ids[p-1];

        priorPenalty.push_back(penalty);priorDv.push_back(dv);
    }

    // No demonstrated end-range knee: do not invent headroom. The confirmed
    // Stable Max is the high-end daily suggestion; the user may still choose lower.
    return maxIdx;
}'''
m=replace_function(m,'int findRamSuggestedTargetIndex()',new_suggest)

# Result graph: all measured points on one page, line view. Left/Right only moves
# the inspection cursor; it never hides points.
graph_case=r'''case Stage::RamGraph:{
            refreshRamSuggestedTarget();
            v.stageTitle="RAM Benchmark Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartDualBars=false;v.chartRamLines=true;
            v.chartTitle="RAM performance and SoC voltage";
            v.chartXLabel="RAM frequency";v.chartPerformanceLabel="Performance %";v.chartCostLabel="SoC voltage";
            v.chartPoints=ramTargetChart();v.chartSelectedIndex=ramChartSelectedIndex();
            v.chartSummary=ramPointSummary(g.ramTargetMHz)+"  |  Suggested "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max "+std::to_string(g.ramStableMaxMHz)+" MHz";
            gui::begin(v);
            print(9,"A : Continue to explanation");
            print(10,"X : Show explanation");
            print(11,"B : Exit");
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamGraph:',graph_case)
p.write_text(m)


# Dedicated RAM all-points line renderer. Keep beta29 dual bars in source as an
# unused fallback so this remains a small, reversible visual patch.
p=Path('source/gui_console.hpp')
h=p.read_text()
h=must_replace(h,'    bool chartDualBars = false;\n','    bool chartDualBars = false;\n    bool chartRamLines = false;\n','RAM line chart flag')
p.write_text(h)

p=Path('source/gui_console.cpp')
g=p.read_text()
ram_lines=r'''        if (g_view.chartRamLines) {
            const int gx=x+70, gy=y+145, gw=w-140, gh=160;
            drawText(gx,y+106,18,C_CYAN,g_view.chartTitle.empty()?"RAM benchmark result":g_view.chartTitle);

            // Compact, readable legend above the plot. No legend is placed under
            // the chart where the action buttons live.
            roundedRect(gx+520,y+109,14,8,3,C_GREEN);
            drawText(gx+541,y+103,13,C_TEXT,"Performance %");
            roundedRect(gx+680,y+109,14,8,3,C_AMBER);
            drawText(gx+701,y+103,13,C_TEXT,"SoC mV");

            const int total=int(g_view.chartPoints.size());
            double maxPerf=0.0,minVolt=1e30,maxVolt=0.0;
            for(const auto&q:g_view.chartPoints){
                maxPerf=std::max(maxPerf,q.performance);
                if(q.voltage>0.0){minVolt=std::min(minVolt,q.voltage);maxVolt=std::max(maxVolt,q.voltage);}
            }
            if(maxPerf<=0.0)maxPerf=1.0;
            if(minVolt>1e20){minVolt=0.0;maxVolt=1.0;}
            if(maxVolt<=minVolt)maxVolt=minVolt+1.0;
            // Add visual breathing room to the voltage axis so small changes remain visible.
            const double voltPad=std::max(6.25,(maxVolt-minVolt)*0.08);
            minVolt=std::max(0.0,minVolt-voltPad);maxVolt+=voltPad;

            auto px=[&](int i){return total<=1?gx+gw/2:gx+int(double(i)*double(gw)/double(total-1));};
            auto pyP=[&](double perf){const double pct=100.0*perf/maxPerf;return gy+gh-int(std::clamp(pct,0.0,100.0)/100.0*gh);};
            auto pyV=[&](double mv){return gy+gh-int((mv-minVolt)/(maxVolt-minVolt)*gh);};

            fillRect(gx,gy+gh,gw,1,C_BORDER);fillRect(gx,gy,1,gh,C_BORDER);
            for(int k=1;k<4;++k){const int yy=gy+gh*k/4;fillRect(gx,yy,gw,1,mix(C_BG,C_BORDER,52));}

            // Selection cursor: all points remain visible while Left/Right only changes focus.
            const int selected=std::clamp(g_view.chartSelectedIndex,0,std::max(0,total-1));
            if(total>0){const int sx=px(selected);drawLine(sx,gy,sx,gy+gh,mix(C_BG,C_CYAN,52),1);}

            for(int i=1;i<total;++i){
                const auto&a=g_view.chartPoints[i-1];const auto&b=g_view.chartPoints[i];
                drawLine(px(i-1),pyP(a.performance),px(i),pyP(b.performance),C_GREEN,2);
                drawLine(px(i-1),pyV(a.voltage),px(i),pyV(b.voltage),C_AMBER,2);
            }

            for(int i=0;i<total;++i){
                const auto&q=g_view.chartPoints[i];const int xx=px(i);
                fillCircle(xx,pyP(q.performance),i==selected?6:4,i==selected?C_CYAN:C_GREEN);
                fillCircle(xx,pyV(q.voltage),i==selected?6:4,i==selected?C_CYAN:C_AMBER);
                if(q.recommended){
                    drawText(std::max(gx,xx-18),gy-20,11,C_GREEN,"SUG");
                }
                if(q.stableMax){
                    drawText(std::min(gx+gw-28,std::max(gx,xx-14)),gy-34,11,C_RED,"MAX");
                }
            }

            // Keep every measurement point visible. Label every point when space
            // allows; on long sweeps alternate labels while the cursor still reaches all points.
            const int labelEvery=total<=16?1:2;
            for(int i=0;i<total;++i){
                if(i%labelEvery!=0 && i!=selected && i!=total-1)continue;
                const std::string lab=std::to_string(int(std::round(g_view.chartPoints[i].x)));
                const int xx=px(i);drawText(xx-textWidth(lab,10)/2,gy+gh+8,10,i==selected?C_TEXT:C_MUTED,lab);
            }
            drawTextRight(gx+gw,gy+gh+8,10,C_MUTED,"MHz");

            if(!g_view.chartSummary.empty())
                drawText(gx,gy+gh+30,14,C_TEXT,fitText(g_view.chartSummary,14,gw));
        } else if (g_view.chartDualBars) {'''
g=must_replace(g,'        if (g_view.chartDualBars) {',ram_lines,'RAM all-points line renderer')
p.write_text(g)


# Audits.
main=Path('source/main_oc.cpp').read_text();gui=Path('source/gui_console.cpp').read_text();hpp=Path('source/gui_console.hpp').read_text();stress=Path('source/stress_tests.cpp').read_text()
checks={
 'beta30 version':'0.1.0-beta.30' in Path('Makefile').read_text(),
 'end range 90 percent':'minTargetMHz=double(maxMHz)*0.90' in main,
 'no-knee keeps stable max':'return maxIdx;' in main[main.find('int findRamSuggestedTargetIndex'):main.find('void refreshRamSuggestedTarget')],
 'clear knee backs off':'return ids[p-1]' in main[main.find('int findRamSuggestedTargetIndex'):main.find('void refreshRamSuggestedTarget')],
 'ram line chart enabled':'chartRamLines=true' in main and 'bool chartRamLines = false' in hpp,
 'all points renderer':'Keep every measurement point visible' in gui and 'const int total=int(g_view.chartPoints.size())' in gui,
 'no seven point window in ram lines':'chartRamLines' in gui,
 'selection cursor':'Selection cursor' in gui and 'chartSelectedIndex' in gui,
 'top compact legend':'Performance %' in gui and 'SoC mV' in gui,
 'mandatory explanation retained':'Read the explanation before choosing your RAM target' in main,
 'target selection retained':'Choose RAM Target' in main and 'moveRamTarget' in main,
 'benchmark override cleanup retained':'Do not leave the benchmark RAM clock active' in main,
 'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
 'DVB8 automatic baseline retained':'g.ramBaseDvb=8' in main,
 'RAM error immediate cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta30 source audit failed: '+', '.join(bad))
