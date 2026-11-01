from pathlib import Path


def must_replace(s: str, old: str, new: str, name: str, count: int = 1) -> str:
    if old not in s:
        raise SystemExit(f"beta16 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src: str, signature: str, replacement: str) -> str:
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta16 function missing: {signature}")
    brace = src.find("{", pos)
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == "{": depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"beta16 unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# Version
p=Path("Makefile"); s=p.read_text(); s=must_replace(s,"APP_VERSION := 0.1.0-beta.15","APP_VERSION := 0.1.0-beta.16","version"); p.write_text(s)

# Use one coherent HOC RAM step mode for capability discovery: 66 MHz.
# Keep stock 1331 as the initial baseline, then use clocks actually available in HOC 66 MHz mode.
p=Path("source/oc_profiles.hpp"); s=p.read_text()
start=s.index("static constexpr std::uint32_t RAM_STEPS_MHZ[] = {")
end=s.index("};",start)+2
new_table='''static constexpr std::uint32_t RAM_STEPS_MHZ[] = {
    1331, 1600, 1666, 1733, 1800, 1866, 1933, 2000, 2066, 2133,
    2200, 2266, 2333, 2400, 2466, 2533, 2600, 2666, 2733, 2800,
    2866, 2933, 3000, 3066, 3133, 3200, 3266, 3333, 3400
};'''
s=s[:start]+new_table+s[end:]; p.write_text(s)

# Add Step Mode to the config reader/writer model.
p=Path("source/oc_config.hpp"); h=p.read_text()
h=must_replace(h,"    std::uint32_t vdd2Uv = 0;\n    std::uint32_t vddqUv = 0;","    std::uint32_t vdd2Uv = 0;\n    int stepMode = 0;\n    std::uint32_t vddqUv = 0;","RamConfig step mode")
p.write_text(h)

p=Path("source/oc_config.cpp"); c=p.read_text()
c=must_replace(c,"    int uncapped, hp, memVolt, ramMax, vddq, dvb, socVmax, timing0;","    int uncapped, hp, memVolt, stepMode, ramMax, vddq, dvb, socVmax, timing0;","Idx step mode")
c=must_replace(c,"constexpr Idx I251 = {34,5,35,36,39,40,41,42,43,72,73,74,75,76,77,78,83,84,85,86,87,138,24};","constexpr Idx I251 = {34,5,35,36,38,39,40,41,42,43,72,73,74,75,76,77,78,83,84,85,86,87,138,24};","I251 step index")
c=must_replace(c,"constexpr Idx ICUR = {39,5,40,41,44,45,46,47,48,77,78,79,80,81,82,83,88,89,90,91,92,144,25};","constexpr Idx ICUR = {39,5,40,41,43,44,45,46,47,48,77,78,79,80,81,82,83,88,89,90,91,92,144,25};","ICUR step index")
c=must_replace(c,"out.ok=true;out.hpMode=v[i->hp]!=0;out.ramMaxMHz=std::uint32_t(v[i->ramMax]/1000ULL);out.vdd2Uv=std::uint32_t(v[i->memVolt]);out.vddqUv=std::uint32_t(v[i->vddq]);","out.ok=true;out.hpMode=v[i->hp]!=0;out.ramMaxMHz=std::uint32_t(v[i->ramMax]/1000ULL);out.vdd2Uv=std::uint32_t(v[i->memVolt]);out.stepMode=int(v[i->stepMode]);out.vddqUv=std::uint32_t(v[i->vddq]);","read step mode")
c=must_replace(c,"v[i->uncapped]=1;v[i->hp]=hpMode?1:0;v[i->memVolt]=u64(vdd2Mv)*1000ULL;v[i->ramMax]=u64(ramMaxMHz)*1000ULL;","v[i->uncapped]=1;v[i->hp]=hpMode?1:0;v[i->memVolt]=u64(vdd2Mv)*1000ULL;v[i->stepMode]=0;v[i->ramMax]=u64(ramMaxMHz)*1000ULL;","set 66MHz step mode")
p.write_text(c)

# Main guard/UI + robust sweep error handling.
p=Path("source/main_oc.cpp"); m=p.read_text()
needle='''row("RAM","Max Clock","3400 MHz",have?std::to_string(rc.ramMaxMHz)+" MHz":"unavailable",have&&rc.ramMaxMHz!=3400);'''
replacement=needle+'\n                row("RAM","Step Mode","66 MHz",have?(rc.stepMode==0?"66 MHz":rc.stepMode==1?"100 MHz":rc.stepMode==2?"JEDEC":rc.stepMode==3?"133 MHz":rc.stepMode==4?"33 MHz":"unknown"):"unavailable",have&&rc.stepMode!=0);'
m=must_replace(m,needle,replacement,"preparation step row")
needle='''    if(rc.ramMaxMHz!=expectedMax) add("RAM Max "+std::to_string(rc.ramMaxMHz)+" != "+std::to_string(expectedMax)+" MHz");'''
replacement=needle+'\n    if(rc.stepMode!=0) add("RAM Step Mode is not 66 MHz");'
m=must_replace(m,needle,replacement,"guard step mode")
new_func=r'''void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This is not counted as a RAM stability failure; verify the HOC Step Mode/config and retry.");
        return;
    }
    if(!runStress(stress::Kind::Ram,45,"RAM Clock Stability - "+std::to_string(freq)+" MHz","Testing RAM: "+std::to_string(freq)+" MHz")){
        finishRamSweep();return;
    }
    auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");
    if(!b.ok){modalError("Memory Benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" The RAM point is not marked unstable; retry the benchmark.");return;}
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB5 / 66MHz Step Mode";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
m=replace_function(m,"void runRamCandidate()",new_func)
m=m.replace("Search controls: HP OFF  |  DVB Shift 5  |  SoC VMAX 1150 mV ceiling","Search controls: Step Mode 66 MHz  |  HP OFF  |  DVB 5  |  SoC VMAX 1150 mV")
p.write_text(m)

# Audit all important invariants.
main=Path("source/main_oc.cpp").read_text(); cfg=Path("source/oc_config.cpp").read_text(); prof=Path("source/oc_profiles.hpp").read_text(); hdr=Path("source/oc_config.hpp").read_text()
arr=prof[prof.index("static constexpr std::uint32_t RAM_STEPS_MHZ[] = {"):prof.index("};",prof.index("static constexpr std::uint32_t RAM_STEPS_MHZ[] = {"))+2]
checks={
 "beta16 version":"0.1.0-beta.16" in Path("Makefile").read_text(),
 "step mode field":"stepMode" in hdr and "int uncapped, hp, memVolt, stepMode" in cfg,
 "step mode index current":"39,5,40,41,43,44,45,46,47,48" in cfg,
 "step mode forced 66":"v[i->stepMode]=0" in cfg,
 "guard checks 66":"RAM Step Mode is not 66 MHz" in main,
 "66MHz sweep contains 2200":"2066, 2133,\n    2200, 2266" in arr,
 "bad mixed 2300 removed":", 2300," not in arr,
 "override failure not false fail":"This is not counted as a RAM stability failure" in main,
 "benchmark failure retry":"RAM point is not marked unstable" in main,
 "visible benchmark retained":"ocbench::runRam(\"RAM \"+std::to_string(freq)+\" MHz\")" in main,
 "GPU retained":"GPU + RAM Integration" in main,
 "CPU retained":"CPU + RAM Final Validation" in main,
}
for name,ok in checks.items(): print(("PASS " if ok else "FAIL ")+name)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit("Beta16 source audit failed: "+", ".join(bad))
