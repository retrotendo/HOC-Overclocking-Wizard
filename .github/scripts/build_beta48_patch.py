from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta48 marker missing: {name}")
    return s.replace(old, new, count)


def replace_any(s, candidates, new, name):
    for old in candidates:
        if old in s:
            return s.replace(old, new, 1)
    raise SystemExit(f"beta48 marker missing: {name}")

# Version only; score/recommendation math is intentionally unchanged.
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.47','APP_VERSION := 0.1.0-beta.48','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# RAM result graph UI/readability only.
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()

old_cluster='''            // Switch-like four-pad inspection control. The larger separated pads
            // mirror the physical four-button cluster without drawing a bulky D-pad.
            // Only Left/Right are active; Up/Down remain blank and muted.
            const int dcx=gx+46, dcy=y+116;
            const int sideW=34, sideH=26, vertW=26, vertH=34;
            const int lx=dcx-48, ly=dcy-sideH/2;
            const int rx=dcx+14, ry=ly;
            const int tx=dcx-vertW/2, ty=dcy-46;
            const int bx=tx, by=dcy+12;
            roundedBorder(tx,ty,vertW,vertH,11,C_BORDER,C_PANEL_2,1);
            roundedBorder(bx,by,vertW,vertH,11,C_BORDER,C_PANEL_2,1);
            roundedBorder(lx,ly,sideW,sideH,11,C_BLUE,C_PANEL_2,2);
            roundedBorder(rx,ry,sideW,sideH,11,C_BLUE,C_PANEL_2,2);
            // Minimal outlined chevrons instead of text glyphs.
            drawLine(lx+20,ly+7,lx+11,ly+13,C_TEXT,2);
            drawLine(lx+11,ly+13,lx+20,ly+19,C_TEXT,2);
            drawLine(rx+14,ry+7,rx+23,ry+13,C_TEXT,2);
            drawLine(rx+23,ry+13,rx+14,ry+19,C_TEXT,2);
            drawText(dcx+60,dcy-9,14,C_TEXT,"Inspect points");'''
new_cluster='''            // Tiny round four-button inspection cluster, matching the user's
            // reference. Only Left/Right are marked; Up/Down stay blank and muted.
            const int dcx=gx+34, dcy=y+112, dr=9, ds=13;
            fillCircle(dcx,dcy-ds,dr,C_BORDER); fillCircle(dcx,dcy-ds,dr-2,C_PANEL_2);
            fillCircle(dcx,dcy+ds,dr,C_BORDER); fillCircle(dcx,dcy+ds,dr-2,C_PANEL_2);
            fillCircle(dcx-ds,dcy,dr,C_BLUE);   fillCircle(dcx-ds,dcy,dr-2,C_PANEL_2);
            fillCircle(dcx+ds,dcy,dr,C_BLUE);   fillCircle(dcx+ds,dcy,dr-2,C_PANEL_2);
            drawLine(dcx-ds+3,dcy-4,dcx-ds-2,dcy,C_TEXT,2);
            drawLine(dcx-ds-2,dcy,dcx-ds+3,dcy+4,C_TEXT,2);
            drawLine(dcx+ds-3,dcy-4,dcx+ds+2,dcy,C_TEXT,2);
            drawLine(dcx+ds+2,dcy,dcx+ds-3,dcy+4,C_TEXT,2);
            drawText(dcx+32,dcy-8,15,C_TEXT,"Inspect points");'''
g=must_replace(g,old_cluster,new_cluster,'mini round four-button cluster')

# Larger legends.
g=must_replace(g,'            drawText(gx+541,y+103,13,C_TEXT,"RAM Score");','            drawText(gx+541,y+101,15,C_TEXT,"RAM Score");','RAM Score legend font')
g=must_replace(g,'            drawText(gx+701,y+103,13,C_TEXT,"SoC mV");','            drawText(gx+701,y+101,15,C_TEXT,"SoC mV");','SoC legend font')

# Larger EFF/PERF/MAX role markers, including the possible combined marker.
g=replace_any(g,[
    'drawText(std::max(gx,xx-30),gy-20,10,C_GREEN,"EFF+PERF")',
], 'drawText(std::max(gx,xx-36),gy-24,12,C_GREEN,"EFF+PERF")', 'EFF+PERF marker font')
g=replace_any(g,[
    'drawText(std::max(gx,xx-16),gy-20,11,C_GREEN,"EFF")',
    'drawText(std::max(gx,xx-18),gy-20,11,C_GREEN,"EFF")',
], 'drawText(std::max(gx,xx-20),gy-23,13,C_GREEN,"EFF")', 'EFF marker font')
g=replace_any(g,[
    'drawText(std::max(gx,xx-18),gy-20,11,C_GREEN,"PERF")',
    'drawText(std::max(gx,xx-20),gy-20,11,C_GREEN,"PERF")',
], 'drawText(std::max(gx,xx-23),gy-23,13,C_GREEN,"PERF")', 'PERF marker font')
g=replace_any(g,[
    'drawText(std::min(gx+gw-28,std::max(gx,xx-14)),gy-34,11,C_RED,"MAX")',
], 'drawText(std::min(gx+gw-34,std::max(gx,xx-17)),gy-38,13,C_RED,"MAX")', 'MAX marker font')

# Larger frequency labels. Accept either historical vertical offset.
g=replace_any(g,[
    'drawText(xx-textWidth(lab,10)/2,gy+gh+8,10,i==selected?C_TEXT:C_MUTED,lab);',
    'drawText(xx-textWidth(lab,10)/2,gy+gh+6,10,i==selected?C_TEXT:C_MUTED,lab);',
], 'drawText(xx-textWidth(lab,12)/2,gy+gh+8,12,i==selected?C_TEXT:C_MUTED,lab);', 'MHz label font')

# Selected point + recommendation line larger.
old_summary='''                drawText(gx,sy,12,C_TEXT,fitText(g_view.chartSummary,12,std::max(250,gw-500)));
                drawTextRight(gx+gw,sy,12,C_GREEN,rec);'''
new_summary='''                drawText(gx,sy,14,C_TEXT,fitText(g_view.chartSummary,14,std::max(280,gw-570)));
                drawTextRight(gx+gw,sy,14,C_GREEN,rec);'''
g=must_replace(g,old_summary,new_summary,'larger selected point and recommendation row')
p.write_text(g)

# -----------------------------------------------------------------------------
# Remove duplicate X action on RAM graph; A alone opens mandatory explanation.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()
m=must_replace(m,'            if((k&HidNpadButton_A)||(k&HidNpadButton_X)){g.stage=Stage::RamTargetExplanation;saveState();redraw=true;continue;}','            if(k&HidNpadButton_A){g.stage=Stage::RamTargetExplanation;saveState();redraw=true;continue;}','RAM graph A-only explanation input')
m=must_replace(m,'            print(9,"A : Continue to explanation");\n            print(10,"X : Show explanation");\n            print(11,"B : Exit");','            print(9,"A : Continue to explanation");\n            print(10,"B : Exit");','remove duplicate X graph action')
p.write_text(m)

# Audit: UI-only beta. Keep beta47 score + recommendation math intact.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta48 version':'0.1.0-beta.48' in Path('Makefile').read_text(),
    'mini round cluster':'const int dcx=gx+34, dcy=y+112, dr=9, ds=13' in gui,
    'round side buttons':'fillCircle(dcx-ds,dcy' in gui and 'fillCircle(dcx+ds,dcy' in gui,
    'round vertical buttons':'fillCircle(dcx,dcy-ds' in gui and 'fillCircle(dcx,dcy+ds' in gui,
    'inspect text retained':'Inspect points' in gui,
    'larger legends':'15,C_TEXT,"RAM Score"' in gui and '15,C_TEXT,"SoC mV"' in gui,
    'larger markers':'12,C_GREEN,"EFF+PERF"' in gui and '13,C_GREEN,"EFF"' in gui and '13,C_GREEN,"PERF"' in gui and '13,C_RED,"MAX"' in gui,
    'larger mhz labels':'textWidth(lab,12)' in gui,
    'larger summary recommendation':'drawText(gx,sy,14' in gui and 'drawTextRight(gx+gw,sy,14' in gui,
    'duplicate X graph action removed':'X : Show explanation' not in main,
    'A graph explanation retained':'if(k&HidNpadButton_A){g.stage=Stage::RamTargetExplanation' in main,
    'B graph exit retained':'print(10,"B : Exit")' in main,
    'benchmark score retained':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'raw composite gpu 35':'0.35*std::log(gpuGroup)' in eng,
    'raw composite cpu 35':'0.35*std::log(cpuGroup)' in eng,
    'raw composite ram latency 25':'0.25*std::log(ramLat)' in eng,
    'raw composite l2 5':'0.05*std::log(l2Lat)' in eng,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta48 source audit failed: '+', '.join(bad))
