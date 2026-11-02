from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta42 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.41','APP_VERSION := 0.1.0-beta.42','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# Normal Wizard UI: remove the temporary RAM debug-page entry point now that the
# full raw benchmark data and recommendation model are validated. Keep the raw
# measurements themselves; they are still required by the Performance Index.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()
m=must_replace(m,
    '            if(k&HidNpadButton_Y){g_ramDebugPage=0;g.stage=Stage::RamDebug;saveState();redraw=true;continue;}\n',
    '',
    'remove graph Y debug input')
m=must_replace(m,
    '            print(11,"Y : Debug data");\n            print(12,"B : Exit");',
    '            print(11,"B : Exit");',
    'remove graph debug action')

# Give the renderer explicit recommendation values instead of hiding them inside
# the long selected-point summary, where they could be clipped below the plot.
old_summary='''            v.chartSummary=ramPointSummary(g.ramTargetMHz)+"  |  Efficiency "+std::to_string(g.ramEfficiencyRecommendedMHz)+"  |  Performance "+std::to_string(g.ramRecommendedMHz)+"  |  Max "+std::to_string(g.ramStableMaxMHz)+" MHz";'''
new_summary='''            v.chartSummary=ramPointSummary(g.ramTargetMHz);
            v.chartEfficiencyMHz=g.ramEfficiencyRecommendedMHz;
            v.chartPerformanceMHz=g.ramRecommendedMHz;
            v.chartStableMaxMHz=g.ramStableMaxMHz;'''
m=must_replace(m,old_summary,new_summary,'explicit graph recommendation values')
p.write_text(m)

# View fields for a dedicated, always-visible recommendation strip.
p=Path('source/gui_console.hpp'); h=p.read_text()
h=must_replace(h,
    '    bool chartRamLines = false;\n',
    '    bool chartRamLines = false;\n    int chartEfficiencyMHz = 0;\n    int chartPerformanceMHz = 0;\n    int chartStableMaxMHz = 0;\n',
    'chart recommendation fields')
p.write_text(h)

# -----------------------------------------------------------------------------
# RAM result graph layout:
# - lift the x-axis and selected-point summary clear of the action buttons;
# - show both recommendation values + Stable Max above the plot;
# - show an explicit Left/Right inspection hint in the legend row.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()
g=must_replace(g,
    '            const int gx=x+70, gy=y+145, gw=w-140, gh=160;',
    '            const int gx=x+70, gy=y+150, gw=w-140, gh=130;',
    'raise RAM graph bottom')

legend_anchor='''            roundedRect(gx+680,y+109,14,8,3,C_AMBER);
            drawText(gx+701,y+103,13,C_TEXT,"SoC mV");
'''
legend_new='''            roundedRect(gx+680,y+109,14,8,3,C_AMBER);
            drawText(gx+701,y+103,13,C_TEXT,"SoC mV");
            drawTextRight(gx+gw,y+103,12,C_MUTED,"Left / Right: inspect points");

            // Recommendation values stay visible independently of the selected
            // inspection point and independently of the bottom action buttons.
            const std::string recLine=
                "Efficiency " + std::to_string(g_view.chartEfficiencyMHz) + " MHz   |   Performance " +
                std::to_string(g_view.chartPerformanceMHz) + " MHz   |   Stable Max " +
                std::to_string(g_view.chartStableMaxMHz) + " MHz";
            drawText(gx,y+126,14,C_TEXT,fitText(recLine,14,gw));
'''
g=must_replace(g,legend_anchor,legend_new,'recommendation strip and inspect hint')

# Keep MHz labels clearly above the selected-point detail line.
g=must_replace(g,
    '            drawTextRight(gx+gw,gy+gh+8,10,C_MUTED,"MHz");',
    '            drawTextRight(gx+gw,gy+gh+6,10,C_MUTED,"MHz");',
    'MHz label spacing')
g=must_replace(g,
    '                drawText(gx,gy+gh+30,14,C_TEXT,fitText(g_view.chartSummary,14,gw));',
    '                drawText(gx,gy+gh+27,13,C_TEXT,fitText(g_view.chartSummary,13,gw));',
    'selected summary spacing')
p.write_text(g)

# Audit
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); hpp=Path('source/gui_console.hpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
# Scope only the graph input block so dormant compatibility code for the old
# RamDebug enum does not matter.
graph_input_start=main.find('if(g.stage==Stage::RamGraph){')
graph_input_end=main.find('if(g.stage==Stage::RamDebug)',graph_input_start)
graph_input=main[graph_input_start:graph_input_end] if graph_input_start>=0 and graph_input_end>graph_input_start else ''
graph_render_start=main.find('case Stage::RamGraph:')
graph_render_end=main.find('gui::present();break;}',graph_render_start)
graph_render=main[graph_render_start:graph_render_end] if graph_render_start>=0 and graph_render_end>graph_render_start else ''
checks={
    'beta42 version':'0.1.0-beta.42' in Path('Makefile').read_text(),
    'graph input found':bool(graph_input),
    'debug entry removed':'g.stage=Stage::RamDebug' not in graph_input,
    'debug button removed':'Y : Debug data' not in graph_render,
    'raw metrics retained':'ramCpuCopyMBs' in main and 'ramGpuWriteMBs' in main and 'ramL2LatencyNs' in main,
    'performance index retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
    'dual recommendation state retained':'ramEfficiencyRecommendedMHz' in main and 'findRamEfficiencyTargetIndex' in main and 'findRamSuggestedTargetIndex' in main,
    'explicit graph recommendation values':'chartEfficiencyMHz=g.ramEfficiencyRecommendedMHz' in main and 'chartPerformanceMHz=g.ramRecommendedMHz' in main and 'chartStableMaxMHz=g.ramStableMaxMHz' in main,
    'view recommendation fields':'chartEfficiencyMHz = 0' in hpp and 'chartPerformanceMHz = 0' in hpp and 'chartStableMaxMHz = 0' in hpp,
    'recommendation strip':'Efficiency ' in gui and 'Performance ' in gui and 'Stable Max ' in gui and 'recLine' in gui,
    'inspect hint':'Left / Right: inspect points' in gui,
    'raised graph':'gy=y+150' in gui and 'gh=130' in gui,
    'MHz axis retained':'"MHz"' in gui,
    'EFF PERF markers retained':'EFF+PERF' in gui and '"EFF"' in gui and '"PERF"' in gui,
    'mandatory explanation retained':'Read the explanation before choosing your RAM target' in main,
    'target badges retained':'ramTargetBadges' in main and 'EFFICIENCY' in main and 'PERFORMANCE' in main,
    'beta41 two-choice recovery retained':'NO - retry ' in main and 'YES - mark ' in main and 'Two-choice decision modal: A / X only.' in gui,
    'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta42 source audit failed: '+', '.join(bad))
