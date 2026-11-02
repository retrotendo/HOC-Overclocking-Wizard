from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta26 marker missing: {name}")
    return s.replace(old, new, count)

# Version only. No tuning-state/methodology changes in this patch.
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.25','APP_VERSION := 0.1.0-beta.26','version')
p.write_text(s)

p=Path('source/gui_console.cpp')
g=p.read_text()

# drawInstructionCard needs the wrapping helper before its definition.
progress_end='''}\n\nvoid drawInstructionCard() {'''
wrapped_decl='''}\n\nint drawWrappedText(int x, int y, int size, u32 color, const std::string& text,\n                    int maxWidth, int lineHeight, int maxLines);\n\nvoid drawInstructionCard() {'''
g=must_replace(g,progress_end,wrapped_decl,'wrapped text declaration before task card')

# Global YOUR TASK policy: wrap title/subtitle inside the card; never render action hints here.
old_task='''void drawInstructionCard() {\n    const int x = 835, y = 158, w = 405, h = 205;\n    drawCard(x, y, w, h, true);\n    drawLabel(x + 24, y + 20, "YOUR TASK");\n    drawText(x + 24, y + 52, 23, C_TEXT,\n             fitText(g_view.instructionTitle.empty() ? "Continue Wizard" : g_view.instructionTitle, 23, w - 48));\n    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));\n\n    roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));\n    drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));\n}'''
new_task='''void drawInstructionCard() {\n    const int x = 835, y = 158, w = 405, h = 205;\n    drawCard(x, y, w, h, true);\n    drawLabel(x + 24, y + 20, "YOUR TASK");\n\n    int ty = y + 48;\n    ty = drawWrappedText(x + 24, ty, 22, C_TEXT,\n        g_view.instructionTitle.empty() ? "Continue Wizard" : g_view.instructionTitle,\n        w - 48, 28, 3);\n\n    if (!g_view.instructionLine1.empty() && ty < y + h - 30) {\n        ty += 10;\n        drawWrappedText(x + 24, ty, 15, C_MUTED, g_view.instructionLine1,\n                        w - 48, 21, 3);\n    }\n}'''
g=must_replace(g,old_task,new_task,'global wrapped YOUR TASK card')

# Remove the now-redundant later forward declaration.
late_decl='''\nint drawWrappedText(int x, int y, int size, u32 color, const std::string& text,\n                    int maxWidth, int lineHeight, int maxLines);\n\nvoid drawMainCard() {'''
g=must_replace(g,late_decl,'\nvoid drawMainCard() {','remove duplicate wrapped text declaration')

# Global main-card vertical rhythm. Give every logical item visible breathing room.
g=must_replace(g,'by += 26;\n                ++shown;','by += 34;\n                ++shown;','heading spacing')
g=must_replace(g,'by += 22;\n                ++shown;','by += 31;\n                ++shown;','numbered-row spacing')
g=must_replace(g,'by += 31;\n            } else {','by += 40;\n            } else {','value-row spacing')
g=must_replace(g,'by = drawWrappedText(x + 28, by, 17, C_TEXT, raw, w - 56, 25, 3);\n                by += 5;','by = drawWrappedText(x + 28, by, 17, C_TEXT, raw, w - 56, 27, 3);\n                by += 13;','prose spacing')

# Preparation explanatory prose gets the same visual breathing room.
g=g.replace('by += 12;\n            drawWrappedText(x + 28, by, 17, C_MUTED,','by += 18;\n            drawWrappedText(x + 28, by, 17, C_MUTED,')

p.write_text(g)

# Audit generated source: UI-only patch and global renderer rules.
main=Path('source/main_oc.cpp').read_text()
gui=p.read_text()
start=gui.find('void drawInstructionCard()')
end=gui.find('void drawPreparationCard()',start)
task=gui[start:end]
checks={
    'beta26 version':'0.1.0-beta.26' in Path('Makefile').read_text(),
    'task title wraps':'drawWrappedText(x + 24, ty, 22' in task,
    'task subtitle wraps':'drawWrappedText(x + 24, ty, 15' in task,
    'task no ellipsis fitText':'fitText(g_view.instructionTitle' not in task,
    'task no duplicate action line':'instructionLine2' not in task,
    'global prose breathing room':'w - 56, 27, 3' in gui and 'by += 13;' in gui,
    'global value-row breathing room':'by += 40;' in gui,
    'global numbered-row breathing room':'by += 31;' in gui,
    'global heading breathing room':'by += 34;' in gui,
    'beta25 current baseline retained':'Use current values as baseline' in main and 'baselineCustom' in main,
    'beta24 benchmark stage retained':'RamBenchmark' in main,
    'beta22 force shortcuts retained':'HidNpadButton_Plus' in Path('source/stress_tests.cpp').read_text() and 'HidNpadButton_Minus' in Path('source/stress_tests.cpp').read_text(),
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad: raise SystemExit('Beta26 source audit failed: '+', '.join(bad))
