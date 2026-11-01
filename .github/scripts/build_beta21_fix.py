from pathlib import Path
import re


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta21-fix marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta21-fix function missing: {signature}")
    brace = src.find('{', pos)
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"beta21-fix unbalanced function: {signature}")
    return src[:pos] + replacement + src[end:]


# -----------------------------------------------------------------------------
# YOUR TASK = information only. All actionable buttons remain on the left card.
# -----------------------------------------------------------------------------
p = Path('source/gui_console.cpp')
g = p.read_text()
new_card = r'''void drawInstructionCard() {
    const int x = 835, y = 158, w = 405, h = 205;
    drawCard(x, y, w, h, true);
    drawLabel(x + 24, y + 20, "YOUR TASK");
    drawText(x + 24, y + 52, 23, C_TEXT,
             fitText(g_view.instructionTitle.empty() ? "Continue Wizard" : g_view.instructionTitle, 23, w - 48));
    if (!g_view.instructionLine1.empty())
        drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));
}'''
g = replace_function(g, 'void drawInstructionCard()', new_card)
p.write_text(g)


# -----------------------------------------------------------------------------
# Main wizard fixes.
# -----------------------------------------------------------------------------
p = Path('source/main_oc.cpp')
m = p.read_text()

# Track the actual stress outcome. A user cancel / technical abort must never be reported as
# "Detected errors" and must not establish the max-clock limit.
m = must_replace(
    m,
    'HocMonClocks g_active{};\n',
    'HocMonClocks g_active{};\nstress::Outcome g_lastStressOutcome = stress::Outcome::Pass;\nstd::string g_lastStressDetail;\n',
    'stress result globals')

m = must_replace(
    m,
    '        auto r=stress::run(k,seconds,title,ctx);',
    '        auto r=stress::run(k,seconds,title,ctx);\n        g_lastStressOutcome=r.outcome;\n        g_lastStressDetail=r.detail;',
    'capture stress result')

# Temporary override lifetime is one complete tuning test function. Stress + benchmark inside the
# same function still see the requested clocks; every return path clears CPU/GPU/RAM afterwards.
clear_marker = 'void clearOverrides(){hocmonSetOverride(HocMonModule_CPU,0);hocmonSetOverride(HocMonModule_GPU,0);hocmonSetOverride(HocMonModule_MEM,0);}\n'
cleanup_decl = clear_marker + '''\nstruct OverrideCleanupScope {\n    ~OverrideCleanupScope(){ clearOverrides(); }\n};\n'''
m = must_replace(m, clear_marker, cleanup_decl, 'override cleanup scope')

# Max-clock candidate: classify genuine RAM stability failure separately from cancel/technical
# interruption. The beta21 result stage remains the user-facing summary page.
new_ram_candidate = r'''void runRamCandidate(){
    if(g.ramSearchIndex<0||g.ramSearchIndex>g.ramSearchEndIndex){finishRamSweep();return;}
    const int freq=int(oc::RAM_STEPS_MHZ[g.ramSearchIndex]);std::string e;
    g.ramFailedMHz=0;
    if(!guardRamConfig("RAM clock test"))return;
    if(!setRamOverrides(CPU_BASE_HZ,GPU_BASE_HZ,u32(freq)*1000000U,e)){
        modalError("RAM "+std::to_string(freq)+" MHz could not be activated. "+e+" This candidate was not evaluated; verify the HOC settings and retry.");
        return;
    }
    if(!runStress(stress::Kind::Ram,60,"RAM Clock Stability - "+std::to_string(freq)+" MHz","Testing RAM: "+std::to_string(freq)+" MHz")){
        if(g_lastStressOutcome==stress::Outcome::Fail){
            g.ramFailedMHz=freq;
            finishRamSweep();
        }else if(g_lastStressOutcome==stress::Outcome::Cancelled){
            modalError("RAM "+std::to_string(freq)+" MHz test was cancelled. This candidate was not evaluated; retry the same clock.");
        }else{
            modalError("RAM "+std::to_string(freq)+" MHz test did not complete. "+g_lastStressDetail+" This candidate was not evaluated; retry the same clock.");
        }
        return;
    }
    auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");
    if(!b.ok){
        modalError("Memory Benchmark failed at "+std::to_string(freq)+" MHz: "+b.error+" This candidate was not evaluated; retry the benchmark.");
        return;
    }
    oc::SweepPoint p;p.domain=oc::Domain::Ram;p.requestedMHz=freq;p.realMHz=b.telemetry.realRamMHz;p.railMv=std::uint32_t(std::round(b.telemetry.socMv));p.auxMv=std::uint32_t(std::round(b.telemetry.vdd2Mv));p.performance=b.score;p.latencyNs=b.ramNs;p.bandwidthMBs=b.cpuRead+b.gpuRead;p.batteryPowerW=b.telemetry.batteryPowerW;p.powerReliable=false;p.stable=true;p.context="Common / HP off / DVB8 / 66MHz Step Mode";recordPoint(ramPoints,p);g.ramStableMaxMHz=freq;
    if(g.ramSearchIndex>=g.ramSearchEndIndex)finishRamSweep();else{++g.ramSearchIndex;saveState();}
}'''
m = replace_function(m, 'void runRamCandidate()', new_ram_candidate)

# On the left, state explicitly that the number is the NEXT DVB candidate. On the right, the
# instruction title already says "Continue to apply DVB Shift X and reboot" before application.
m = must_replace(
    m,
    'case Stage::RamDvb:{v.stageTitle="RAM DVB Optimization";v.instructionTitle=',
    'case Stage::RamDvb:{v.stageTitle=g.dvbApplied?("DVB Shift "+std::to_string(g.dvbCandidate)+" Validation"):"Next DVB Candidate to Test";v.instructionTitle=',
    'DVB stage title')

# Apply the cleanup scope to every real tuning function that sets a temporary override and then
# runs a stress test and/or benchmark. This does not change tuning values or order.
def inject_cleanup(src):
    inserts=[]
    pattern=re.compile(r'\b(?:void|bool)\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{')
    for mt in pattern.finditer(src):
        name=mt.group(1)
        if name in {'setOverrides','setRamOverrides','runStress','requestReboot'}:
            continue
        brace=src.find('{',mt.start())
        depth=0; end=None
        for i in range(brace,len(src)):
            if src[i]=='{': depth+=1
            elif src[i]=='}':
                depth-=1
                if depth==0:
                    end=i+1; break
        if end is None:
            continue
        body=src[brace+1:end-1]
        owns_override=('setOverrides(' in body or 'setRamOverrides(' in body)
        does_test=('runStress(' in body or 'ocbench::run' in body)
        if owns_override and does_test and 'OverrideCleanupScope overrideCleanup;' not in body:
            inserts.append((brace+1,name))
    for pos,name in reversed(inserts):
        src=src[:pos]+f'\n    OverrideCleanupScope overrideCleanup; // clear CPU/GPU/RAM temporary overrides after {name}\n'+src[pos:]
    return src,[name for _,name in inserts]

m,injected=inject_cleanup(m)
print('Beta21 override cleanup functions:', ', '.join(injected))
if 'runRamCandidate' not in injected:
    raise SystemExit('beta21-fix did not add cleanup to runRamCandidate')

p.write_text(m)


# -----------------------------------------------------------------------------
# Final audit. No hidden developer shortcuts are added here.
# -----------------------------------------------------------------------------
gui=Path('source/gui_console.cpp').read_text()
main=Path('source/main_oc.cpp').read_text()
stress=Path('source/stress_tests.cpp').read_text()
card_start=gui.find('void drawInstructionCard()')
card_end=gui.find('\n}',card_start)+2
card=gui[card_start:card_end]
checks={
    'task card instruction only':'instructionLine2' not in card and 'drawActionButton' not in card and 'y + 126' not in card,
    'DVB left says next candidate':'Next DVB Candidate to Test' in main,
    'DVB right says apply and reboot':'Continue to apply DVB Shift ' in main and ' and reboot' in main,
    'sweep result page retained':'Errors detected at ' in main and 'Max clock candidate for now' in main,
    'true stress result captured':'g_lastStressOutcome=r.outcome' in main and 'g_lastStressDetail=r.detail' in main,
    'cancel not classified as fail':'g_lastStressOutcome==stress::Outcome::Cancelled' in main and 'was cancelled' in main,
    'technical abort not classified as fail':'This candidate was not evaluated' in main,
    'all-test override cleanup scope':'struct OverrideCleanupScope' in main and 'OverrideCleanupScope overrideCleanup' in main,
    'RAM candidate cleanup scope':'clear CPU/GPU/RAM temporary overrides after runRamCandidate' in main,
    '60 second RAM stability retained':'runStress(stress::Kind::Ram,60,"RAM Clock Stability - "' in main,
    'DVB8 retained':'Common / HP off / DVB8 / 66MHz Step Mode' in main,
    'charger guard retained':'waitForChargerRetry' in main,
    'audio reminder retained':'attention::tick(false)' in main,
    'no developer forced pass':'developerForcePass' not in stress,
    'no developer forced fail':'developerForceFail' not in stress,
}
for name,ok in checks.items():
    print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad:
    raise SystemExit('Beta21 final fix audit failed: '+', '.join(bad))
