from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta44 marker missing: {name}")
    return s.replace(old, new, count)

# Version only; tuning/recommendation logic is intentionally unchanged in beta44.
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.43','APP_VERSION := 0.1.0-beta.44','version')
p.write_text(s)

p=Path('source/gui_console.cpp'); g=p.read_text()

# Replace the redundant chart title + beta43 two-button hint with a compact
# Switch-like four-button inspection legend. Only Left/Right carry symbols;
# Up/Down remain muted decorative members of the directional cluster.
old_title='''            drawText(gx,y+106,18,C_CYAN,g_view.chartTitle.empty()?"RAM benchmark result":g_view.chartTitle);'''
new_title='''            // Compact Switch-like directional legend in place of the redundant
            // "RAM performance and SoC voltage" title. Only Left/Right are active.
            const int dcx=gx+38, dcy=y+114, dr=13;
            fillCircle(dcx,dcy-17,dr,C_BORDER); fillCircle(dcx,dcy-17,dr-2,C_PANEL_2);
            fillCircle(dcx,dcy+17,dr,C_BORDER); fillCircle(dcx,dcy+17,dr-2,C_PANEL_2);
            fillCircle(dcx-17,dcy,dr,C_BLUE);   fillCircle(dcx-17,dcy,dr-2,C_PANEL_2);
            fillCircle(dcx+17,dcy,dr,C_BLUE);   fillCircle(dcx+17,dcy,dr-2,C_PANEL_2);
            drawText(dcx-22,dcy-10,16,C_TEXT,"<");
            drawText(dcx+12,dcy-10,16,C_TEXT,">");
            drawText(dcx+42,dcy-9,14,C_TEXT,"Inspect points");'''
g=must_replace(g,old_title,new_title,'Switch-like inspection legend')

# Remove beta43's separate right-side arrow legend now that the directional
# cluster occupies the old title position.
old_nav='''            const int navX=gx+gw-220, navY=y+97;
            roundedBorder(navX,navY,28,28,8,C_BLUE,C_PANEL_2,1);
            roundedBorder(navX+36,navY,28,28,8,C_BLUE,C_PANEL_2,1);
            drawText(navX+9,navY+3,17,C_TEXT,"<");
            drawText(navX+45,navY+3,17,C_TEXT,">");
            drawText(navX+75,navY+4,13,C_TEXT,"Inspect points");'''
g=must_replace(g,old_nav,'','remove beta43 right-side navigation hint')

# Spell out both recommendation meanings in the selected-point row.
old_rec='''                const std::string rec="EFF "+std::to_string(g_view.chartEfficiencyMHz)+" MHz   |   PERF "+std::to_string(g_view.chartPerformanceMHz)+" MHz";'''
new_rec='''                const std::string rec="Recommended for: Efficiency "+std::to_string(g_view.chartEfficiencyMHz)+" MHz   |   Performance "+std::to_string(g_view.chartPerformanceMHz)+" MHz";'''
g=must_replace(g,old_rec,new_rec,'expanded recommendation wording')

# Give the longer recommendation text enough room while keeping the currently
# inspected point visible at the left.
old_draw='''                drawText(gx,sy,13,C_TEXT,fitText(g_view.chartSummary,13,std::max(300,gw-330)));
                drawTextRight(gx+gw,sy,13,C_GREEN,rec);'''
new_draw='''                drawText(gx,sy,12,C_TEXT,fitText(g_view.chartSummary,12,std::max(250,gw-500)));
                drawTextRight(gx+gw,sy,12,C_GREEN,rec);'''
g=must_replace(g,old_draw,new_draw,'recommendation row spacing')
p.write_text(g)

# Audit: UI-only beta; preserve beta43 recommendation + hidden debug and the
# beta32 measured performance-index formula exactly.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
checks={
    'beta44 version':'0.1.0-beta.44' in Path('Makefile').read_text(),
    'old chart title hidden':'drawText(gx,y+106,18,C_CYAN,g_view.chartTitle' not in gui,
    'four button direction cluster':'const int dcx=gx+38' in gui and 'dcy-17' in gui and 'dcy+17' in gui and 'dcx-17' in gui and 'dcx+17' in gui,
    'left right marked':'drawText(dcx-22' in gui and 'drawText(dcx+12' in gui,
    'inspection text':'Inspect points' in gui,
    'old right nav removed':'const int navX=gx+gw-220' not in gui,
    'expanded recommendations':'Recommended for: Efficiency ' in gui and 'Performance ' in gui,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'HidNpadButton_Plus' in main and 'B : Back to RAM graph' in main,
    'eff recommendation retained':'findRamEfficiencyTargetIndex' in main and 'ramEfficiencyRecommendedMHz' in main,
    'perf recommendation retained':'findRamSuggestedTargetIndex' in main and 'ramRecommendedMHz' in main,
    'performance index gpu 35':'0.35*std::log(gpuGroup)' in eng,
    'performance index cpu 35':'0.35*std::log(cpuGroup)' in eng,
    'performance index ram latency 25':'0.25*std::log(ramLat)' in eng,
    'performance index l2 5':'0.05*std::log(l2Lat)' in eng,
    'beta41 recovery retained':'NO - retry ' in main and 'YES - mark ' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta44 source audit failed: '+', '.join(bad))
