from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta49 marker missing: {name}")
    return s.replace(old, new, count)


def replace_braced(src, marker, replacement):
    pos=src.find(marker)
    if pos<0:
        raise SystemExit(f"beta49 braced marker missing: {marker}")
    brace=src.find('{',pos)
    if brace<0:
        raise SystemExit(f"beta49 opening brace missing: {marker}")
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None:
        raise SystemExit(f"beta49 unbalanced: {marker}")
    return src[:pos]+replacement+src[end:]

# -----------------------------------------------------------------------------
# Version only; tuning, score and recommendation math remain unchanged.
# -----------------------------------------------------------------------------
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.48','APP_VERSION := 0.1.0-beta.49','version')
p.write_text(s)

# -----------------------------------------------------------------------------
# RAM result graph: use the free space instead of compressing the chart.
# - wider + taller plot
# - tiny inspection cluster remains in the header, clear of the plot
# - larger graph labels/markers
# - selected point and recommendations get their own separate lines
# -----------------------------------------------------------------------------
p=Path('source/gui_console.cpp'); g=p.read_text()

g=must_replace(g,
    '            const int gx=x+70, gy=y+150, gw=w-140, gh=130;',
    '            const int gx=x+48, gy=y+140, gw=w-96, gh=190;',
    'larger RAM graph geometry')

old_cluster='''            // Tiny round four-button inspection cluster, matching the physical
            // Switch four-button look without covering the graph. Only L/R are marked.
            const int dcx=gx+34, dcy=y+112, dr=9, ds=13;
            fillCircle(dcx,dcy-ds,dr,C_BORDER); fillCircle(dcx,dcy-ds,dr-2,C_PANEL_2);
            fillCircle(dcx,dcy+ds,dr,C_BORDER); fillCircle(dcx,dcy+ds,dr-2,C_PANEL_2);
            fillCircle(dcx-ds,dcy,dr,C_BLUE);   fillCircle(dcx-ds,dcy,dr-2,C_PANEL_2);
            fillCircle(dcx+ds,dcy,dr,C_BLUE);   fillCircle(dcx+ds,dcy,dr-2,C_PANEL_2);
            // Small outlined arrowheads inside the left/right round buttons.
            drawLine(dcx-ds+3,dcy-4,dcx-ds-2,dcy,C_TEXT,2);
            drawLine(dcx-ds-2,dcy,dcx-ds+3,dcy+4,C_TEXT,2);
            drawLine(dcx+ds-3,dcy-4,dcx+ds+2,dcy,C_TEXT,2);
            drawLine(dcx+ds+2,dcy,dcx+ds-3,dcy+4,C_TEXT,2);
            drawText(dcx+32,dcy-8,15,C_TEXT,"Inspect points");'''
new_cluster='''            // Tiny physical-button style hint. Keep it deliberately small and
            // entirely inside the header strip so it never covers chart data.
            const int dcx=gx+28, dcy=y+111, dr=8, ds=11;
            fillCircle(dcx,dcy-ds,dr,C_BORDER); fillCircle(dcx,dcy-ds,dr-2,C_PANEL_2);
            fillCircle(dcx,dcy+ds,dr,C_BORDER); fillCircle(dcx,dcy+ds,dr-2,C_PANEL_2);
            fillCircle(dcx-ds,dcy,dr,C_BLUE);   fillCircle(dcx-ds,dcy,dr-2,C_PANEL_2);
            fillCircle(dcx+ds,dcy,dr,C_BLUE);   fillCircle(dcx+ds,dcy,dr-2,C_PANEL_2);
            drawLine(dcx-ds+3,dcy-3,dcx-ds-2,dcy,C_TEXT,2);
            drawLine(dcx-ds-2,dcy,dcx-ds+3,dcy+3,C_TEXT,2);
            drawLine(dcx+ds-3,dcy-3,dcx+ds+2,dcy,C_TEXT,2);
            drawLine(dcx+ds+2,dcy,dcx+ds-3,dcy+3,C_TEXT,2);
            drawText(dcx+28,dcy-8,15,C_TEXT,"Inspect points");'''
g=must_replace(g,old_cluster,new_cluster,'smaller header inspection cluster')

# Give the legend more presence now that the graph has room.
g=must_replace(g,
    '            drawText(gx+541,y+101,15,C_TEXT,"RAM Score");',
    '            drawText(gx+500,y+100,16,C_TEXT,"RAM Score");',
    'RAM Score legend layout')
g=must_replace(g,
    '            drawText(gx+701,y+101,15,C_TEXT,"SoC mV");',
    '            drawText(gx+690,y+100,16,C_TEXT,"SoC mV");',
    'SoC legend layout')
# Move the legend swatches with their labels.
g=g.replace('roundedRect(gx+520,y+109,14,8,3,C_GREEN);','roundedRect(gx+477,y+108,14,8,3,C_GREEN);')
g=g.replace('roundedRect(gx+680,y+109,14,8,3,C_AMBER);','roundedRect(gx+667,y+108,14,8,3,C_AMBER);')

# More readable axis and role labels.
g=must_replace(g,
    'drawText(xx-textWidth(lab,12)/2,gy+gh+8,12,i==selected?C_TEXT:C_MUTED,lab);',
    'drawText(xx-textWidth(lab,13)/2,gy+gh+8,13,i==selected?C_TEXT:C_MUTED,lab);',
    'larger MHz labels')
g=g.replace('13,C_GREEN,"EFF"','14,C_GREEN,"EFF"')
g=g.replace('13,C_GREEN,"PERF"','14,C_GREEN,"PERF"')
g=g.replace('13,C_RED,"MAX"','14,C_RED,"MAX"')

# Selected point and recommendation are no longer squeezed onto one line.
old_summary='''            if(!g_view.chartSummary.empty()){
                const int sy=gy+gh+27;
                const std::string rec="Recommended for: Efficiency "+std::to_string(g_view.chartEfficiencyMHz)+" MHz   |   Performance "+std::to_string(g_view.chartPerformanceMHz)+" MHz";
                drawText(gx,sy,14,C_TEXT,fitText(g_view.chartSummary,14,std::max(280,gw-570)));
                drawTextRight(gx+gw,sy,14,C_GREEN,rec);
            }'''
new_summary='''            if(!g_view.chartSummary.empty()){
                const int sy=gy+gh+28;
                const std::string rec="Recommended for: Efficiency "+std::to_string(g_view.chartEfficiencyMHz)+" MHz   |   Performance "+std::to_string(g_view.chartPerformanceMHz)+" MHz";
                drawText(gx,sy,15,C_TEXT,fitText(g_view.chartSummary,15,gw));
                drawText(gx,sy+21,15,C_GREEN,fitText(rec,15,gw));
            }'''
g=must_replace(g,old_summary,new_summary,'separate graph result lines')
p.write_text(g)

# -----------------------------------------------------------------------------
# RAM target explanation: full-width page, no YOUR TASK box. Replace the older
# technical wording with a concise explanation of both recommendations and make
# the consequence of the upcoming VDD2/VDDQ tuning explicit.
# -----------------------------------------------------------------------------
p=Path('source/main_oc.cpp'); m=p.read_text()
new_explanation=r'''case Stage::RamTargetExplanation:{
            refreshRamSuggestedTarget();
            v.stageTitle="Choosing Your RAM Target";
            v.fullWidthLayout=true;
            v.hideValuesCard=true;
            v.instructionTitle="";v.instructionLine1="";v.instructionLine2="";
            gui::begin(v);
            print(1,"The Wizard found two recommended RAM targets:");
            print(3,"Efficiency: "+std::to_string(g.ramEfficiencyRecommendedMHz)+" MHz");
            print(4,"Best balance between RAM performance and voltage. Choosing this target can allow lower VDD2 and VDDQ in the next steps.");
            print(6,"Performance: "+std::to_string(g.ramRecommendedMHz)+" MHz");
            print(7,"A higher RAM target focused on performance. It stays close to Stable Max while avoiding steps that require disproportionately more voltage for only negligible additional performance.");
            print(9,"Your choice sets the maximum RAM clock for this profile.");
            print(10,"In the next steps, VDD2 and VDDQ are tuned specifically for that target.");
            print(12,"Important: After VDD2/VDDQ tuning, RAM clocks above your selected target should no longer be used. The optimized voltages may make those higher clocks unstable.");
            print(13,"To use a higher RAM clock later, VDD2/VDDQ must be tuned again for that higher target.");
            print(15,"A : Continue to RAM Target Selection");
            print(16,"X : Back to graph");
            print(17,"B : Exit");
            gui::present();break;}'''
m=replace_braced(m,'case Stage::RamTargetExplanation:',new_explanation)
p.write_text(m)

# -----------------------------------------------------------------------------
# Audit: presentation only. Preserve beta47 RAM Score and beta43 recommendation
# algorithms exactly.
# -----------------------------------------------------------------------------
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta49 version':'0.1.0-beta.49' in Path('Makefile').read_text(),
    'larger graph':'gx=x+48' in gui and 'gy=y+140' in gui and 'gw=w-96' in gui and 'gh=190' in gui,
    'mini cluster retained':'const int dcx=gx+28, dcy=y+111, dr=8, ds=11' in gui and 'Inspect points' in gui,
    'larger graph labels':'textWidth(lab,13)' in gui and '16,C_TEXT,"RAM Score"' in gui and '16,C_TEXT,"SoC mV"' in gui,
    'separate result rows':'drawText(gx,sy,15' in gui and 'drawText(gx,sy+21,15,C_GREEN' in gui,
    'full width explanation':'case Stage::RamTargetExplanation' in main and 'v.fullWidthLayout=true' in main,
    'task box disabled':'v.instructionTitle=""' in main,
    'efficiency wording':'Best balance between RAM performance and voltage' in main,
    'performance wording':'only negligible additional performance' in main,
    'higher clocks consequence':'RAM clocks above your selected target should no longer be used' in main,
    'retune higher target':'VDD2/VDDQ must be tuned again for that higher target' in main,
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
if bad: raise SystemExit('Beta49 source audit failed: '+', '.join(bad))
