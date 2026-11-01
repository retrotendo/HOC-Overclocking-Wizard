from pathlib import Path


def must_replace(s: str, old: str, new: str, name: str, count: int = 1) -> str:
    if old not in s:
        raise SystemExit(f"beta13 marker missing: {name}")
    return s.replace(old, new, count)


# Version
p = Path("Makefile")
s = p.read_text()
s = must_replace(s, "APP_VERSION := 0.1.0-beta.12", "APP_VERSION := 0.1.0-beta.13", "version")
p.write_text(s)

# Expand the active-values card so Hardware Detection can show all RAM values/timings.
p = Path("source/gui_console.hpp")
s = p.read_text()
s = must_replace(
    s,
    "    bool haveActiveValues = false;\n    ValueRow values[5];",
    "    bool haveActiveValues = false;\n    int valueCount = 5;\n    ValueRow values[16];",
    "active values capacity",
)
p.write_text(s)

p = Path("source/main_oc.cpp")
s = p.read_text()

# SoC automatic ceiling is 1150 mV everywhere. Also cap the candidate table so combined
# diagnostics can never step above the agreed 1150 mV ceiling.
s = must_replace(
    s,
    "1125,1137,1150,1162,1175,1187,1200};",
    "1125,1137,1150};",
    "SOC_MV ceiling",
)
s = s.replace("d.socVmaxUv=1200", "d.socVmaxUv=1150")
s = s.replace(",5,1200,t,e)", ",5,1150,t,e)")
s = s.replace('"SoC VMAX","1200 mV"', '"SoC VMAX","1150 mV"')
s = s.replace("rc.socVmaxMv!=1200", "rc.socVmaxMv!=1150")
s = s.replace("SoC VMAX 1200 mV", "SoC VMAX 1150 mV")
s = s.replace("1200 mV ceiling", "1150 mV ceiling")

# RAM-only override verification: set CPU/GPU/RAM overrides, but only RAM real clock is
# allowed to decide whether a RAM test may start. CPU/GPU can downclock at idle.
marker = "void clearOverrides(){hocmonSetOverride(HocMonModule_CPU,0);hocmonSetOverride(HocMonModule_GPU,0);hocmonSetOverride(HocMonModule_MEM,0);}\n"
helper = r'''bool setRamOverrides(u32 cpu,u32 gpu,u32 ram,std::string& err) {
    Result rc=hocmonSetOverride(HocMonModule_CPU,cpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_GPU,gpu); if(R_SUCCEEDED(rc))rc=hocmonSetOverride(HocMonModule_MEM,ram);
    if(R_FAILED(rc)){char b[64];std::snprintf(b,sizeof(b),"Temporary Override failed: 0x%08X",rc);err=b;return false;}
    svcSleepThread(500'000'000);
    HocMonClocks c{}; rc=hocmonGetTelemetry(&c); if(R_FAILED(rc)){err="Could not verify HOC active values.";return false;}
    if(!clockMatch(c.overrideHz[0],cpu)||!clockMatch(c.overrideHz[1],gpu)||!clockMatch(c.overrideHz[2],ram)||!clockMatch(c.realHz[2],ram)){
        err="Requested RAM clock is not active. This candidate may be capped or experiencing a PLL drop.";return false;
    }
    g_active=c; return true;
}

'''
if "bool setRamOverrides(" not in s:
    s = must_replace(s, marker, helper + marker, "RAM-only override helper")

# Every RAM-only validation uses RAM-domain real-clock verification.
s = s.replace("setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)", "setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)")
s = s.replace("setOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)", "setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(g.ramRecommendedMHz)*1000000U,e)")

# Hardware Detection: real current RAM config in readable individual rows.
old_hw = '''            if(detected){
                occonfig::RamConfig rc{}; std::string re;
                if(occonfig::getRamConfig(rc,re)){
                    v.haveActiveValues=true;
                    std::ostringstream rt; for(int i=0;i<8;++i){if(i)rt<<'-';rt<<rc.timings[i];}
                    setValue(0,"RAM Timings",rt.str());
                }
            }
            gui::begin(v);'''
new_hw = '''            if(detected){
                occonfig::RamConfig rc{}; std::string re;
                if(occonfig::getRamConfig(rc,re)){
                    v.haveActiveValues=true;v.valueCount=13;
                    setValue(0,"RAM Max Clock",std::to_string(rc.ramMaxMHz)+" MHz");
                    setValue(1,"SoC",std::to_string(int(std::lround(g_active.socVoltageUv/1000.0)))+" mV");
                    setValue(2,"DVB Shift",std::to_string(rc.dvbShift));
                    setValue(3,"VDDQ",std::to_string(int(std::lround(rc.vddqUv/1000.0)))+" mV");
                    setValue(4,"VDD2",std::to_string(int(std::lround(rc.vdd2Uv/1000.0)))+" mV");
                    static const char* timingNames[8]={"t1 tRCD","t2 tRP","t3 tRAS","t4 tRRD","t5 tRFC","t6 tRTW","t7 tWTR","t8 tREFI"};
                    for(int i=0;i<8;++i)setValue(5+i,timingNames[i],std::to_string(rc.timings[i]));
                }
            }
            gui::begin(v);'''
s = must_replace(s, old_hw, new_hw, "hardware active values")

# Active values: no decimals anywhere in the side card.
s = s.replace('fmt1(g_active.realHz[2]/1e6)+" MHz"', 'std::to_string(int(std::lround(g_active.realHz[2]/1e6)))+" MHz"')
s = s.replace('fmt1(g_active.vdd2VoltageUv/1000.0)+" mV"', 'std::to_string(int(std::lround(g_active.vdd2VoltageUv/1000.0)))+" mV"')
s = s.replace('fmt1(g_active.vddqVoltageUv/1000.0)+" mV"', 'std::to_string(int(std::lround(g_active.vddqVoltageUv/1000.0)))+" mV"')
s = s.replace('fmt1(g_active.socVoltageUv/1000.0)+" mV"', 'std::to_string(int(std::lround(g_active.socVoltageUv/1000.0)))+" mV"')
s = s.replace('fmt1(g_active.realHz[1]/1e6)+" MHz"', 'std::to_string(int(std::lround(g_active.realHz[1]/1e6)))+" MHz"')
s = s.replace('fmt1(g_active.gpuVoltageUv/1000.0)+" mV"', 'std::to_string(int(std::lround(g_active.gpuVoltageUv/1000.0)))+" mV"')
s = s.replace('fmt1(g_active.realHz[0]/1e6)+" MHz"', 'std::to_string(int(std::lround(g_active.realHz[0]/1e6)))+" MHz"')
s = s.replace('fmt1(g_active.cpuVoltageUv/1000.0)+" mV"', 'std::to_string(int(std::lround(g_active.cpuVoltageUv/1000.0)))+" mV"')

# RAM Max Clock Search: clear title, no X shortcut, clean red warning lines.
old_ui = '''case Stage::RamSweep:{int freq=(g.ramSearchIndex>=0&&g.ramSearchIndex<=g.ramSearchEndIndex)?int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]):0;v.stageTitle="RAM Clock Search";v.instructionTitle="Start test";v.instructionLine1="";v.instructionLine2="A  Start test";gui::begin(v);print(1,"WARNING");print(2,"Crash or freeze may occur.");print(3,"If it happens: reboot CFW and reopen Wizard.");print(4,"Test clocks are temporary.");print(9,"A : Start test");print(10,"X : Stop / use last stable");print(11,"B : Exit");gui::present();break;}'''
new_ui = '''case Stage::RamSweep:{v.stageTitle="RAM Max Clock Search";v.instructionTitle="Start test";v.instructionLine1="";v.instructionLine2="A  Start test";gui::begin(v);print(1,"WARNING");print(3,"Crash or freeze may occur.");print(5,"If it happens:");print(7,"reboot CFW and reopen Wizard.");print(9,"Test clocks are temporary.");print(11,"A : Start test");print(12,"B : Exit");gui::present();break;}'''
s = must_replace(s, old_ui, new_ui, "RAM Max Clock Search UI")
old_input = '''if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamSweepAutomatic();redraw=true;continue;}if(k&HidNpadButton_X){finishRamSweep();redraw=true;continue;}}'''
new_input = '''if(g.stage==Stage::RamSweep){if(k&HidNpadButton_A){runRamSweepAutomatic();redraw=true;continue;}}'''
s = must_replace(s, old_input, new_input, "remove RAM sweep X")

# Reboot modal gets visible spacing between its three instructions.
old_reboot_body = '''m.body={"The new Horizon OC values were saved.","Press A to reboot now. After CFW starts, reopen the Wizard.","The Wizard resumes at the next step."};'''
new_reboot_body = '''m.body={"The new Horizon OC values were saved.","","Press A to reboot now. After CFW starts, reopen the Wizard.","","The Wizard resumes at the next step."};'''
s = must_replace(s, old_reboot_body, new_reboot_body, "restart spacing")

# Disclaimer: once tuning has already progressed, reconstruct the acceptance marker instead
# of showing the disclaimer again after every Wizard reboot. Full Reset still removes it and
# returns the stage to Hardware, so a genuinely reset Wizard shows it again.
old_disclaimer = '''    if(!fileExists(DISCLAIMER_FILE)){'''
new_disclaimer = '''    if(!fileExists(DISCLAIMER_FILE) && g.stage!=Stage::Hardware){ensureDir(APP_DIR);std::ofstream(DISCLAIMER_FILE)<<"accepted\\n";fsdevCommitDevice("sdmc");}\n    if(!fileExists(DISCLAIMER_FILE)){'''
s = must_replace(s, old_disclaimer, new_disclaimer, "disclaimer persistence")

p.write_text(s)

# GUI: compact 13-row active-values card; red/roomy warning block.
p = Path("source/gui_console.cpp")
g = p.read_text()
old_values = '''    int yy = y + 61;
    for (int i = 0; i < 5; ++i, yy += 43) {
        const ValueRow& v = g_view.values[i];
        if (v.mismatch) roundedRect(x + 18, yy - 5, w - 36, 36, 10, mix(C_PANEL_2, C_RED, 11));
        if (i) fillRect(x + 25, yy - 9, w - 50, 1, mix(C_PANEL, C_BORDER, 70));
        drawText(x + 26, yy, 16, C_MUTED, v.label);
        drawTextRight(x + w - 26, yy - 1, 18, v.mismatch ? C_RED : C_TEXT, v.value);
        fillCircle(x + 13, yy + 10, 3, v.mismatch ? C_RED : C_GREEN);
    }'''
new_values = '''    const int count=std::clamp(g_view.valueCount,0,16);
    const bool compact=count>5;
    int yy = y + (compact?49:61);
    const int step=compact?18:43;
    for (int i = 0; i < count; ++i, yy += step) {
        const ValueRow& v = g_view.values[i];
        if (v.mismatch) roundedRect(x + 18, yy - 3, w - 36, compact?18:36, 8, mix(C_PANEL_2, C_RED, 11));
        if (i && !compact) fillRect(x + 25, yy - 9, w - 50, 1, mix(C_PANEL, C_BORDER, 70));
        drawText(x + 26, yy, compact?13:16, C_MUTED, v.label);
        drawTextRight(x + w - 26, yy - 1, compact?14:18, v.mismatch ? C_RED : C_TEXT, v.value);
        fillCircle(x + 13, yy + (compact?7:10), 3, v.mismatch ? C_RED : C_GREEN);
    }'''
g = must_replace(g, old_values, new_values, "compact active values")

# Special warning rendering: no colon-table/tab effect, red from WARNING through Wizard,
# with a visible free line between each warning line.
needle = '''        for (const std::string& raw : body) {
            if (shown >= bodyMax || by > y + h - 190) break;
            if (raw == "WARNING") {'''
replacement = '''        for (const std::string& raw : body) {
            if (shown >= bodyMax || by > y + h - 190) break;
            const bool ramSearchWarning = g_view.stageTitle == "RAM Max Clock Search" &&
                (raw == "WARNING" || raw == "Crash or freeze may occur." || raw == "If it happens:" || raw == "reboot CFW and reopen Wizard.");
            if (ramSearchWarning) {
                by = drawWrappedText(x + 28, by, raw=="WARNING"?16:17, C_RED, raw, w - 56, 25, 2);
                by += 13; ++shown; continue;
            }
            if (raw == "WARNING") {'''
g = must_replace(g, needle, replacement, "red RAM warning")
p.write_text(g)

# Assertions: fail the build before compiling if any agreed beta13 behavior is missing.
main = Path("source/main_oc.cpp").read_text()
hpp = Path("source/gui_console.hpp").read_text()
gui = Path("source/gui_console.cpp").read_text()
checks = {
    "beta13 version": "0.1.0-beta.13" in Path("Makefile").read_text(),
    "SoC max 1150": "d.socVmaxUv=1150" in main and "1187,1200" not in main,
    "RAM-only real clock check": "bool setRamOverrides(" in main and "clockMatch(c.realHz[2],ram)" in main,
    "RAM max search title": 'v.stageTitle="RAM Max Clock Search"' in main,
    "RAM sweep X removed": "Stop / use last stable" not in main,
    "hardware 13 active values": "v.valueCount=13" in main and '"t8 tREFI"' in main,
    "active values compact": "const bool compact=count>5" in gui and "ValueRow values[16]" in hpp,
    "warning red spaced": "ramSearchWarning" in gui and "by += 13" in gui,
    "restart spacing": 'm.body={"The new Horizon OC values were saved.","","Press A to reboot now.' in main,
    "disclaimer resume": "g.stage!=Stage::Hardware" in main,
    "GPU logic retained": "GPU + RAM Integration" in main,
    "CPU logic retained": "CPU + RAM Final Validation" in main,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
bad=[name for name,ok in checks.items() if not ok]
if bad:
    raise SystemExit("Beta13 source audit failed: " + ", ".join(bad))
