from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta17 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta17 function missing: {signature}")
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
        raise SystemExit(f"beta17 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]

# Version
p=Path('Makefile'); s=p.read_text(); s=must_replace(s,'APP_VERSION := 0.1.0-beta.16','APP_VERSION := 0.1.0-beta.17','version'); p.write_text(s)

# Expose GPU config-selected tuning values for the side card.
p=Path('source/oc_config.hpp'); h=p.read_text()
marker='''bool getGpuPoint(std::uint32_t mhz, int& mv, std::string& error);\nbool setGpuVmin(int mv, std::string& error);'''
repl='''bool getGpuPoint(std::uint32_t mhz, int& mv, std::string& error);\nbool getGpuTuning(int& uvTable, int& vminMv, int& vmaxMv, std::string& error);\nbool setGpuVmin(int mv, std::string& error);'''
h=must_replace(h,marker,repl,'gpu tuning declaration'); p.write_text(h)

p=Path('source/oc_config.cpp'); c=p.read_text()
marker='''bool getGpuPoint(std::uint32_t mhz,int&mv,std::string& error){std::array<u64,256>v{};bool o=false;const Idx*i=nullptr;if(!read(v,o,i,error))return false;int p=findFreq(GPU_FREQS,i->gpuVoltCount,mhz);if(p<0){error="Unsupported GPU frequency.";return false;}mv=int(v[i->gpuVolt0+p]);return true;}\nbool setGpuVmin'''
repl='''bool getGpuPoint(std::uint32_t mhz,int&mv,std::string& error){std::array<u64,256>v{};bool o=false;const Idx*i=nullptr;if(!read(v,o,i,error))return false;int p=findFreq(GPU_FREQS,i->gpuVoltCount,mhz);if(p<0){error="Unsupported GPU frequency.";return false;}mv=int(v[i->gpuVolt0+p]);return true;}\nbool getGpuTuning(int&uvTable,int&vminMv,int&vmaxMv,std::string& error){std::array<u64,256>v{};bool o=false;const Idx*i=nullptr;if(!read(v,o,i,error))return false;uvTable=int(v[i->gpuUv]);vminMv=int(v[i->gpuVmin]);vmaxMv=int(v[i->gpuVmax]);return true;}\nbool setGpuVmin'''
c=must_replace(c,marker,repl,'gpu tuning implementation'); p.write_text(c)

p=Path('source/main_oc.cpp'); m=p.read_text()

# New official RAM prep reserve: DVB 8, with the first optimization candidate at 7.
m=m.replace('int dvbGood = 5;\n    int dvbCandidate = 4;', 'int dvbGood = 8;\n    int dvbCandidate = 7;')
m=m.replace('int expectedDvb=5;', 'int expectedDvb=8;')
m=m.replace('g.dvbGood=5;g.dvbCandidate=4;', 'g.dvbGood=8;g.dvbCandidate=7;')
m=m.replace('d.dvbShift=5;', 'd.dvbShift=8;')
m=m.replace(',5,1150,t,e)', ',8,1150,t,e)')
m=m.replace('DVB Shift 5', 'DVB Shift 8')
m=m.replace('DVB 5  |', 'DVB 8  |')
m=m.replace('DVB5 / 66MHz Step Mode', 'DVB8 / 66MHz Step Mode')
m=m.replace('Common / HP off / DVB5', 'Common / HP off / DVB8')

# The RAM Max Clock stability phase is one full minute.
start=m.find('void runRamCandidate()')
if start < 0: raise SystemExit('runRamCandidate missing')
end=m.find('\n}', start)+2
body=m[start:end]
if 'runStress(stress::Kind::Ram,45,' not in body:
    raise SystemExit('beta17 45s RAM marker missing')
body=body.replace('runStress(stress::Kind::Ram,45,','runStress(stress::Kind::Ram,60,',1)
m=m[:start]+body+m[end:]

# HOC applies an override asynchronously. Do not sample once at 500 ms and declare a PLL failure.
# Poll for up to five seconds and only judge the RAM override/real clock domain.
m=replace_function(m,'bool setRamOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err)',r'''bool setRamOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err) {
    Result rc=hocmonSetOverride(HocMonModule_CPU,cpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_GPU,gpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_MEM,ram);
    if(R_FAILED(rc)){char b[80];std::snprintf(b,sizeof(b),"Temporary RAM override failed: 0x%08X",rc);err=b;return false;}
    HocMonClocks c{}; bool got=false;
    for(int i=0;i<50;++i){
        svcSleepThread(100'000'000);
        rc=hocmonGetTelemetry(&c);
        if(R_FAILED(rc)) continue;
        got=true;
        if(clockMatch(c.overrideHz[2],ram) && clockMatch(c.realHz[2],ram)){g_active=c;return true;}
    }
    if(!got){err="Could not read RAM override telemetry while waiting for the clock to settle.";return false;}
    char b[220];
    std::snprintf(b,sizeof(b),"Requested RAM %u.%03u MHz did not settle. Override %u.%03u MHz, Real %u.%03u MHz.",
        ram/1000000U,(ram%1000000U)/1000U,c.overrideHz[2]/1000000U,(c.overrideHz[2]%1000000U)/1000U,c.realHz[2]/1000000U,(c.realHz[2]%1000000U)/1000U);
    err=b; return false;
}''')

# Side card policy: CONFIG-selected values only. No live clock/voltage telemetry for stored HOC values.
setpos=m.find('    auto setValue=[&](int i,const char* label,const std::string& value)')
printpos=m.find('    auto print=[&](int row,const std::string&s)', setpos)
if setpos < 0 or printpos < 0: raise SystemExit('render side-card block missing')
newblock=r'''    auto setValue=[&](int i,const char* label,const std::string& value){v.values[i]={label,value,false};};
    if(g.stage>=Stage::RamPreparation && g.stage<=Stage::RamFinalGraph){
        occonfig::RamConfig rc{};std::string ce;
        if(occonfig::getRamConfig(rc,ce)){
            v.haveActiveValues=true;
            setValue(0,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
            setValue(1,"VDD2",fmtMvUv(int(rc.vdd2Uv)));
            setValue(2,"VDDQ",fmtMvUv(int(rc.vddqUv)));
            int sf=1866;
            if(g.stage==Stage::RamSweep && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex) sf=nearestSocFreq(std::max(1866,int(oc::RAM_STEPS_MHZ[g.ramSearchIndex])));
            else if(g.ramRecommendedMHz>0) sf=nearestSocFreq(std::max(1866,g.ramRecommendedMHz));
            int sv=0;std::string se;
            setValue(3,"SoC",occonfig::getSocPoint(sf,sv,se)&&sv>0?fmtSocConfigMv(sv):fmtMvUv(int(g_active.socVoltageUv)));
            setValue(4,"DVB Shift",std::to_string(rc.dvbShift));
        }
    }else if(g.stage>=Stage::GpuPreparation && g.stage<=Stage::GpuRamCombined){
        int uv=0,vmin=0,vmax=0;std::string ge;occonfig::RamConfig rc{};std::string re;
        if(occonfig::getGpuTuning(uv,vmin,vmax,ge) && occonfig::getRamConfig(rc,re)){
            v.haveActiveValues=true;
            int gf=(g.stage==Stage::GpuTune)?GPU_FREQS[std::clamp(g.gpuIndex,0,int(sizeof(GPU_FREQS)/sizeof(GPU_FREQS[0]))-1)]:std::max(768,g.gpuRecommendedMHz);
            int gmv=0;std::string pe;
            setValue(0,"GPU UV Table",std::to_string(uv));
            setValue(1,"GPU Point",occonfig::getGpuPoint(gf,gmv,pe)?std::to_string(gmv)+" mV":"unavailable");
            setValue(2,"GPU VMIN",std::to_string(vmin)+" mV");
            setValue(3,"GPU VMAX",std::to_string(vmax)+" mV");
            setValue(4,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
        }
    }else if(g.stage>=Stage::CpuPreparation && g.stage<=Stage::CpuRamCombined){
        int low=0,high=0,tb=0,lv=0,hv=0,vmax=0;std::uint32_t cm=0;std::string ce;
        if(occonfig::getCpuTuning(low,high,tb,lv,hv,vmax,cm,ce)){
            v.haveActiveValues=true;
            setValue(0,"CPU Max Clock",std::to_string(cm)+" MHz");
            setValue(1,"Low UV",std::to_string(low));
            setValue(2,"High UV",std::to_string(high));
            setValue(3,"Low VMIN",std::to_string(lv)+" mV");
            setValue(4,"High VMIN",std::to_string(hv)+" mV");
        }
    }
'''
m=m[:setpos]+newblock+m[printpos:]

p.write_text(m)

# Audit the requested beta17 invariants before compiling.
main=Path('source/main_oc.cpp').read_text(); cfg=Path('source/oc_config.cpp').read_text(); hdr=Path('source/oc_config.hpp').read_text()
checks={
 'beta17 version':'0.1.0-beta.17' in Path('Makefile').read_text(),
 'DVB state starts 8':'int dvbGood = 8' in main and 'int dvbCandidate = 7' in main,
 'DVB guard expects 8':'int expectedDvb=8' in main,
 'DVB prep text 8':('DVB Shift 8' in main or 'DVB 8  |' in main),
 'no prep DVB5 assignments':'d.dvbShift=5;' not in main and 'g.dvbGood=5;g.dvbCandidate=4;' not in main,
 'RAM stability 60s':'runStress(stress::Kind::Ram,60,"RAM Clock Stability - "' in main,
 'RAM settle polling':"for(int i=0;i<50;++i)" in main and "Override %u.%03u MHz" in main,
 'RAM only verification':'clockMatch(c.overrideHz[2],ram)' in main and 'clockMatch(c.realHz[2],ram)' in main,
 'config side cards':'setValue(0,"RAM Max Clock"' in main and 'setValue(0,"CPU Max Clock"' in main and 'setValue(0,"GPU UV Table"' in main,
 'GPU config getter':'getGpuTuning' in hdr and 'bool getGpuTuning' in cfg,
 'exact VDD formatting':'fmtMvUv(int(rc.vdd2Uv))' in main and 'fmtMvUv(int(rc.vddqUv))' in main,
 'visible benchmark retained':'RAM Memory Benchmark' in Path('source/oc_bench.cpp').read_text(),
 'GPU flow retained':'GPU + RAM Integration' in main,
 'CPU flow retained':'CPU + RAM Final Validation' in main,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta17 source audit failed: '+', '.join(bad))
