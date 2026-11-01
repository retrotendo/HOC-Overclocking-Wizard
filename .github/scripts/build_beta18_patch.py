from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta18 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced_statement(src, marker, replacement):
    pos = src.find(marker)
    if pos < 0:
        raise SystemExit(f"beta18 statement missing: {marker}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta18 opening brace missing: {marker}")
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
        raise SystemExit(f"beta18 unbalanced statement: {marker}")
    return src[:pos] + replacement + src[end:]


# Version
p=Path('Makefile'); s=p.read_text(); s=must_replace(s,'APP_VERSION := 0.1.0-beta.17','APP_VERSION := 0.1.0-beta.18','version'); p.write_text(s)

# RamConfig must expose every CONFIG value that RAM Preparation requires.
p=Path('source/oc_config.hpp'); h=p.read_text()
h=must_replace(h,
'''struct RamConfig {\n    bool ok = false;\n    bool hpMode = false;''',
'''struct RamConfig {\n    bool ok = false;\n    bool uncappedClocks = false;\n    bool hpMode = false;''',
'uncapped field')
p.write_text(h)

p=Path('source/oc_config.cpp'); c=p.read_text()
c=must_replace(c,
'''out.ok=true;out.hpMode=v[i->hp]!=0;out.ramMaxMHz=''',
'''out.ok=true;out.uncappedClocks=v[i->uncapped]!=0;out.hpMode=v[i->hp]!=0;out.ramMaxMHz=''',
'uncapped read')
p.write_text(c)

p=Path('source/main_oc.cpp'); m=p.read_text()

# The preparation SET table and its mismatch highlighting must use the official DVB baseline 8.
m=must_replace(m,
'''row("RAM","DVB Shift","5",have?std::to_string(rc.dvbShift):"unavailable",have&&rc.dvbShift!=5);''',
'''row("RAM","DVB Shift","8",have?std::to_string(rc.dvbShift):"unavailable",have&&rc.dvbShift!=8);''',
'prep DVB row')

# Show the formerly-hidden uncapped requirement so every checked CONFIG field is visible.
step_row='''row("RAM","Step Mode","66 MHz",have?(rc.stepMode==0?"66 MHz":rc.stepMode==1?"100 MHz":rc.stepMode==2?"JEDEC":rc.stepMode==3?"133 MHz":rc.stepMode==4?"33 MHz":"unknown"):"unavailable",have&&rc.stepMode!=0);'''
if step_row not in m:
    raise SystemExit('beta18 step row missing')
m=m.replace(step_row, step_row+'\n                row("RAM","Uncapped Clocks","ON",have?(rc.uncappedClocks?"ON":"OFF"):"unavailable",have&&!rc.uncappedClocks);',1)

# Never fall back to live telemetry in ACTUAL ACTIVE VALUES. If a SoC config point is not
# explicitly overridden, say so; the card is CONFIG-selected values only.
m=m.replace(
'''setValue(3,"SoC",occonfig::getSocPoint(sf,sv,se)&&sv>0?fmtSocConfigMv(sv):fmtMvUv(int(g_active.socVoltageUv)));''',
'''setValue(3,"SoC",occonfig::getSocPoint(sf,sv,se)?(sv>0?fmtSocConfigMv(sv):"No Override"):"unavailable");''')

# RAM Preparation manual validation: direct CONFIG-vs-SET comparison using exactly the same
# fields displayed in the preparation table. Do not use hocmonVerifyOcPreparation here.
new_handler=r'''if(g.stage==Stage::RamPreparation){
            if(k&HidNpadButton_Y){prepareRamAuto();redraw=true;continue;}
            if(k&HidNpadButton_A){
                const auto*p=profile();
                if(!p){modalError("Automatic RAM preparation is unavailable for this DRAM ID.");redraw=true;continue;}
                occonfig::RamConfig rc{};std::string e;
                if(!occonfig::getRamConfig(rc,e)){modalError("Could not read HOC config: "+e);redraw=true;continue;}
                std::vector<std::string> mm;
                auto add=[&](const std::string& x){mm.push_back(x);};
                if(rc.ramMaxMHz!=3400) add("RAM Max Clock is "+std::to_string(rc.ramMaxMHz)+" MHz; SET is 3400 MHz");
                if(rc.stepMode!=0) add("RAM Step Mode is not 66 MHz");
                if(!rc.uncappedClocks) add("Uncapped Clocks is OFF; SET is ON");
                if(rc.vdd2Uv!=u32(p->vdd2Mv)*1000U) add("VDD2 is "+fmtMvUv(int(rc.vdd2Uv))+"; SET is "+std::to_string(p->vdd2Mv)+" mV");
                if(rc.vddqUv!=u32(p->vddqMv)*1000U) add("VDDQ is "+fmtMvUv(int(rc.vddqUv))+"; SET is "+std::to_string(p->vddqMv)+" mV");
                if(rc.hpMode) add("HP Mode is ON; SET is OFF");
                if(rc.dvbShift!=8) add("DVB Shift is "+std::to_string(rc.dvbShift)+"; SET is 8");
                if(rc.socVmaxMv!=1150) add("SoC VMAX is "+std::to_string(rc.socVmaxMv)+" mV; SET is 1150 mV");
                for(int i=0;i<8;++i){if(rc.timings[i]!=p->common.t[i]){add("Common Timings do not match SET values");break;}}
                if(!mm.empty()){
                    modalError("RAM Preparation mismatch: "+mm.front()+". The check now uses the same HOC config values shown in SET / ACTIVE.");
                    redraw=true;continue;
                }
                g.ramHpMode=0;g.ramTimingMode=0;g.dvbGood=8;g.dvbCandidate=7;
                g.vdd2GoodUv=int(rc.vdd2Uv);g.vdd2CandidateUv=std::max(VDD2_MIN_UV,g.vdd2GoodUv-12500);
                g.vddqGoodMv=int(rc.vddqUv/1000U);g.vddqCandidateMv=std::max(VDDQ_MIN_MV,g.vddqGoodMv-10);
                g.ramSearchIndex=oc::firstRamSearchIndex(p);g.ramSearchEndIndex=ramEndIndex();
                requestReboot(Stage::RamSweep);redraw=true;continue;
            }
        }'''
m=replace_braced_statement(m,'if(g.stage==Stage::RamPreparation){',new_handler)

p.write_text(m)

# Audit the actual generated source, not only patch markers.
main=Path('source/main_oc.cpp').read_text(); cfg=Path('source/oc_config.cpp').read_text(); hdr=Path('source/oc_config.hpp').read_text()
prep_start=main.find('case Stage::RamPreparation:')
prep_end=main.find('case Stage::RamSweep:',prep_start)
prep_ui=main[prep_start:prep_end]
handler_start=main.find('if(g.stage==Stage::RamPreparation){')
handler_end=main.find('if(g.stage==Stage::RamSweep)',handler_start)
prep_handler=main[handler_start:handler_end]
side_start=main.find('auto setValue=[&]')
side_end=main.find('auto print=[&]',side_start)
side=main[side_start:side_end]
checks={
 'beta18 version':'0.1.0-beta.18' in Path('Makefile').read_text(),
 'prep UI DVB8':'row("RAM","DVB Shift","8"' in prep_ui and 'rc.dvbShift!=8' in prep_ui,
 'prep UI uncapped visible':'row("RAM","Uncapped Clocks","ON"' in prep_ui,
 'manual check direct config':'occonfig::getRamConfig(rc,e)' in prep_handler and 'hocmonVerifyOcPreparation' not in prep_handler,
 'manual check DVB8':'rc.dvbShift!=8' in prep_handler and 'SET is 8' in prep_handler,
 'manual check step66':'rc.stepMode!=0' in prep_handler,
 'manual check uncapped':'!rc.uncappedClocks' in prep_handler,
 'manual check SoC1150':'rc.socVmaxMv!=1150' in prep_handler,
 'manual check common timings':'rc.timings[i]!=p->common.t[i]' in prep_handler,
 'state starts DVB8':'g.dvbGood=8;g.dvbCandidate=7' in prep_handler,
 'RamConfig uncapped':'uncappedClocks' in hdr and 'out.uncappedClocks=v[i->uncapped]!=0' in cfg,
 'no live SoC fallback':'g_active.socVoltageUv' not in side,
 '60s RAM retained':'runStress(stress::Kind::Ram,60,' in main,
 'settling poll retained':'for(int i=0;i<50;++i)' in main,
 'visible benchmark retained':'RAM Memory Benchmark' in Path('source/oc_bench.cpp').read_text(),
 'GPU flow retained':'GPU + RAM Integration' in main,
 'CPU flow retained':'CPU + RAM Final Validation' in main,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta18 source audit failed: '+', '.join(bad))
