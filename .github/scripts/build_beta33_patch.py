from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta33 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos<0: raise SystemExit(f"beta33 function missing: {signature}")
    brace=src.find('{',pos)
    if brace<0: raise SystemExit(f"beta33 opening brace missing: {signature}")
    depth=0;end=None
    for i in range(brace,len(src)):
        if src[i]=='{':depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1;break
    if end is None: raise SystemExit(f"beta33 unbalanced: {signature}")
    return src[:pos]+replacement+src[end:]


# Version.
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.32','APP_VERSION := 0.1.0-beta.33','version')
p.write_text(s)


# -----------------------------------------------------------------------------
# RAM Preparation: populate a concise Automatic Baseline summary.
# The user now chooses only Automatic or Current, so SET/ACTIVE comparison is
# obsolete on this page. Current settings are deliberately not copied into this
# card: choosing Current means "leave everything untouched" and immediately
# continues with that configuration.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp')
m=p.read_text()
needle='''            const auto*p=profile();\n            if(g_autoBaselineWarning){'''
replacement='''            const auto*p=profile();\n            v.preparationRows.clear();\n            if(p){\n                auto addPrep=[&](const char* group,const char* label,const std::string& value){\n                    gui::PreparationRow r;r.group=group;r.label=label;r.setValue=value;r.activeValue=\"\";r.mismatch=false;v.preparationRows.push_back(r);\n                };\n                addPrep(\"RAM\",\"Max Clock\",\"3400 MHz\");\n                addPrep(\"RAM\",\"Step Mode\",\"66 MHz\");\n                addPrep(\"RAM\",\"Uncapped\",\"ON\");\n                addPrep(\"RAM\",\"HP Mode\",\"OFF\");\n                addPrep(\"RAM\",\"DVB Shift\",\"8\");\n                addPrep(\"Voltages\",\"VDD2\",std::to_string(p->vdd2Mv)+\" mV\");\n                addPrep(\"Voltages\",\"VDDQ\",std::to_string(p->vddqMv)+\" mV\");\n                addPrep(\"Voltages\",\"SoC VMAX\",\"1150 mV\");\n                addPrep(\"Voltages\",\"SoC table\",\"Stock\");\n                addPrep(\"Timings\",\"RAM timings\",\"Common\");\n            }else{\n                gui::PreparationRow r;r.group=\"Automatic Baseline\";r.label=\"Status\";r.setValue=\"Unavailable for this DRAM\";v.preparationRows.push_back(r);\n            }\n            if(g_autoBaselineWarning){'''
m=must_replace(m,needle,replacement,'prep summary population')
p.write_text(m)


# -----------------------------------------------------------------------------
# Preparation renderer: one clean value column, no obsolete SET/ACTIVE columns.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp')
g=p.read_text()
new_renderer=r'''void drawPreparationCard() {
    const int x = 715, y = 158, w = 525, h = 522;
    drawCard(x, y, w, h, true);
    drawLabel(x + 24, y + 20, "AUTOMATIC BASELINE");
    drawText(x + 24, y + 48, 24, C_TEXT, "Preparation Values");
    drawText(x + 24, y + 80, 14, C_MUTED, "Values applied only when Automatic baseline is selected.");
    fillRect(x + 24, y + 112, w - 48, 1, C_BORDER);

    int yy = y + 126;
    std::string currentGroup;
    for (const PreparationRow& r : g_view.preparationRows) {
        if (r.group != currentGroup) {
            if (!currentGroup.empty()) {
                fillRect(x + 24, yy + 2, w - 48, 1, C_BORDER);
                yy += 12;
            }
            currentGroup = r.group;
            drawText(x + 24, yy, 14, C_CYAN, fitText(currentGroup, 14, w - 48));
            yy += 26;
        }
        if (yy > y + h - 32) break;
        drawText(x + 34, yy, 16, C_MUTED, fitText(r.label, 16, 250));
        drawTextRight(x + w - 28, yy, 17, C_TEXT, fitText(r.setValue, 17, 205));
        yy += 29;
    }
}'''
g=replace_function(g,'void drawPreparationCard()',new_renderer)
p.write_text(g)


# Audit generated source. UI-only beta; Beta32 benchmark methodology must remain.
main=Path('source/main_oc.cpp').read_text();gui=Path('source/gui_console.cpp').read_text();eng=Path('source/oc_engine.cpp').read_text();stress=Path('source/stress_tests.cpp').read_text()
start=gui.find('void drawPreparationCard()');end=gui.find('\nvoid ',start+10);prep_renderer=gui[start:end if end>0 else len(gui)]
checks={
 'beta33 version':'0.1.0-beta.33' in Path('Makefile').read_text(),
 'automatic baseline title':'AUTOMATIC BASELINE' in prep_renderer,
 'no set column':'\"SET\"' not in prep_renderer,
 'no active column':'\"ACTIVE\"' not in prep_renderer,
 'no old manual instruction':'Open Horizon OC / HOC Toolkit and match SET.' not in prep_renderer,
 'compact RAM values':all(x in main for x in ['Max Clock','3400 MHz','Step Mode','66 MHz','DVB Shift','HP Mode']),
 'profile rails':'std::to_string(p->vdd2Mv)' in main and 'std::to_string(p->vddqMv)' in main,
 'soc vmax concise':'SoC VMAX' in main and '1150 mV' in main,
 'soc table stock':'SoC table' in main and 'Stock' in main,
 'timings common':'RAM timings' in main and 'Common' in main,
 'automatic/current choices retained':'A : Automatic baseline' in main and 'X : Use my current settings as baseline' in main,
 'DVB8 baseline retained':'setRamPreparation(false,3400,p->vdd2Mv,p->vddqMv,8,1150' in main,
 'beta32 full raw RAM metrics':all(x in main for x in ['ramCpuCopyMBs','ramCpuReadMBs','ramCpuWriteMBs','ramGpuCopyMBs','ramGpuReadMBs','ramGpuWriteMBs','ramL2LatencyNs']),
 'beta32 composite index':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
 'benchmark cleanup retained':'clearOverrides();' in main[main.find('bool runFinalRamBenchmarkPoint'):main.find('void finishFinalRamBenchmarkSweep')],
 'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
 'mandatory explanation retained':'Read the explanation before choosing your RAM target' in main,
}
for name,ok in checks.items():print(('PASS ' if ok else 'FAIL ')+name)
bad=[n for n,o in checks.items() if not o]
if bad:raise SystemExit('Beta33 source audit failed: '+', '.join(bad))
