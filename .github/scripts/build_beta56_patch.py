from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta56 marker missing: {name}")
    return s.replace(old, new, count)


# Version only. No tuning, benchmark, score or recommendation math changes.
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.55','APP_VERSION := 0.1.0-beta.56','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# RAM target selection task copy: explicit, short fixed lines.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()
m=must_replace(m,
    'v.instructionLine1="Use the Left / Right buttons to inspect and";',
    'v.instructionLine1="Use the Left / Right buttons";',
    'target task line 1')
m=must_replace(m,
    'v.instructionLine2="select another measured stable RAM point.";',
    'v.instructionLine2="to select your target frequency.";',
    'target task line 2')

# Explain the practical benefit of lower VDD2/VDDQ for users who do not know the rails.
old_eff='print(4,"@INDENT@Best balance between RAM performance and voltage. Choosing this target can allow lower VDD2 and VDDQ in the next steps.");'
new_eff='print(4,"@INDENT@Best balance between RAM performance and voltage. Choosing this target can allow lower VDD2 and VDDQ in the next steps. Lower VDD2/VDDQ can reduce overall RAM temperatures and power consumption.");'
m=must_replace(m,old_eff,new_eff,'efficiency benefit explanation')
p.write_text(m)

# -----------------------------------------------------------------------------
# RAM graph: move the mini Inspect-points control into the free graph-header area
# indicated by the user, while keeping it above the plotted curves.
# Also suppress the generic "More details..." footer on the two RAM-target
# explanation pages because those pages are complete and paginated explicitly.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()
g=must_replace(g,
    'const int dcx=gx+28, dcy=y+111, dr=8, ds=11;',
    'const int dcx=gx+300, dcy=y+111, dr=8, ds=11;',
    'inspect control position')
old_more='''        if (shown < int(body.size()) && by < y + h - 175)\n            drawText(x + 28, by, 15, C_MUTED, "More details continue in this step...");'''
new_more='''        const bool ramTargetExplanation = startsWith(g_view.stageTitle, "Choosing Your RAM Target");\n        if (!ramTargetExplanation && shown < int(body.size()) && by < y + h - 175)\n            drawText(x + 28, by, 15, C_MUTED, "More details continue in this step...");'''
g=must_replace(g,old_more,new_more,'suppress RAM target more-details footer')
p.write_text(g)

# -----------------------------------------------------------------------------
# Audit presentation changes and explicitly preserve all tuning logic.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta56 version':'0.1.0-beta.56' in Path('Makefile').read_text(),
    'task fixed line 1':'v.instructionLine1="Use the Left / Right buttons"' in main,
    'task fixed line 2':'v.instructionLine2="to select your target frequency."' in main,
    'efficiency practical benefit':'Lower VDD2/VDDQ can reduce overall RAM temperatures and power consumption.' in main,
    'two-page explanation retained':'Choosing Your RAM Target (1/2)' in main and 'Choosing Your RAM Target (2/2)' in main,
    'real indentation retained':'@INDENT@' in main and 'drawWrappedText(x + 68' in gui,
    'more-details suppressed only here':'startsWith(g_view.stageTitle, "Choosing Your RAM Target")' in gui and '!ramTargetExplanation && shown < int(body.size())' in gui,
    'inspect control moved':'const int dcx=gx+300, dcy=y+111, dr=8, ds=11' in gui,
    'inspect text retained':'Inspect points' in gui,
    'graph geometry retained':'gx=x+48' in gui and 'gy=y+140' in gui and 'gw=w-96' in gui and 'gh=190' in gui,
    'score formula retained':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'raw composite retained':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng and '0.25*std::log(ramLat)' in eng and '0.05*std::log(l2Lat)' in eng,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta56 source audit failed: '+', '.join(bad))
