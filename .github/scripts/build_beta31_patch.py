from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta31 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos = src.find(marker)
    if pos < 0:
        raise SystemExit(f"beta31 braced marker missing: {marker}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta31 opening brace missing: {marker}")
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
        raise SystemExit(f"beta31 unbalanced marker: {marker}")
    return src[:pos] + replacement + src[end:]


# Version.
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.30','APP_VERSION := 0.1.0-beta.31','version')
p.write_text(s)

p=Path('source/main_oc.cpp')
m=p.read_text()

# Append-only stage to preserve all persisted enum numbers from previous betas.
m=must_replace(
    m,
    '    RamTargetExplanation,\n    RamTargetSelect,\n};',
    '    RamTargetExplanation,\n    RamTargetSelect,\n    RamDebug,\n};',
    'append RAM debug stage')

# Local debug-page cursor. This is intentionally not persisted; it is diagnostics only.
m=must_replace(
    m,
    'bool g_recoveryModal = false;\n',
    'bool g_recoveryModal = false;\nint g_ramDebugPage = 0;\n',
    'RAM debug page cursor')

# Helpers are inserted after beta29/beta30 RAM result helpers, immediately before analyzeRam().
marker='void analyzeRam(){'
helpers=r'''
std::vector<int> ramDebugPointIndices(){
    std::vector<int> out;
    for(int i=0;i<int(ramPoints.size());++i){
        const auto& p=ramPoints[i];
        if(p.stable && p.combinedStable && p.performance>0.0 && int(p.requestedMHz)>=1866) out.push_back(i);
    }
    return out;
}

std::string fmt2Debug(double v){char b[40];std::snprintf(b,sizeof(b),"%.2f",v);return b;}
std::string fmt3Debug(double v){char b[40];std::snprintf(b,sizeof(b),"%.3f",v);return b;}
std::string fmt0Debug(double v){char b[40];std::snprintf(b,sizeof(b),"%.0f",v);return b;}

int ramDebugPageCount(){
    const int n=int(ramDebugPointIndices().size());
    return std::max(1,(n+7)/8);
}

std::string ramDebugRow(int absolutePos){
    const auto ids=ramDebugPointIndices();
    if(absolutePos<0 || absolutePos>=int(ids.size())) return {};
    const auto& p=ramPoints[ids[absolutePos]];
    const double perfPct=ramPerformancePercent(int(p.requestedMHz));

    std::string dMv="-", cost="-";
    if(absolutePos>0){
        const auto& prev=ramPoints[ids[absolutePos-1]];
        const double dMHz=double(p.requestedMHz)-double(prev.requestedMHz);
        const double dv=double(p.railMv)-double(prev.railMv);
        dMv=(dv>=0?"+":"")+fmt2Debug(dv);
        if(std::abs(dMHz)>0.001) cost=fmt2Debug(dv/dMHz*100.0);
    }

    std::ostringstream o;
    o<<int(p.requestedMHz)<<" | "
     <<fmtSocConfigMv(int(p.railMv))<<" | "
     <<dMv<<" | "<<cost<<" | "
     <<fmt2Debug(p.performance)<<" | "
     <<fmt3Debug(perfPct)<<"% | "
     <<fmt0Debug(p.bandwidthMBs)<<" | "
     <<fmt2Debug(p.latencyNs);
    return o.str();
}
'''
m=must_replace(m,marker,helpers+'\n'+marker,'RAM debug helpers')

# Graph: Y opens diagnostics without changing recommendation/selection state.
old_graph=r'''if(g.stage==Stage::RamGraph){
            if(k&HidNpadButton_Left){moveRamTarget(-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){moveRamTarget(1);redraw=true;continue;}
            if((k&HidNpadButton_A)||(k&HidNpadButton_X)){g.stage=Stage::RamTargetExplanation;saveState();redraw=true;continue;}
        }'''
new_graph=r'''if(g.stage==Stage::RamGraph){
            if(k&HidNpadButton_Left){moveRamTarget(-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){moveRamTarget(1);redraw=true;continue;}
            if(k&HidNpadButton_Y){g_ramDebugPage=0;g.stage=Stage::RamDebug;saveState();redraw=true;continue;}
            if((k&HidNpadButton_A)||(k&HidNpadButton_X)){g.stage=Stage::RamTargetExplanation;saveState();redraw=true;continue;}
        }
        if(g.stage==Stage::RamDebug){
            const int pages=ramDebugPageCount();
            if(k&HidNpadButton_Left){g_ramDebugPage=std::max(0,g_ramDebugPage-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){g_ramDebugPage=std::min(pages-1,g_ramDebugPage+1);redraw=true;continue;}
            if((k&HidNpadButton_Y)||(k&HidNpadButton_B)){g.stage=Stage::RamGraph;saveState();redraw=true;continue;}
        }'''
m=must_replace(m,old_graph,new_graph,'RAM debug input')

# Add a visible hint to the normal RAM graph without altering the chart itself.
graph_case_start=m.find('case Stage::RamGraph:')
if graph_case_start<0: raise SystemExit('beta31 RAM graph case missing')
graph_case_end=m.find('gui::present();break;}',graph_case_start)
if graph_case_end<0: raise SystemExit('beta31 RAM graph end missing')
graph_body=m[graph_case_start:graph_case_end]
if 'Y : Debug data' not in graph_body:
    graph_body=graph_body.replace('print(11,"B : Exit");','print(11,"Y : Debug data");\n            print(12,"B : Exit");')
    m=m[:graph_case_start]+graph_body+m[graph_case_end:]

# Debug page is intentionally text-first and photographable. Eight rows per page keep
# the columns readable; Left/Right pages cover long 3400+ sweeps without truncation.
insert_before='        case Stage::RamTargetExplanation:{'
debug_page=r'''        case Stage::RamDebug:{
            const auto ids=ramDebugPointIndices();
            const int pages=ramDebugPageCount();
            g_ramDebugPage=std::clamp(g_ramDebugPage,0,pages-1);
            v.stageTitle="RAM Debug Data";v.instructionTitle="Photograph this page for curve analysis";v.instructionLine1="";v.instructionLine2="";v.hideValuesCard=true;v.fullWidthLayout=true;
            gui::begin(v);
            print(1,"MHz | SoC mV | dV | mV/100MHz | Raw Score | Perf % | BW | Lat ns");
            const int first=g_ramDebugPage*8;
            for(int r=0;r<8;++r){
                const int pos=first+r;
                if(pos>=int(ids.size()))break;
                print(2+r,ramDebugRow(pos));
            }
            print(10,"Page "+std::to_string(g_ramDebugPage+1)+" / "+std::to_string(pages)+"   Left / Right : change page");
            print(11,"Y / B : Back to RAM graph");
            gui::present();break;}
'''
m=must_replace(m,insert_before,debug_page+insert_before,'RAM debug page render')

p.write_text(m)

# Audit: diagnostic-only beta. Recommendation logic must remain beta30 unchanged.
main=Path('source/main_oc.cpp').read_text(); engine=Path('source/oc_engine.cpp').read_text()
checks={
 'beta31 version':'0.1.0-beta.31' in Path('Makefile').read_text(),
 'debug stage append':'RamDebug' in main,
 'graph Y debug':'HidNpadButton_Y' in main and 'Y : Debug data' in main,
 'debug raw score':'Raw Score' in main and 'fmt2Debug(p.performance)' in main,
 'debug precise performance':'fmt3Debug(perfPct)' in main,
 'debug electrical slope':'mV/100MHz' in main and 'dv/dMHz*100.0' in main,
 'debug benchmark data':'p.bandwidthMBs' in main and 'p.latencyNs' in main,
 'OC-only debug rows':'requestedMHz)>=1866' in main,
 'paged diagnostics':'ramDebugPageCount' in main and 'g_ramDebugPage*8' in main,
 'beta30 recommendation retained':'minTargetMHz=double(maxMHz)*0.90' in main and 'return maxIdx;' in main,
 'mandatory explanation retained':'Read the explanation before choosing your RAM target' in main,
 'target selection retained':'Choose RAM Target' in main,
 'benchmark score source retained':'ramPerformanceScore' in engine,
 'override cleanup retained':'Do not leave the benchmark RAM clock active' in main,
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta31 source audit failed: '+', '.join(bad))
