from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta32 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta32 function missing: {signature}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta32 opening brace missing: {signature}")
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
        raise SystemExit(f"beta32 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# -----------------------------------------------------------------------------
# Version.
# -----------------------------------------------------------------------------
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.31','APP_VERSION := 0.1.0-beta.32','version')
p.write_text(s)


# -----------------------------------------------------------------------------
# Persist every RAM benchmark raw metric in SweepPoint.
# -----------------------------------------------------------------------------
p=Path('source/oc_engine.hpp')
h=p.read_text()
h=must_replace(
    h,
    '    double bandwidthMBs = 0.0;      // RAM only\n',
    '''    double bandwidthMBs = 0.0;      // RAM legacy aggregate only\n    // Full RAM benchmark raw data. These are persisted so the final RAM\n    // performance index can be recomputed without throwing measurements away.\n    double ramCpuCopyMBs = 0.0;\n    double ramCpuReadMBs = 0.0;\n    double ramCpuWriteMBs = 0.0;\n    double ramGpuCopyMBs = 0.0;\n    double ramGpuReadMBs = 0.0;\n    double ramGpuWriteMBs = 0.0;\n    double ramL2LatencyNs = 0.0;\n    double ramLegacyScore = 0.0;\n''',
    'raw RAM metrics fields')
h=must_replace(
    h,
    '// RAM benchmark composite: rewards bandwidth and lower full-RAM latency.\ndouble ramPerformanceScore(double cpuCopy, double cpuRead, double cpuWrite,\n                           double gpuCopy, double gpuRead, double gpuWrite,\n                           double ramLatencyNs);\n',
    '''// Legacy single-run RAM score retained only for diagnostics/backward comparison.\ndouble ramPerformanceScore(double cpuCopy, double cpuRead, double cpuWrite,\n                           double gpuCopy, double gpuRead, double gpuWrite,\n                           double ramLatencyNs);\n\n// Rebuild the final RAM Performance Index from all eight measured dimensions.\n// Each dimension is normalized first; GPU and CPU bandwidth groups are geometric\n// means so raw MB/s magnitude cannot dominate the score. Lower latency is better.\nvoid recalculateRamPerformanceIndex(std::vector<SweepPoint>& points);\n''',
    'RAM composite declaration')
p.write_text(h)


# -----------------------------------------------------------------------------
# New cross-point RAM performance index.
# -----------------------------------------------------------------------------
p=Path('source/oc_engine.cpp')
e=p.read_text()
insert='const char* domainName(Domain d) {'
impl=r'''
void recalculateRamPerformanceIndex(std::vector<SweepPoint>& points) {
    std::vector<int> ids;
    for (int i=0;i<int(points.size());++i) {
        const auto& p=points[i];
        const bool raw = p.domain==Domain::Ram && p.stable && p.combinedStable &&
            p.ramCpuCopyMBs>0.0 && p.ramCpuReadMBs>0.0 && p.ramCpuWriteMBs>0.0 &&
            p.ramGpuCopyMBs>0.0 && p.ramGpuReadMBs>0.0 && p.ramGpuWriteMBs>0.0 &&
            p.ramL2LatencyNs>0.0 && p.latencyNs>0.0;
        if(raw) ids.push_back(i);
    }
    if(ids.empty()) return;

    // Best observed value of each independent metric is its dimensionless reference.
    // This avoids mixing MB/s and ns directly and makes the index portable across consoles.
    double cCopy=0,cRead=0,cWrite=0,gCopy=0,gRead=0,gWrite=0;
    double bestL2=std::numeric_limits<double>::infinity();
    double bestRam=std::numeric_limits<double>::infinity();
    for(int i:ids){
        const auto& p=points[i];
        cCopy=std::max(cCopy,p.ramCpuCopyMBs); cRead=std::max(cRead,p.ramCpuReadMBs); cWrite=std::max(cWrite,p.ramCpuWriteMBs);
        gCopy=std::max(gCopy,p.ramGpuCopyMBs); gRead=std::max(gRead,p.ramGpuReadMBs); gWrite=std::max(gWrite,p.ramGpuWriteMBs);
        bestL2=std::min(bestL2,p.ramL2LatencyNs); bestRam=std::min(bestRam,p.latencyNs);
    }

    auto ratio=[](double value,double ref){return std::clamp(value/std::max(1e-9,ref),1e-6,1.0);};
    auto invRatio=[](double best,double value){return std::clamp(best/std::max(1e-9,value),1e-6,1.0);};
    double bestComposite=0.0;
    for(int i:ids){
        auto& p=points[i];
        const double cpuGroup=std::cbrt(ratio(p.ramCpuCopyMBs,cCopy)*ratio(p.ramCpuReadMBs,cRead)*ratio(p.ramCpuWriteMBs,cWrite));
        const double gpuGroup=std::cbrt(ratio(p.ramGpuCopyMBs,gCopy)*ratio(p.ramGpuReadMBs,gRead)*ratio(p.ramGpuWriteMBs,gWrite));
        const double ramLat=invRatio(bestRam,p.latencyNs);
        const double l2Lat=invRatio(bestL2,p.ramL2LatencyNs);

        // Group-balanced weighted geometric mean:
        // 35% GPU bandwidth, 35% CPU bandwidth, 25% Full-RAM latency, 5% L2 latency.
        // All eight raw measurements contribute, but cache latency cannot overpower DRAM behavior.
        const double composite=std::exp(
            0.35*std::log(gpuGroup) +
            0.35*std::log(cpuGroup) +
            0.25*std::log(ramLat) +
            0.05*std::log(l2Lat));
        p.performance=composite;
        bestComposite=std::max(bestComposite,composite);
    }
    if(bestComposite<=0.0) return;
    for(int i:ids) points[i].performance=100.0*points[i].performance/bestComposite;
}

'''
e=must_replace(e,insert,impl+insert,'RAM composite implementation')
p.write_text(e)


# -----------------------------------------------------------------------------
# Extended measurements.csv, backward-compatible with beta31 and older rows.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp')
m=p.read_text()

new_save=r'''void savePoints() {
    ensureDir(APP_DIR);
    std::ofstream f(POINTS_FILE,std::ios::trunc); if(!f) return;
    auto wr=[&](const std::vector<oc::SweepPoint>& v){
        for(const auto&p:v){
            f<<int(p.domain)<<','<<p.requestedMHz<<','<<p.realMHz<<','<<p.railMv<<','<<p.auxMv<<','
             <<p.performance<<','<<p.latencyNs<<','<<p.bandwidthMBs<<','<<p.batteryPowerW<<','<<p.stable<<','<<p.combinedStable<<','
             <<p.ramCpuCopyMBs<<','<<p.ramCpuReadMBs<<','<<p.ramCpuWriteMBs<<','
             <<p.ramGpuCopyMBs<<','<<p.ramGpuReadMBs<<','<<p.ramGpuWriteMBs<<','
             <<p.ramL2LatencyNs<<','<<p.ramLegacyScore<<'\n';
        }
    };
    wr(ramPoints); wr(gpuPoints); wr(cpuPoints); f.flush(); fsdevCommitDevice("sdmc");
}'''
m=replace_function(m,'void savePoints()',new_save)

new_load=r'''void loadPoints() {
    std::ifstream f(POINTS_FILE); if(!f) return; std::string l;
    while(std::getline(f,l)) {
        std::stringstream ss(l);std::vector<std::string> c;std::string a;
        while(std::getline(ss,a,','))c.push_back(a);
        if(c.size()<11)continue;
        oc::SweepPoint p;
        p.domain=oc::Domain(std::atoi(c[0].c_str()));p.requestedMHz=std::strtoul(c[1].c_str(),nullptr,10);p.realMHz=std::atof(c[2].c_str());
        p.railMv=std::strtoul(c[3].c_str(),nullptr,10);p.auxMv=std::strtoul(c[4].c_str(),nullptr,10);p.performance=std::atof(c[5].c_str());
        p.latencyNs=std::atof(c[6].c_str());p.bandwidthMBs=std::atof(c[7].c_str());p.batteryPowerW=std::atof(c[8].c_str());
        p.stable=std::atoi(c[9].c_str())!=0;p.combinedStable=std::atoi(c[10].c_str())!=0;
        // Optional beta32 columns. Older measurement files remain readable and can
        // be upgraded by re-running only the final RAM benchmark sweep.
        if(c.size()>11)p.ramCpuCopyMBs=std::atof(c[11].c_str());
        if(c.size()>12)p.ramCpuReadMBs=std::atof(c[12].c_str());
        if(c.size()>13)p.ramCpuWriteMBs=std::atof(c[13].c_str());
        if(c.size()>14)p.ramGpuCopyMBs=std::atof(c[14].c_str());
        if(c.size()>15)p.ramGpuReadMBs=std::atof(c[15].c_str());
        if(c.size()>16)p.ramGpuWriteMBs=std::atof(c[16].c_str());
        if(c.size()>17)p.ramL2LatencyNs=std::atof(c[17].c_str());
        if(c.size()>18)p.ramLegacyScore=std::atof(c[18].c_str());
        auto& v=p.domain==oc::Domain::Ram?ramPoints:(p.domain==oc::Domain::Gpu?gpuPoints:cpuPoints);v.push_back(p);
    }
    // A beta32 file can always regenerate its display index from persisted raw data.
    oc::recalculateRamPerformanceIndex(ramPoints);
}'''
m=replace_function(m,'void loadPoints()',new_load)

# Final RAM benchmark: store every raw Membench metric, not a collapsed subset.
new_bench=r'''bool runFinalRamBenchmarkPoint(int index){
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
    clearOverrides();
    if(!b.ok){modalError("Final RAM benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" This point was not measured; retry the benchmark sweep.");return false;}
    p.realMHz=b.telemetry.realRamMHz;
    p.ramLegacyScore=b.score;
    p.ramCpuCopyMBs=b.cpuCopy;p.ramCpuReadMBs=b.cpuRead;p.ramCpuWriteMBs=b.cpuWrite;
    p.ramGpuCopyMBs=b.gpuCopy;p.ramGpuReadMBs=b.gpuRead;p.ramGpuWriteMBs=b.gpuWrite;
    p.ramL2LatencyNs=b.l2Ns;p.latencyNs=b.ramNs;
    p.bandwidthMBs=b.cpuRead+b.gpuRead; // legacy display field only
    p.batteryPowerW=b.telemetry.batteryPowerW;
    p.powerReliable=false;
    p.context="Final RAM benchmark / full raw Membench data / tuned SoC / validated DVB-HP-timings";
    savePoints();
    return true;
}'''
m=replace_function(m,'bool runFinalRamBenchmarkPoint(int index)',new_bench)

new_finish=r'''void finishFinalRamBenchmarkSweep(){
    clearOverrides();
    svcSleepThread(150'000'000);
    // Rebuild performance only after every point has all eight comparable raw metrics.
    oc::recalculateRamPerformanceIndex(ramPoints);
    savePoints();
    refreshRamSuggestedTarget();
    if(g.ramRecommendedMHz<=0){modalError("Could not determine a high-performance RAM target from the final benchmark curve.");return;}
    g.ramTargetMHz=g.ramRecommendedMHz;
    g.socTableMHz=socTableForRamMHz(g.ramRecommendedMHz);
    g.socGoodMv=0;
    for(const auto& p:ramPoints)if(int(p.requestedMHz)==g.ramRecommendedMHz){g.socGoodMv=int(p.railMv);break;}
    g.socCandidateMv=nextLowerSocMv(g.socGoodMv);
    g.stage=Stage::RamGraph;saveState();
}'''
m=replace_function(m,'void finishFinalRamBenchmarkSweep()',new_finish)

# -----------------------------------------------------------------------------
# Beta32 debug: all eight raw metrics + electrical slope + new index.
# Two lines per frequency, four points per page, readable from a photo.
# X lets an existing beta31 installation re-run only the final benchmark sweep.
# -----------------------------------------------------------------------------
new_debug_count=r'''int ramDebugPageCount(){
    const int n=int(ramDebugPointIndices().size());
    return std::max(1,(n+3)/4);
}'''
m=replace_function(m,'int ramDebugPageCount()',new_debug_count)

new_debug_row=r'''std::string ramDebugRow(int absolutePos){
    const auto ids=ramDebugPointIndices();
    if(absolutePos<0 || absolutePos>=int(ids.size())) return {};
    const auto& p=ramPoints[ids[absolutePos]];
    std::string cost="-";
    if(absolutePos>0){
        const auto& prev=ramPoints[ids[absolutePos-1]];
        const double dMHz=double(p.requestedMHz)-double(prev.requestedMHz);
        const double dv=double(p.railMv)-double(prev.railMv);
        if(std::abs(dMHz)>0.001) cost=fmt2Debug(dv/dMHz*100.0);
    }
    std::ostringstream o;
    o<<int(p.requestedMHz)<<" MHz | SoC "<<fmtSocConfigMv(int(p.railMv))
     <<" | dV/100 "<<cost<<" | Index "<<fmt3Debug(p.performance)<<"%";
    return o.str();
}'''
m=replace_function(m,'std::string ramDebugRow(int absolutePos)',new_debug_row)

# Extra line helper inserted before analyzeRam.
marker='void analyzeRam(){'
extra=r'''
std::string ramDebugMetricsRow(int absolutePos){
    const auto ids=ramDebugPointIndices();
    if(absolutePos<0 || absolutePos>=int(ids.size())) return {};
    const auto& p=ramPoints[ids[absolutePos]];
    std::ostringstream o;
    o<<"GPU "<<fmt0Debug(p.ramGpuCopyMBs)<<'/'<<fmt0Debug(p.ramGpuReadMBs)<<'/'<<fmt0Debug(p.ramGpuWriteMBs)
     <<" | CPU "<<fmt0Debug(p.ramCpuCopyMBs)<<'/'<<fmt0Debug(p.ramCpuReadMBs)<<'/'<<fmt0Debug(p.ramCpuWriteMBs)
     <<" | L2 "<<fmt2Debug(p.ramL2LatencyNs)<<" ns | RAM "<<fmt2Debug(p.latencyNs)<<" ns"
     <<" | legacy "<<fmt2Debug(p.ramLegacyScore);
    return o.str();
}

bool ramRawMetricsComplete(){
    const auto ids=ramDebugPointIndices();
    if(ids.empty())return false;
    for(int i:ids){const auto&p=ramPoints[i];
        if(p.ramCpuCopyMBs<=0||p.ramCpuReadMBs<=0||p.ramCpuWriteMBs<=0||p.ramGpuCopyMBs<=0||p.ramGpuReadMBs<=0||p.ramGpuWriteMBs<=0||p.ramL2LatencyNs<=0||p.latencyNs<=0)return false;
    }
    return true;
}
'''
m=must_replace(m,marker,extra+'\n'+marker,'beta32 debug helpers')

# Debug input: X returns to the final benchmark stage so beta31 data can be upgraded.
old_debug_input=r'''if(g.stage==Stage::RamDebug){
            const int pages=ramDebugPageCount();
            if(k&HidNpadButton_Left){g_ramDebugPage=std::max(0,g_ramDebugPage-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){g_ramDebugPage=std::min(pages-1,g_ramDebugPage+1);redraw=true;continue;}
            if((k&HidNpadButton_Y)||(k&HidNpadButton_B)){g.stage=Stage::RamGraph;saveState();redraw=true;continue;}
        }'''
new_debug_input=r'''if(g.stage==Stage::RamDebug){
            const int pages=ramDebugPageCount();
            if(k&HidNpadButton_Left){g_ramDebugPage=std::max(0,g_ramDebugPage-1);redraw=true;continue;}
            if(k&HidNpadButton_Right){g_ramDebugPage=std::min(pages-1,g_ramDebugPage+1);redraw=true;continue;}
            if(k&HidNpadButton_X){g.ramBenchmarkIndex=0;g.stage=Stage::RamBenchmark;saveState();redraw=true;continue;}
            if((k&HidNpadButton_Y)||(k&HidNpadButton_B)){g.stage=Stage::RamGraph;saveState();redraw=true;continue;}
        }'''
m=must_replace(m,old_debug_input,new_debug_input,'beta32 debug rebenchmark input')

# Replace photographable debug page.
start=m.find('        case Stage::RamDebug:{')
if start<0: raise SystemExit('beta32 RAM debug case missing')
brace=m.find('{',start);depth=0;end=None
for i in range(brace,len(m)):
    if m[i]=='{':depth+=1
    elif m[i]=='}':
        depth-=1
        if depth==0:
            end=i+1;break
if end is None: raise SystemExit('beta32 RAM debug case unbalanced')
new_debug_page=r'''        case Stage::RamDebug:{
            const auto ids=ramDebugPointIndices();
            const int pages=ramDebugPageCount();
            g_ramDebugPage=std::clamp(g_ramDebugPage,0,pages-1);
            v.stageTitle="RAM Debug Data";v.instructionTitle="Full Membench raw data + composite index";v.instructionLine1="";v.instructionLine2="";v.hideValuesCard=true;v.fullWidthLayout=true;
            gui::begin(v);
            print(1,"Index uses GPU 35% + CPU 35% + Full RAM latency 25% + L2 latency 5%.");
            const int first=g_ramDebugPage*4;
            for(int r=0;r<4;++r){
                const int pos=first+r;if(pos>=int(ids.size()))break;
                print(2+r*2,ramDebugRow(pos));
                print(3+r*2,ramDebugMetricsRow(pos));
            }
            print(10,"Page "+std::to_string(g_ramDebugPage+1)+" / "+std::to_string(pages)+"   Left / Right : change page");
            print(11,ramRawMetricsComplete()?"X : Re-run final benchmark   Y / B : Back":"RAW DATA MISSING - X : Re-run final benchmark   Y / B : Back");
            gui::present();break;}'''
m=m[:start]+new_debug_page+m[end:]

p.write_text(m)


# -----------------------------------------------------------------------------
# Build-time audit.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text();hdr=Path('source/oc_engine.hpp').read_text();eng=Path('source/oc_engine.cpp').read_text();stress=Path('source/stress_tests.cpp').read_text()
checks={
 'beta32 version':'0.1.0-beta.32' in Path('Makefile').read_text(),
 'all six bandwidth fields':all(x in hdr for x in ['ramCpuCopyMBs','ramCpuReadMBs','ramCpuWriteMBs','ramGpuCopyMBs','ramGpuReadMBs','ramGpuWriteMBs']),
 'both latency fields':'ramL2LatencyNs' in hdr and 'latencyNs' in hdr,
 'legacy score preserved':'ramLegacyScore' in hdr and 'p.ramLegacyScore=b.score' in main,
 'full raw capture':'p.ramCpuCopyMBs=b.cpuCopy' in main and 'p.ramGpuWriteMBs=b.gpuWrite' in main and 'p.ramL2LatencyNs=b.l2Ns' in main,
 'csv optional compatibility':'if(c.size()>18)p.ramLegacyScore' in main,
 'cross point recompute':'recalculateRamPerformanceIndex(ramPoints)' in main,
 'normalized groups':'std::cbrt' in eng and 'bestRam' in eng and 'bestL2' in eng,
 'all eight weighted':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng and '0.25*std::log(ramLat)' in eng and '0.05*std::log(l2Lat)' in eng,
 'debug all raw':'GPU ' in main and 'CPU ' in main and 'L2 ' in main and 'RAM ' in main,
 'debug electrical slope':'dV/100' in main,
 'debug rebenchmark':'RAW DATA MISSING - X : Re-run final benchmark' in main,
 'recommendation logic retained':'minTargetMHz=double(maxMHz)*0.90' in main,
 'mandatory explanation retained':'Read the explanation before choosing your RAM target' in main,
 'override cleanup retained':'Do not leave the benchmark RAM clock active' in main,
 'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for name,ok in checks.items():print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad:raise SystemExit('Beta32 source audit failed: '+', '.join(bad))
