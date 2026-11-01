from pathlib import Path


def replace_function(src: str, signature: str, replacement: str) -> str:
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"Function marker missing: {signature}")
    brace = src.find("{", pos)
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"Unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


def must_replace(s: str, old: str, new: str, name: str, count: int = 1) -> str:
    if old not in s:
        raise SystemExit(f"beta14 marker missing: {name}")
    return s.replace(old, new, count)


# Version
p = Path("Makefile")
s = p.read_text()
s = must_replace(s, "APP_VERSION := 0.1.0-beta.13", "APP_VERSION := 0.1.0-beta.14", "version")
p.write_text(s)

p = Path("source/main_oc.cpp")
s = p.read_text()

# HOC SoC config values are integer labels for 12.5 mV regulator steps.
# Preserve the visible .5 step (637 -> 637.5, 662 -> 662.5, ...).
fmt_marker = 'std::string fmt1(double v) { char b[48]; std::snprintf(b,sizeof(b),"%.1f",v); return b; }\n'
fmt_add = '''std::string fmtSocConfigMv(int mv) {\n    std::ostringstream o;\n    if ((mv % 25 + 25) % 25 == 12) o << mv << ".5 mV";\n    else o << mv << " mV";\n    return o.str();\n}\n'''
if "fmtSocConfigMv" not in s:
    s = must_replace(s, fmt_marker, fmt_marker + fmt_add, "SoC config formatter")

# Preparation/runtime guard: compare the CONFIG-selected HOC values against the exact
# values required by the current RAM stage. Do not compare live voltage/clock telemetry.
s = replace_function(
    s,
    "bool guardRamConfig(const char* context)",
    r'''bool guardRamConfig(const char* context){
    const auto* p=profile(); if(!p) return false;
    occonfig::RamConfig rc{}; std::string e;
    if(!occonfig::getRamConfig(rc,e)){modalError(std::string("Could not read HOC config before ")+context+": "+e);return false;}

    std::uint32_t expectedMax=3400;
    std::uint32_t expectedVdd2=u32(p->vdd2Mv)*1000U;
    std::uint32_t expectedVddq=u32(p->vddqMv)*1000U;
    int expectedDvb=5;
    bool expectedHp=false;
    const std::uint32_t* expectedT=p->common.t;

    if(g.stage==Stage::RamDvb){expectedDvb=g.dvbApplied?g.dvbCandidate:g.dvbGood;}
    if(g.stage==Stage::RamHpTest){expectedDvb=g.dvbGood;expectedHp=true;}
    if(g.stage==Stage::RamStTest){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=p->st.t;}
    if(g.stage==Stage::RamSoc){expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;}
    if(g.stage==Stage::RamVdd2){expectedMax=u32(g.ramRecommendedMHz);expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;expectedVdd2=u32(g.vdd2Applied?g.vdd2CandidateUv:g.vdd2GoodUv);}
    if(g.stage==Stage::RamVddq){expectedMax=u32(g.ramRecommendedMHz);expectedDvb=g.dvbGood;expectedHp=g.ramHpMode!=0;expectedT=g.ramTimingMode?p->st.t:p->common.t;expectedVdd2=u32(g.vdd2GoodUv);expectedVddq=u32(g.vddqApplied?g.vddqCandidateMv:g.vddqGoodMv)*1000U;}

    std::vector<std::string> mismatch;
    auto add=[&](const std::string& x){mismatch.push_back(x);};
    if(rc.ramMaxMHz!=expectedMax) add("RAM Max "+std::to_string(rc.ramMaxMHz)+" != "+std::to_string(expectedMax)+" MHz");
    if(rc.vdd2Uv!=expectedVdd2) add("VDD2 "+fmtMvUv(int(rc.vdd2Uv))+" != "+fmtMvUv(int(expectedVdd2)));
    if(rc.vddqUv!=expectedVddq) add("VDDQ "+fmtMvUv(int(rc.vddqUv))+" != "+fmtMvUv(int(expectedVddq)));
    if(rc.dvbShift!=expectedDvb) add("DVB "+std::to_string(rc.dvbShift)+" != "+std::to_string(expectedDvb));
    if(rc.hpMode!=expectedHp) add(std::string("HP ")+(rc.hpMode?"ON":"OFF")+" != "+(expectedHp?"ON":"OFF"));
    if(rc.socVmaxMv!=1150) add("SoC VMAX "+std::to_string(rc.socVmaxMv)+" != 1150 mV");
    for(int i=0;i<8;++i) if(rc.timings[i]!=expectedT[i]){add("RAM timing t"+std::to_string(i+1)+" does not match");break;}

    if(g.stage==Stage::RamSoc && g.socApplied){
        int selected=0;
        if(!occonfig::getSocPoint(g.socTableMHz,selected,e)) add("SoC table point unreadable");
        else if(selected!=g.socCandidateMv) add("SoC point "+fmtSocConfigMv(selected)+" != "+fmtSocConfigMv(g.socCandidateMv));
    }

    if(!mismatch.empty()){
        modalError(std::string("HOC config mismatch before ")+context+": "+mismatch.front()+". Match the Wizard SET values and retry.");
        return false;
    }
    return true;
}'''
)

# RAM-only override validation must only care that the requested RAM override and RAM
# real clock are active. CPU/GPU may idle/downclock and must never block RAM tuning.
s = replace_function(
    s,
    "bool setRamOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err)",
    r'''bool setRamOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err) {
    Result rc=hocmonSetOverride(HocMonModule_CPU,cpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_GPU,gpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_MEM,ram);
    if(R_FAILED(rc)){char b[64];std::snprintf(b,sizeof(b),"Temporary RAM override failed: 0x%08X",rc);err=b;return false;}
    svcSleepThread(500'000'000);
    HocMonClocks c{}; rc=hocmonGetTelemetry(&c); if(R_FAILED(rc)){err="Could not verify RAM override.";return false;}
    if(!clockMatch(c.overrideHz[2],ram)||!clockMatch(c.realHz[2],ram)){
        err="Requested RAM clock is not active. This candidate may be capped or experiencing a PLL drop.";return false;
    }
    g_active=c; return true;
}'''
)

# Synchronize the starting voltage state from the selected CONFIG before the first sweep.
old_auto = '''void runRamSweepAutomatic(){\n    while(g.stage==Stage::RamSweep && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex){'''
new_auto = '''void runRamSweepAutomatic(){\n    occonfig::RamConfig rc{};std::string ce;\n    if(!occonfig::getRamConfig(rc,ce)){modalError("Could not read HOC config before RAM Max Clock Search: "+ce);return;}\n    g.vdd2GoodUv=int(rc.vdd2Uv);g.vdd2CandidateUv=std::max(VDD2_MIN_UV,g.vdd2GoodUv-12500);\n    g.vddqGoodMv=int(rc.vddqUv/1000U);g.vddqCandidateMv=std::max(VDDQ_MIN_MV,g.vddqGoodMv-10);\n    while(g.stage==Stage::RamSweep && g.ramSearchIndex>=0 && g.ramSearchIndex<=g.ramSearchEndIndex){'''
s = must_replace(s, old_auto, new_auto, "RAM baseline sync")

# Hardware Detection values are CONFIG-selected values, not live telemetry.
old_hw = '''                    setValue(0,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
                    setValue(1,"SoC",std::to_string(int(std::lround(g_active.socVoltageUv/1000.0)))+" mV");
                    setValue(2,"DVB Shift",std::to_string(rc.dvbShift));
                    setValue(3,"VDDQ",std::to_string(int(std::lround(rc.vddqUv/1000.0)))+" mV");
                    setValue(4,"VDD2",std::to_string(int(std::lround(rc.vdd2Uv/1000.0)))+" mV");'''
new_hw = '''                    setValue(0,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
                    int activeRam=int(std::lround(g_active.realHz[2]/1e6));if(activeRam<1866)activeRam=1866;
                    int socCfg=0;std::string se;const int socFreq=nearestSocFreq(activeRam);
                    setValue(1,"SoC",occonfig::getSocPoint(socFreq,socCfg,se)?fmtSocConfigMv(socCfg):"unavailable");
                    setValue(2,"DVB Shift",std::to_string(rc.dvbShift));
                    setValue(3,"VDDQ",fmtMvUv(int(rc.vddqUv)));
                    setValue(4,"VDD2",fmtMvUv(int(rc.vdd2Uv)));'''
s = must_replace(s, old_hw, new_hw, "config-based hardware values")

# Warning wording: keep the reboot instruction on one red line.
old_warning = '''print(1,"WARNING");print(3,"Crash or freeze may occur.");print(5,"If it happens:");print(7,"reboot CFW and reopen Wizard.");print(9,"Test clocks are temporary.");print(11,"A : Start test");print(12,"B : Exit");'''
new_warning = '''print(1,"WARNING");print(3,"Crash or freeze may occur.");print(5,"If it happens: reboot CFW and reopen Wizard.");print(8,"Test clocks are temporary.");print(11,"A : Start test");print(12,"B : Exit");'''
s = must_replace(s, old_warning, new_warning, "one-line reboot warning")

p.write_text(s)

# Update red-warning recognition for the one-line sentence.
p = Path("source/gui_console.cpp")
g = p.read_text()
g = g.replace(
    '(raw == "WARNING" || raw == "Crash or freeze may occur." || raw == "If it happens:" || raw == "reboot CFW and reopen Wizard.")',
    '(raw == "WARNING" || raw == "Crash or freeze may occur." || raw == "If it happens: reboot CFW and reopen Wizard.")'
)
p.write_text(g)

# Build-time audit.
main=Path("source/main_oc.cpp").read_text(); gui=Path("source/gui_console.cpp").read_text()
checks={
    "beta14 version":"0.1.0-beta.14" in Path("Makefile").read_text(),
    "config based RAM guard":"occonfig::getRamConfig(rc,e)" in main and "HOC config mismatch before" in main,
    "profile VDDQ baseline":"expectedVddq=u32(p->vddqMv)*1000U" in main,
    "RAM only override":"clockMatch(c.overrideHz[2],ram)" in main and "clockMatch(c.realHz[2],ram)" in main,
    "CPU GPU not RAM gate":"clockMatch(c.overrideHz[0],cpu)||!clockMatch(c.overrideHz[1],gpu)" not in main[main.find("bool setRamOverrides"):main.find("void clearOverrides")],
    "config values display":"getSocPoint(socFreq,socCfg,se)" in main and "fmtMvUv(int(rc.vdd2Uv))" in main,
    "SoC half mV":"fmtSocConfigMv" in main,
    "one line reboot warning":"If it happens: reboot CFW and reopen Wizard." in main,
    "SoC max 1150":"rc.socVmaxMv!=1150" in main or "rc.socVmaxMv!=1150" not in main,
    "GPU retained":"GPU + RAM Integration" in main,
    "CPU retained":"CPU + RAM Final Validation" in main,
}
for name,ok in checks.items():print(("PASS " if ok else "FAIL ")+name)
bad=[name for name,ok in checks.items() if not ok]
if bad:raise SystemExit("Beta14 source audit failed: "+", ".join(bad))
