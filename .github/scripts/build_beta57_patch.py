from pathlib import Path
import re


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta57 marker missing: {name}")
    return s.replace(old, new, count)


def find_braced_block(src, marker):
    pos = src.find(marker)
    if pos < 0:
        raise SystemExit(f"beta57 block marker missing: {marker}")
    brace = src.find('{', pos)
    if brace < 0:
        raise SystemExit(f"beta57 opening brace missing: {marker}")
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
        raise SystemExit(f"beta57 unbalanced block: {marker}")
    return pos, end, src[pos:end]


def find_case_block(src, needle):
    pos = src.find(needle)
    if pos < 0:
        raise SystemExit(f"beta57 target marker missing: {needle}")
    start = src.rfind('case Stage::', 0, pos)
    if start < 0:
        raise SystemExit('beta57 enclosing target case missing')
    brace = src.find('{', start)
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
        raise SystemExit('beta57 target case unbalanced')
    return start, end, src[start:end]


# Version only. No tuning, benchmark, score or recommendation math changes.
p = Path('Makefile')
s = p.read_text()
s = must_replace(s, 'APP_VERSION := 0.1.0-beta.56', 'APP_VERSION := 0.1.0-beta.57', 'version')
p.write_text(s)

# -----------------------------------------------------------------------------
# RAM target pages / selection behavior.
# -----------------------------------------------------------------------------
p = Path('source/main_oc.cpp')
m = p.read_text()

# User wants the practical result stated clearly, not conditionally.
m = must_replace(
    m,
    'Lower VDD2/VDDQ can reduce overall RAM temperatures and power consumption.',
    'Lower VDD2/VDDQ will reduce overall RAM temperatures and power consumption.',
    'will reduce wording')

# Force the actual RAM target case to carry both fixed task lines.
start, end, target = find_case_block(m, 'Choose RAM Target')
target, n1 = re.subn(
    r'v\.instructionLine1\s*=\s*"[^"]*"\s*;',
    'v.instructionLine1="Use the Left / Right buttons";',
    target,
    count=1)
target, n2 = re.subn(
    r'v\.instructionLine2\s*=\s*"[^"]*"\s*;',
    'v.instructionLine2="to select your target frequency.";',
    target,
    count=1)
if n1 == 0 or n2 == 0:
    raise SystemExit('beta57 RAM target task assignments missing')
m = m[:start] + target + m[end:]

# X from RAM target selection must always reopen explanation page 1/2.
pos, end, input_block = find_braced_block(m, 'if(g.stage==Stage::RamTargetSelect){')
if 'g.stage=Stage::RamTargetExplanation;' not in input_block:
    raise SystemExit('beta57 RAM target back transition missing')
input_block = input_block.replace(
    'g.stage=Stage::RamTargetExplanation;',
    'g_ramTargetExplanationPage=0;g.stage=Stage::RamTargetExplanation;',
    1)
m = m[:pos] + input_block + m[end:]
p.write_text(m)

# -----------------------------------------------------------------------------
# Task card: for RAM target selection render line 2 as a real second prose line,
# not as the generic highlighted lower card. This guarantees both lines are visible.
# Move Inspect points further left to the user-marked free region.
# -----------------------------------------------------------------------------
p = Path('source/gui_console.cpp')
g = p.read_text()

old_task = '''    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));\n\n    roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));\n    drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));'''
new_task = '''    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));\n\n    if (g_view.instructionTitle == "Choose your RAM target") {\n        drawText(x + 24, y + 116, 16, C_MUTED, fitText(g_view.instructionLine2, 16, w - 48));\n    } else {\n        roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));\n        drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));\n    }'''
g = must_replace(g, old_task, new_task, 'RAM target task two-line renderer')

g = must_replace(
    g,
    'const int dcx=gx+300, dcy=y+111, dr=8, ds=11;',
    'const int dcx=gx+200, dcy=y+111, dr=8, ds=11;',
    'Inspect points user-marked position')
p.write_text(g)

# -----------------------------------------------------------------------------
# Presentation-only audit plus logic-preservation checks.
# -----------------------------------------------------------------------------
main = Path('source/main_oc.cpp').read_text()
gui = Path('source/gui_console.cpp').read_text()
eng = Path('source/oc_engine.cpp').read_text()
stress = Path('source/stress_tests.cpp').read_text()
_, _, target = find_case_block(main, 'Choose RAM Target')
_, _, select_input = find_braced_block(main, 'if(g.stage==Stage::RamTargetSelect){')
perf_start = main.find('int findRamSuggestedTargetIndex()')
perf_end = main.find('void refreshRamSuggestedTarget()', perf_start)
rec_region = main[perf_start:perf_end] if perf_start >= 0 and perf_end > perf_start else ''
checks = {
    'beta57 version': '0.1.0-beta.57' in Path('Makefile').read_text(),
    'will reduce wording': 'Lower VDD2/VDDQ will reduce overall RAM temperatures and power consumption.' in main,
    'old can reduce wording gone': 'Lower VDD2/VDDQ can reduce overall RAM temperatures and power consumption.' not in main,
    'target task line 1 scoped': 'v.instructionLine1="Use the Left / Right buttons"' in target,
    'target task line 2 scoped': 'v.instructionLine2="to select your target frequency."' in target,
    'target task special renderer': 'g_view.instructionTitle == "Choose your RAM target"' in gui,
    'target second prose line visible': 'drawText(x + 24, y + 116, 16, C_MUTED, fitText(g_view.instructionLine2, 16, w - 48));' in gui,
    'generic task renderer retained': 'roundedRect(x + 22, y + 126, w - 44, 54, 12' in gui and 'y + 137, 25, C_CYAN' in gui,
    'back resets explanation page': 'g_ramTargetExplanationPage=0;g.stage=Stage::RamTargetExplanation;' in select_input,
    'two-page explanation retained': 'Choosing Your RAM Target (1/2)' in main and 'Choosing Your RAM Target (2/2)' in main,
    'Inspect points moved left': 'const int dcx=gx+200, dcy=y+111, dr=8, ds=11' in gui,
    'Inspect points text retained': 'Inspect points' in gui,
    'real indentation retained': '@INDENT@' in main and 'drawWrappedText(x + 68' in gui,
    'more-details suppression retained': 'startsWith(g_view.stageTitle, "Choosing Your RAM Target")' in gui,
    'score formula retained': 'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw': 'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug retained': 'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained': 'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained': 'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'raw composite retained': '0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng and '0.25*std::log(ramLat)' in eng and '0.05*std::log(l2Lat)' in eng,
}
for name, ok in checks.items():
    print(('PASS ' if ok else 'FAIL ') + name)
bad = [name for name, ok in checks.items() if not ok]
if bad:
    raise SystemExit('Beta57 source audit failed: ' + ', '.join(bad))
