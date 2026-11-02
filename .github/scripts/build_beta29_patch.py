from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta29 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta29 function missing: {signature}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta29 opening brace missing: {signature}")
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
        raise SystemExit(f"beta29 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


def replace_braced(src, marker, replacement):
    pos = src.find(marker)
    if pos < 0:
        raise SystemExit(f"beta29 braced marker missing: {marker}")
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
        raise SystemExit(f"beta29 unbalanced marker: {marker}")
    return src[:pos] + replacement + src[end:]


# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p = Path('Makefile')
s = p.read_text()
s = must_replace(s, 'APP_VERSION := 0.1.0-beta.28', 'APP_VERSION := 0.1.0-beta.29', 'version')
p.write_text(s)


# -----------------------------------------------------------------------------
# Wizard state + target-selection flow.
# -----------------------------------------------------------------------------
p = Path('source/main_oc.cpp')
m = p.read_text()

m = must_replace(
    m,
    '    RamSweepResult,\n    RamBenchmark,\n    RamConfirm,\n};',
    '    RamSweepResult,\n    RamBenchmark,\n    RamConfirm,\n    RamTargetExplanation,\n    RamTargetSelect,\n};',
    'target stages')

m = must_replace(
    m,
    '    int ramConfirmLastFailedMHz = 0;\n',
    '    int ramConfirmLastFailedMHz = 0;\n    int ramTargetMHz = 0;\n',
    'target state')

m = must_replace(
    m,
    'W(ramConfirmMHz); W(ramConfirmInProgress); W(ramConfirmPassed); W(ramConfirmLastFailedMHz);',
    'W(ramConfirmMHz); W(ramConfirmInProgress); W(ramConfirmPassed); W(ramConfirmLastFailedMHz); W(ramTargetMHz);',
    'save target state')
m = must_replace(
    m,
    'R(ramConfirmMHz) R(ramConfirmInProgress) R(ramConfirmPassed) R(ramConfirmLastFailedMHz)',
    'R(ramConfirmMHz) R(ramConfirmInProgress) R(ramConfirmPassed) R(ramConfirmLastFailedMHz) R(ramTargetMHz)',
    'load target state')

m = must_replace(
    m,
    'if(s==Stage::RamBenchmark) return 3;',
    'if(s==Stage::RamBenchmark) return 3;\n    if(s==Stage::RamTargetExplanation || s==Stage::RamTargetSelect) return 3;',
    'target progress step')

# Helpers: measured RAM points, upper-range knee, point navigation and chart data.
insert_marker = 'void analyzeRam(){'
helpers = r'''
std::vector<int> measuredRamPointIndices(){
    std::vector<int> out;
    for(int i=0;i<int(ramPoints.size());++i){
        const auto& p=ramPoints[i];
        if(p.stable && p.combinedStable && p.performance>0.0) out.push_back(i);
    }
    return out;
}

int ramPointIndexByMHz(int mhz){
    for(int i=0;i<int(ramPoints.size());++i)
        if(int(ramPoints[i].requestedMHz)==mhz && ramPoints[i].stable && ramPoints[i].performance>0.0) return i;
    return -1;
}

int findRamSuggestedTargetIndex(){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return -1;
    if(ids.size()==1) return ids.front();

    const int maxIdx=ids.back();
    const double maxPerf=std::max(1e-9,ramPoints[maxIdx].performance);
    const int maxMHz=int(ramPoints[maxIdx].requestedMHz);

    // Work only in the upper useful range. We want a high OC target, not the
    // mathematically cheapest low-frequency point.
    int startPos=0;
    for(int p=0;p<int(ids.size());++p){
        const auto& q=ramPoints[ids[p]];
        if(int(q.requestedMHz)>=int(maxMHz*0.80) && q.performance>=maxPerf*0.90){startPos=p;break;}
    }
    if(int(ids.size())-startPos<2) return ids[ids.size()-2];

    std::vector<double> priorPenalty;
    for(int p=startPos+1;p<int(ids.size());++p){
        const auto& a=ramPoints[ids[p-1]];
        const auto& b=ramPoints[ids[p]];
        const double dv=std::max(0.0,double(b.railMv)-double(a.railMv));
        const double perfGainPct=100.0*std::max(0.0,b.performance-a.performance)/maxPerf;
        const double penalty=dv/std::max(0.25,perfGainPct);

        double baseline=0.0;
        if(!priorPenalty.empty()){
            std::vector<double> tmp=priorPenalty;
            std::sort(tmp.begin(),tmp.end());
            baseline=tmp[tmp.size()/2];
        }

        // First clear upper-range electrical knee: at least one HOC voltage step,
        // poor performance return, and substantially worse than previous steps.
        const bool absoluteKnee=dv>=12.0 && penalty>=20.0;
        const bool relativeKnee=baseline>0.0 && penalty>=baseline*1.6;
        if(absoluteKnee && (priorPenalty.empty() || relativeKnee)) return ids[p-1];
        priorPenalty.push_back(penalty);
    }

    // No pronounced knee: keep one step of headroom below the absolute stable max.
    return ids[ids.size()-2];
}

void refreshRamSuggestedTarget(){
    const int idx=findRamSuggestedTargetIndex();
    if(idx<0) return;
    g.ramRecommendedMHz=int(ramPoints[idx].requestedMHz);
    if(ramPointIndexByMHz(g.ramTargetMHz)<0) g.ramTargetMHz=g.ramRecommendedMHz;
}

void moveRamTarget(int direction){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return;
    int pos=0;
    for(int i=0;i<int(ids.size());++i) if(int(ramPoints[ids[i]].requestedMHz)==g.ramTargetMHz){pos=i;break;}
    pos=std::clamp(pos+direction,0,int(ids.size())-1);
    g.ramTargetMHz=int(ramPoints[ids[pos]].requestedMHz);
    saveState();
}

double ramPerformancePercent(int mhz){
    const auto ids=measuredRamPointIndices();
    if(ids.empty()) return 0.0;
    double maxPerf=0.0;for(int i:ids)maxPerf=std::max(maxPerf,ramPoints[i].performance);
    const int idx=ramPointIndexByMHz(mhz);
    if(idx<0||maxPerf<=0.0) return 0.0;
    return 100.0*ramPoints[idx].performance/maxPerf;
}

std::vector<gui::ChartPoint> ramTargetChart(){
    std::vector<gui::ChartPoint> out;
    for(const auto& p:ramPoints){
        if(!p.stable || !p.combinedStable || p.performance<=0.0) continue;
        gui::ChartPoint q;
        q.x=p.requestedMHz;q.performance=p.performance;q.voltage=p.railMv;q.power=0.0;q.stable=true;
        q.recommended=int(p.requestedMHz)==g.ramRecommendedMHz;
        q.stableMax=int(p.requestedMHz)==g.ramStableMaxMHz;
        q.sweetSpot=q.recommended;
        out.push_back(q);
    }
    return out;
}

int ramChartSelectedIndex(){
    int n=0;
    for(const auto& p:ramPoints){
        if(!p.stable || !p.combinedStable || p.performance<=0.0) continue;
        if(int(p.requestedMHz)==g.ramTargetMHz) return n;
        ++n;
    }
    return 0;
}

std::string ramPointSummary(int mhz){
    const int idx=ramPointIndexByMHz(mhz);
    if(idx<0) return "No measured RAM point selected.";
    std::ostringstream o;
    o<<mhz<<" MHz  |  Performance "<<fmt1(ramPerformancePercent(mhz))<<"%  |  SoC "<<fmtSocConfigMv(int(ramPoints[idx].railMv));
    return o.str();
}
'''
m = must_replace(m, insert_marker, helpers + '\n' + insert_marker, 'RAM target helpers')

# Final benchmark: clear overrides immediately after each point and before the result page.
new_bench_point = r'''bool runFinalRamBenchmarkPoint(int index){
    if(index<0 || index>=int(ramPoints.size())) return false;
    auto& p=ramPoints[index];
    const int freq=int(p.requestedMHz);std::string e;
    if(!guardRamConfig("final RAM benchmark"))return false;
    const int table=socTableForRamMHz(freq);int activeSoc=0;
    if(!occonfig::getSocPoint(table,activeSoc,e)){modalError("Could not read the tuned SoC point before RAM benchmark: "+e);return false;}
    if(activeSoc!=int(p.railMv)){
        modalError("RAM benchmark config mismatch at "+std::to_string(freq)+" MHz: SoC is "+fmtSocConfigMv(activeSoc)+", expected tuned value "+fmtSocConfigMv(int(p.railMv))+".");return false;
    }
    OverrideCleanupScope overrideCleanup;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){modalError(e);return false;}
    auto b=ocbench::runRam("Final RAM benchmark: "+std::to_string(freq)+" MHz");
    // Do not leave the benchmark RAM clock active while results are processed or displayed.
    clearOverrides();
    if(!b.ok){modalError("Final RAM benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" This point was not measured; retry the benchmark sweep.");return false;}
    p.realMHz=b.telemetry.realRamMHz;
    p.performance=b.score;
    p.latencyNs=b.ramNs;
    p.bandwidthMBs=b.cpuRead+b.gpuRead;
    p.batteryPowerW=b.telemetry.batteryPowerW;
    p.powerReliable=false;
    p.context="Final RAM benchmark / tuned SoC / validated DVB-HP-timings";
    savePoints();
    return true;
}'''
m = replace_function(m, 'bool runFinalRamBenchmarkPoint(int index)', new_bench_point)

new_finish_bench = r'''void finishFinalRamBenchmarkSweep(){
    clearOverrides();
    svcSleepThread(150'000'000);
    refreshRamSuggestedTarget();
    if(g.ramRecommendedMHz<=0){modalError("Could not determine a high-performance RAM target from the final benchmark curve.");return;}
    g.ramTargetMHz=g.ramRecommendedMHz;
    g.socTableMHz=socTableForRamMHz(g.ramRecommendedMHz);
    g.socGoodMv=0;
    for(const auto& p:ramPoints)if(int(p.requestedMHz)==g.ramRecommendedMHz){g.socGoodMv=int(p.railMv);break;}
    g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
    g.stage=Stage::RamGraph;saveState();
}'''
m = replace_function(m, 'void finishFinalRamBenchmarkSweep()', new_finish_bench)

# Graph no longer jumps straight to VDD2. Explanation is mandatory before target choice.
old_graph_input = 'if(g.stage==Stage::RamGraph&&(k&HidNpadButton_A)){std::string e;if(!occonfig::setRamMax(g.ramRecommendedMHz,e))modalError(e);else requestReboot(Stage::RamVdd2);redraw=true;continue;}'
new_graph_input = r'''if(g.stage==Stage::RamGraph){
            if(k&HidNpadButton_Left){moveRamTarget(-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){moveRamTarget(1);redraw=true;continue;}
            if((k&HidNpadButton_A)||(k&HidNpadButton_X)){g.stage=Stage::RamTargetExplanation;saveState();redraw=true;continue;}
        }
        if(g.stage==Stage::RamTargetExplanation){
            if(k&HidNpadButton_X){g.stage=Stage::RamGraph;saveState();redraw=true;continue;}
            if(k&HidNpadButton_A){g.stage=Stage::RamTargetSelect;g.ramTargetMHz=g.ramRecommendedMHz;saveState();redraw=true;continue;}
        }
        if(g.stage==Stage::RamTargetSelect){
            if(k&HidNpadButton_Left){moveRamTarget(-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){moveRamTarget(1);redraw=true;continue;}
            if(k&HidNpadButton_X){g.stage=Stage::RamTargetExplanation;saveState();redraw=true;continue;}
            if(k&HidNpadButton_A){
                const int idx=ramPointIndexByMHz(g.ramTargetMHz);std::string e;
                if(idx<0){modalError("Selected RAM target has no final benchmark result.");}
                else{
                    g.ramRecommendedMHz=g.ramTargetMHz;
                    g.socTableMHz=socTableForRamMHz(g.ramRecommendedMHz);
                    g.socGoodMv=int(ramPoints[idx].railMv);g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
                    if(!occonfig::setRamMax(g.ramRecommendedMHz,e))modalError(e);
                    else requestReboot(Stage::RamVdd2);
                }
                redraw=true;continue;
            }
        }'''
m = must_replace(m, old_graph_input, new_graph_input, 'graph/explanation/target input flow')

# Replace RAM graph with dual-bar result; append mandatory explanation and selection pages.
graph_case = r'''case Stage::RamGraph:{
            refreshRamSuggestedTarget();
            v.stageTitle="RAM Benchmark Result";v.fullWidthLayout=true;v.chartLayout=true;v.chartDualBars=true;
            v.chartTitle="RAM performance and SoC voltage by frequency";
            v.chartXLabel="RAM frequency";v.chartPerformanceLabel="Performance %";v.chartCostLabel="SoC voltage";
            v.chartPoints=ramTargetChart();v.chartSelectedIndex=ramChartSelectedIndex();
            v.chartSummary=ramPointSummary(g.ramTargetMHz)+"  |  Suggested "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max "+std::to_string(g.ramStableMaxMHz)+" MHz";
            gui::begin(v);
            print(9,"A : Continue to explanation");
            print(10,"X : Show explanation");
            print(11,"B : Exit");
            gui::present();break;}'''
m = replace_braced(m, 'case Stage::RamGraph:', graph_case)

insert_before = '        case Stage::RamVdd2:{'
new_pages = r'''        case Stage::RamTargetExplanation:{
            v.stageTitle="Choosing Your RAM Target";v.instructionTitle="Read the explanation before choosing your RAM target";v.instructionLine1="";v.instructionLine2="";v.hideValuesCard=true;
            gui::begin(v);
            print(1,"The highest stable RAM clock is not automatically the best daily target.");
            print(3,"The Wizard suggests a high-performance point before SoC voltage starts rising disproportionately for the remaining performance gain.");
            print(5,"Lower RAM frequencies can still be used later. Your selected target only defines the highest RAM clock this profile is tuned to support.");
            print(7,"VDD2 and VDDQ are global RAM voltages. Next, they are tuned for the maximum RAM clock you choose here and those voltages also apply at lower RAM frequencies.");
            print(9,"Choosing a clock you never intend to use can therefore force unnecessarily high VDD2/VDDQ across the whole RAM profile.");
            print(11,"Suggested Target: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");
            print(13,"A : Continue to RAM Target Selection");
            print(14,"X : Back to graph");
            print(15,"B : Exit");
            gui::present();break;}
        case Stage::RamTargetSelect:{
            if(ramPointIndexByMHz(g.ramTargetMHz)<0)g.ramTargetMHz=g.ramRecommendedMHz;
            const int idx=ramPointIndexByMHz(g.ramTargetMHz);
            v.stageTitle="Choose RAM Target";v.instructionTitle="Choose your RAM target";v.instructionLine1="";v.instructionLine2="";v.hideValuesCard=true;
            gui::begin(v);
            print(1,"Select the highest RAM clock you actually intend to use in this profile.");
            print(3,"Selected Target: "+std::to_string(g.ramTargetMHz)+" MHz");
            print(5,"Performance: "+fmt1(ramPerformancePercent(g.ramTargetMHz))+"% of Stable Max");
            print(7,"SoC: "+(idx>=0?fmtSocConfigMv(int(ramPoints[idx].railMv)):std::string("unavailable")));
            print(9,"Wizard Suggested: "+std::to_string(g.ramRecommendedMHz)+" MHz  |  Stable Max: "+std::to_string(g.ramStableMaxMHz)+" MHz");
            print(11,"Use Left / Right to inspect and select another measured stable RAM point.");
            print(13,"A : Use selected RAM target");
            print(14,"X : Back to explanation");
            print(15,"B : Exit");
            gui::present();break;}
'''
m = must_replace(m, insert_before, new_pages + insert_before, 'target pages')

# Appended stages must still show the right task card but not claim live/config values are the target data.
m = must_replace(
    m,
    'if((g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph) || g.stage==Stage::RamBenchmark || g.stage==Stage::RamConfirm){',
    'if((g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph) || g.stage==Stage::RamBenchmark || g.stage==Stage::RamConfirm || g.stage==Stage::RamTargetExplanation || g.stage==Stage::RamTargetSelect){',
    'target stage active-values range')

p.write_text(m)


# -----------------------------------------------------------------------------
# GUI: readable dual bars + lines, seven-point scrolling window, clear legend.
# -----------------------------------------------------------------------------
p = Path('source/gui_console.hpp')
h = p.read_text()
h = must_replace(
    h,
    '    bool chartLayout = false;\n',
    '    bool chartLayout = false;\n    bool chartDualBars = false;\n    int chartSelectedIndex = -1;\n',
    'chart view state')
p.write_text(h)

p = Path('source/gui_console.cpp')
g = p.read_text()

start = g.find('    if (g_view.chartLayout && !g_view.chartPoints.empty()) {')
if start < 0: raise SystemExit('beta29 chart branch missing')
else_marker = '    } else if (completeSummary) {'
elsepos = g.find(else_marker, start)
if elsepos < 0: raise SystemExit('beta29 chart else marker missing')
open_marker = '    if (g_view.chartLayout && !g_view.chartPoints.empty()) {'
old_body = g[start + len(open_marker):elsepos]

special = r'''
        if (g_view.chartDualBars) {
            const int gx=x+64, gy=y+146, gw=w-128, gh=150;
            drawText(gx,y+108,18,C_CYAN,g_view.chartTitle.empty()?"RAM benchmark result":g_view.chartTitle);

            // Explicit legend; colors are never conveyed by tiny text alone.
            roundedRect(gx,y+117,16,10,3,C_GREEN);drawText(gx+23,y+112,14,C_TEXT,"Performance %");
            roundedRect(gx+155,y+117,16,10,3,C_AMBER);drawText(gx+178,y+112,14,C_TEXT,"SoC voltage");
            drawLine(gx+300,y+122,gx+332,y+122,C_GREEN,2);drawText(gx+340,y+112,14,C_MUTED,"connected trend");
            drawLine(gx+475,y+122,gx+507,y+122,C_AMBER,2);

            double maxPerf=0.0,minV=1e30,maxV=-1e30;
            for(const auto&q:g_view.chartPoints){maxPerf=std::max(maxPerf,q.performance);if(q.voltage>0){minV=std::min(minV,q.voltage);maxV=std::max(maxV,q.voltage);}}
            if(maxPerf<=0.0)maxPerf=1.0;if(minV>1e20){minV=0;maxV=1;}if(maxV<=minV)maxV=minV+1;

            const int total=int(g_view.chartPoints.size());
            const int selected=std::clamp(g_view.chartSelectedIndex<0?0:g_view.chartSelectedIndex,0,std::max(0,total-1));
            const int visible=std::min(7,total);
            int first=std::max(0,selected-visible/2);if(first+visible>total)first=std::max(0,total-visible);
            const int groupW=std::max(1,gw/visible);const int barW=std::min(24,std::max(12,groupW/4));
            int prevPerfX=0,prevPerfY=0,prevVoltX=0,prevVoltY=0;bool havePrev=false;
            for(int j=0;j<visible;++j){
                const int i=first+j;const auto&q=g_view.chartPoints[i];const int cx=gx+j*groupW+groupW/2;
                if(i==selected)roundedBorder(cx-groupW/2+4,gy-8,groupW-8,gh+42,10,mix(C_BORDER,C_CYAN,65),mix(C_PANEL,C_CYAN,5),1);
                for(int k=1;k<4;++k){const int yy=gy+gh*k/4;fillRect(cx-groupW/2+6,yy,groupW-12,1,mix(C_BG,C_BORDER,45));}
                const double perfNorm=std::clamp(q.performance/maxPerf,0.0,1.0);
                const double voltNorm=0.18+0.82*std::clamp((q.voltage-minV)/(maxV-minV),0.0,1.0);
                const int ph=std::max(3,int(gh*perfNorm));const int vh=std::max(3,int(gh*voltNorm));
                const int px=cx-barW-3,vx=cx+3;const int py=gy+gh-ph,vy=gy+gh-vh;
                roundedRect(px,py,barW,ph,4,C_GREEN);roundedRect(vx,vy,barW,vh,4,C_AMBER);
                const int ptx=px+barW/2,vtx=vx+barW/2;
                if(havePrev){drawLine(prevPerfX,prevPerfY,ptx,py,C_GREEN,2);drawLine(prevVoltX,prevVoltY,vtx,vy,C_AMBER,2);}
                prevPerfX=ptx;prevPerfY=py;prevVoltX=vtx;prevVoltY=vy;havePrev=true;
                if(q.recommended){fillCircle(cx,gy-4,6,C_CYAN);drawText(cx-10,gy-29,12,C_CYAN,"SUG");}
                if(q.stableMax){fillCircle(cx+13,gy-4,5,C_RED);}
                const std::string f=std::to_string(int(q.x));drawText(cx-textWidth(f,13)/2,gy+gh+8,13,i==selected?C_TEXT:C_MUTED,f);
            }
            fillRect(gx,gy+gh,gw,1,C_BORDER);
            drawTextRight(gx+gw,gy+gh+28,12,C_MUTED,"MHz");
            drawText(gx,gy+gh+42,14,C_MUTED,"Left / Right: inspect measured points");
            if(!g_view.chartSummary.empty())drawText(gx,gy+gh+62,15,C_TEXT,fitText(g_view.chartSummary,15,gw));
        } else {'''

new_branch = open_marker + special + old_body + '        }\n'
g = g[:start] + new_branch + g[elsepos:]
p.write_text(g)


# -----------------------------------------------------------------------------
# Build-time audit.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text();gui=Path('source/gui_console.cpp').read_text();hdr=Path('source/gui_console.hpp').read_text();stress=Path('source/stress_tests.cpp').read_text()
checks={
    'beta29 version':'0.1.0-beta.29' in Path('Makefile').read_text(),
    'target stages appended':'RamTargetExplanation' in main and 'RamTargetSelect' in main,
    'upper range suggestion':'findRamSuggestedTargetIndex' in main and 'maxMHz*0.80' in main and 'maxPerf*0.90' in main,
    'first voltage knee':'absoluteKnee' in main and 'relativeKnee' in main,
    'fallback below stable max':'return ids[ids.size()-2]' in main,
    'benchmark immediate override clear':'Do not leave the benchmark RAM clock active' in main and 'auto b=ocbench::runRam' in main and 'clearOverrides();' in main[main.find('bool runFinalRamBenchmarkPoint'):main.find('void finishFinalRamBenchmarkSweep')],
    'result clear before display':"svcSleepThread(150'000'000)" in main,
    'graph dual bars':'chartDualBars=true' in main and 'roundedRect(px,py,barW,ph' in gui and 'roundedRect(vx,vy,barW,vh' in gui,
    'two trend lines':'drawLine(prevPerfX' in gui and 'drawLine(prevVoltX' in gui,
    'readable legend':'Performance %' in gui and 'SoC voltage' in gui,
    'scroll seven points':'const int visible=std::min(7,total)' in gui,
    'mandatory explanation':'g.stage=Stage::RamTargetExplanation' in main and 'Read the explanation before choosing your RAM target' in main,
    'explanation before selection':'if(k&HidNpadButton_A){g.stage=Stage::RamTargetSelect' in main,
    'back to graph':'X : Back to graph' in main,
    'target arrows':'HidNpadButton_Left' in main and 'HidNpadButton_Right' in main and 'moveRamTarget' in main,
    'target commits max clock':'occonfig::setRamMax(g.ramRecommendedMHz' in main,
    'VDD rails explanation':'VDD2 and VDDQ are global RAM voltages' in main,
    'beta28 DVB8 retained':'g.ramBaseDvb=8' in main and 'setRamPreparation(false,3400,p->vdd2Mv,p->vddqMv,8,1150' in main,
    '1h confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
    'RAM error cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'final benchmark retained':'runFinalRamBenchmarkSweepAutomatic' in main,
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta29 source audit failed: '+', '.join(bad))
