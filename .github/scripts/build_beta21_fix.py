from pathlib import Path

# YOUR TASK is instruction-only. Buttons/actions stay on the left.
p=Path('source/gui_console.cpp')
s=p.read_text()
start=s.find('void drawInstructionCard()')
if start < 0:
    raise SystemExit('beta21 drawInstructionCard missing')
end=s.find('\n}\n', start)
if end < 0:
    raise SystemExit('beta21 drawInstructionCard end missing')
end += 3
block=s[start:end]
lines=[]
for line in block.splitlines(True):
    if 'roundedRect(x + 22, y + 126' in line:
        continue
    if 'g_view.instructionLine2' in line:
        continue
    lines.append(line)
newblock=''.join(lines)
s=s[:start]+newblock+s[end:]
p.write_text(s)

# Temporary private testing shortcuts for this beta only.
# ZL + ZR + Plus  = force PASS
# ZL + ZR + Minus = force FAIL
# They are intentionally not shown anywhere in the normal UI.
p=Path('source/stress_tests.cpp')
t=p.read_text()
old='''    bool cancelled = false;\n    bool powerLost = false;'''
new='''    bool cancelled = false;\n    bool powerLost = false;\n    bool developerForcePass = false;\n    bool developerForceFail = false;'''
if old not in t:
    raise SystemExit('beta21 stress state marker missing')
t=t.replace(old,new,1)

old='''        padUpdate(&pad);\n        const u64 down = padGetButtonsDown(&pad);\n        if (down & HidNpadButton_B) {\n            cancelled = true;\n            break;\n        }'''
new='''        padUpdate(&pad);\n        const u64 down = padGetButtonsDown(&pad);\n        const u64 held = padGetButtons(&pad);\n        const u64 devChord = HidNpadButton_ZL | HidNpadButton_ZR;\n        if ((held & devChord) == devChord && (down & HidNpadButton_Plus)) {\n            developerForcePass = true;\n            break;\n        }\n        if ((held & devChord) == devChord && (down & HidNpadButton_Minus)) {\n            developerForceFail = true;\n            break;\n        }\n        if (down & HidNpadButton_B) {\n            cancelled = true;\n            break;\n        }'''
if old not in t:
    raise SystemExit('beta21 stress input marker missing')
t=t.replace(old,new,1)

old='''    if (powerLost) {\n        out.outcome = Outcome::PowerLost;\n        out.detail = chargerError.empty() ? powerguard::kDisconnected : chargerError;\n    } else if (cancelled) {'''
new='''    if (developerForcePass) {\n        out.outcome = Outcome::Pass;\n        out.errors = 0;\n        out.mismatches = 0;\n        out.detail = "Developer shortcut: forced PASS.";\n    } else if (developerForceFail) {\n        out.outcome = Outcome::Fail;\n        out.errors = 1;\n        out.detail = "Developer shortcut: forced FAIL.";\n    } else if (powerLost) {\n        out.outcome = Outcome::PowerLost;\n        out.detail = chargerError.empty() ? powerguard::kDisconnected : chargerError;\n    } else if (cancelled) {'''
if old not in t:
    raise SystemExit('beta21 stress result marker missing')
t=t.replace(old,new,1)
p.write_text(t)

# Remove remaining internal/developer explanations that do not help the user act.
p=Path('source/main_oc.cpp')
m=p.read_text()
replacements={
    'The split is selected only after Low and High curves are known.':'The Wizard will compare the available TBreak settings.',
    'This is tuned after TBreak so the lower High anchor is known.':'The Wizard will lower High VMIN step by step.',
    'A lower Real Clock means the cap is too low; that is not a successful undervolt.':'The requested CPU clock must stay active during the test.',
    'Base RAM is used here so a high-RAM DVFS floor cannot hide the intrinsic GPU curve.':'The Wizard will test each GPU clock and find its lowest stable voltage.',
    'A High UV level is accepted only if all retained High CPU points pass with final RAM.':'The Wizard will test stronger High UV levels until the first failure.',
    'Low UV is not judged from one idle/low clock. Both ends of the Low curve must work.':'The Wizard will test stronger Low UV levels until the first failure.',
}
for a,b in replacements.items():
    m=m.replace(a,b)
p.write_text(m)

# Audit final generated beta21 source.
gui=Path('source/gui_console.cpp').read_text()
stress=Path('source/stress_tests.cpp').read_text()
main=Path('source/main_oc.cpp').read_text()
card_start=gui.find('void drawInstructionCard()')
card_end=gui.find('\n}\n',card_start)+3
card=gui[card_start:card_end]
checks={
    'task card has no duplicate action button':'instructionLine2' not in card and 'y + 126' not in card,
    'developer pass shortcut':'HidNpadButton_ZL | HidNpadButton_ZR' in stress and 'HidNpadButton_Plus' in stress and 'developerForcePass' in stress,
    'developer fail shortcut':'HidNpadButton_Minus' in stress and 'developerForceFail' in stress,
    'shortcuts hidden from normal UI':'Force PASS' not in gui and 'Force FAIL' not in gui,
    'simple RAM timing copy':'So far, the Wizard used standard RAM timings.' in main,
    'stage-specific timing values':'v.valueCount=8' in main and '"tREFI"' in main,
}
for n,o in checks.items():
    print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad:
    raise SystemExit('Beta21 fix audit failed: '+', '.join(bad))
