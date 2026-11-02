from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta26 marker missing: {name}")
    return s.replace(old, new, count)


def replace_function(src, signature, replacement):
    pos=src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta26 function missing: {signature}")
    brace=src.find('{',pos)
    depth=0; end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1; break
    if end is None:
        raise SystemExit(f"beta26 unbalanced function: {signature}")
    return src[:pos]+replacement+src[end:]

# Version only. No tuning-state/methodology changes in this patch.
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.25','APP_VERSION := 0.1.0-beta.26','version')
p.write_text(s)

p=Path('source/gui_console.cpp')
g=p.read_text()

# drawInstructionCard needs the wrapping helper declared before its definition.
funcpos=g.find('void drawInstructionCard()')
if funcpos < 0: raise SystemExit('beta26 drawInstructionCard missing')
pre=g[:funcpos]
if 'int drawWrappedText(int x, int y, int size' not in pre:
    decl='''int drawWrappedText(int x, int y, int size, u32 color, const std::string& text,\n                    int maxWidth, int lineHeight, int maxLines);\n\n'''
    g=g[:funcpos]+decl+g[funcpos:]

# Global YOUR TASK policy: wrap title/subtitle inside the card; never render action hints here.
new_task=r'''void drawInstructionCard() {
    const int x = 835, y = 158, w = 405, h = 205;
    drawCard(x, y, w, h, true);
    drawLabel(x + 24, y + 20, "YOUR TASK");

    int ty = y + 48;
    ty = drawWrappedText(x + 24, ty, 22, C_TEXT,
        g_view.instructionTitle.empty() ? "Continue Wizard" : g_view.instructionTitle,
        w - 48, 28, 3);

    if (!g_view.instructionLine1.empty() && ty < y + h - 30) {
        ty += 10;
        drawWrappedText(x + 24, ty, 15, C_MUTED, g_view.instructionLine1,
                        w - 48, 21, 3);
    }
}'''
g=replace_function(g,'void drawInstructionCard()',new_task)

# Remove a later duplicate forward declaration if present.
late='''\nint drawWrappedText(int x, int y, int size, u32 color, const std::string& text,\n                    int maxWidth, int lineHeight, int maxLines);\n\nvoid drawMainCard() {'''
if late in g:
    g=g.replace(late,'\nvoid drawMainCard() {',1)

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
