from pathlib import Path

p=Path('source/gui_console.cpp')
s=p.read_text()
s=s.replace('constexpr u32 C_CYAN      = RGBA8_MAXALPHA(35, 211, 238);','constexpr u32 C_CYAN      = RGBA8_MAXALPHA(249, 115, 22);')
s=s.replace('constexpr u32 C_CYAN_DIM  = RGBA8_MAXALPHA(15, 105, 125);','constexpr u32 C_CYAN_DIM  = RGBA8_MAXALPHA(139, 52, 13);')
s=s.replace('drawText(198, 24, 24, C_TEXT, "Undervolting Wizard");','drawText(198, 24, 24, C_TEXT, "Overclocking Wizard");')
s=s.replace('static const char* labels[7] = {"Baseline", "Low UV", "Low VMIN", "VDDQ", "VDD2", "High UV", "Finalize"};','static const char* labels[7] = {"Prepare", "RAM", "RAM Tune", "GPU", "CPU", "Combined", "Finalize"};')
s=s.replace('drawCentered(y + 124, 20, C_GREEN, "UNDERVOLTING COMPLETE");','drawCentered(y + 124, 20, C_GREEN, "OVERCLOCKING COMPLETE");')
s=s.replace('raw == "UNDERVOLTING COMPLETE"','raw == "OVERCLOCKING COMPLETE"')

needle='''void fillCircle(int cx, int cy, int r, u32 color) {\n    for (int y = -r; y <= r; ++y) {\n        const int xx = int(std::sqrt(double(std::max(0, r * r - y * y))));\n        fillRect(cx - xx, cy + y, xx * 2 + 1, 1, color);\n    }\n}\n'''
insert=needle+'''\nvoid drawLine(int x0, int y0, int x1, int y1, u32 color, int thickness = 2) {\n    int dx = std::abs(x1-x0), sx = x0<x1 ? 1 : -1;\n    int dy = -std::abs(y1-y0), sy = y0<y1 ? 1 : -1;\n    int err = dx + dy;\n    for (;;) {\n        fillRect(x0-thickness/2, y0-thickness/2, thickness, thickness, color);\n        if (x0==x1 && y0==y1) break;\n        const int e2 = 2*err;\n        if (e2 >= dy) { err += dy; x0 += sx; }\n        if (e2 <= dx) { err += dx; y0 += sy; }\n    }\n}\n'''
if 'void drawLine(int x0' not in s:
    s=s.replace(needle,insert)

old='''    const bool completeSummary = g_view.fullWidthLayout && g_view.stageTitle == "Complete";\n    if (completeSummary) {'''
new='''    const bool completeSummary = g_view.fullWidthLayout && g_view.stageTitle == "Complete";\n    if (g_view.chartLayout && !g_view.chartPoints.empty()) {\n        const int gx = x + 76, gy = y + 142, gw = w - 152, gh = 260;\n        drawText(gx, y + 112, 18, C_CYAN, g_view.chartTitle.empty() ? "Measured tuning curve" : g_view.chartTitle);\n        fillRect(gx, gy + gh, gw, 1, C_BORDER);\n        fillRect(gx, gy, 1, gh, C_BORDER);\n\n        double minX=g_view.chartPoints.front().x, maxX=minX;\n        double minP=g_view.chartPoints.front().performance, maxP=minP;\n        double minC=1e30, maxC=-1e30;\n        for (const auto& q : g_view.chartPoints) {\n            minX=std::min(minX,q.x); maxX=std::max(maxX,q.x);\n            minP=std::min(minP,q.performance); maxP=std::max(maxP,q.performance);\n            const double c=q.power>0.01 ? q.power : q.voltage;\n            if(c>0){minC=std::min(minC,c);maxC=std::max(maxC,c);}\n        }\n        if(maxX<=minX) maxX=minX+1; if(maxP<=minP) maxP=minP+1;\n        if(maxC<=minC || minC>1e20){minC=0;maxC=1;}\n        auto px=[&](double v){return gx+int((v-minX)/(maxX-minX)*gw);};\n        auto pyP=[&](double v){return gy+gh-int((v-minP)/(maxP-minP)*gh);};\n        auto pyC=[&](double v){return gy+gh-int((v-minC)/(maxC-minC)*gh);};\n\n        for(int k=1;k<4;++k){int yy=gy+gh*k/4;fillRect(gx,yy,gw,1,mix(C_BG,C_BORDER,55));}\n        for(size_t i=1;i<g_view.chartPoints.size();++i){\n            const auto&a=g_view.chartPoints[i-1]; const auto&b=g_view.chartPoints[i];\n            drawLine(px(a.x),pyP(a.performance),px(b.x),pyP(b.performance),C_GREEN,2);\n            const double ac=a.power>0.01?a.power:a.voltage, bc=b.power>0.01?b.power:b.voltage;\n            drawLine(px(a.x),pyC(ac),px(b.x),pyC(bc),C_AMBER,2);\n        }\n        for(const auto&q:g_view.chartPoints){\n            u32 c=q.stable?C_TEXT:C_RED; int r=4;\n            if(q.stableMax){c=C_RED;r=6;}\n            if(q.sweetSpot){c=C_AMBER;r=7;}\n            if(q.recommended){c=C_GREEN;r=8;}\n            fillCircle(px(q.x),pyP(q.performance),r,c);\n        }\n        drawText(gx, gy+gh+18, 14, C_MUTED, g_view.chartXLabel);\n        drawText(gx, gy+gh+45, 14, C_GREEN, "Performance");\n        drawText(gx+125, gy+gh+45, 14, C_AMBER, g_view.chartCostLabel.empty()?"Voltage / Power":g_view.chartCostLabel);\n        drawText(gx+310, gy+gh+45, 14, C_GREEN, "Recommended");\n        drawText(gx+455, gy+gh+45, 14, C_RED, "Stable Max");\n        if(!g_view.chartSummary.empty())\n            drawWrappedText(gx, gy+gh+72, 16, C_TEXT, g_view.chartSummary, gw, 23, 3);\n    } else if (completeSummary) {'''
if old not in s:
    raise SystemExit('chart insertion point not found')
s=s.replace(old,new)
p.write_text(s)

p=Path('source/updater.cpp')
s=p.read_text()
s=s.replace('retrotendo/HOC-Undervolting-Wizard','retrotendo/HOC-Overclocking-Wizard')
s=s.replace('HOC-Undervolting-Wizard.nro.sha256','HOC-Overclocking-Wizard.nro.sha256')
s=s.replace('HOC-Undervolting-Wizard.nro','HOC-Overclocking-Wizard.nro')
s=s.replace('sdmc:/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro','sdmc:/switch/HOC-Overclocking-Wizard/HOC-Overclocking-Wizard.nro')
s=s.replace('HOC-Undervolting-Wizard-Updater/1.0','HOC-Overclocking-Wizard-Updater/1.0')
p.write_text(s)
