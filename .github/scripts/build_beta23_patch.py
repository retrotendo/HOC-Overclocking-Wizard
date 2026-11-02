from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta23 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.22','APP_VERSION := 0.1.0-beta.23','version')
p.write_text(s)

# RAM Max Clock Search: YOUR TASK contains only the task itself.
# All controller actions remain on the left side of the Wizard.
p=Path('source/main_oc.cpp')
s=p.read_text()
old='''case Stage::RamSweep:{v.stageTitle="RAM Max Clock Search";v.instructionTitle="Start the automatic RAM clock search";v.instructionLine1="Press A to start. The Wizard handles the frequency steps automatically.";v.instructionLine2="";'''
new='''case Stage::RamSweep:{v.stageTitle="RAM Max Clock Search";v.instructionTitle="Start the automatic RAM Max Clock Search";v.instructionLine1="";v.instructionLine2="";'''
s=must_replace(s,old,new,'RAM Max Clock task wording')
p.write_text(s)

# Audit generated source before compiling.
main=Path('source/main_oc.cpp').read_text()
make=Path('Makefile').read_text()
start=main.find('case Stage::RamSweep:')
end=main.find('case Stage::RamSweepResult:',start)
section=main[start:end]
checks={
    'beta23 version':'0.1.0-beta.23' in make,
    'task title exact':'v.instructionTitle="Start the automatic RAM Max Clock Search"' in section,
    'task subtitle empty':'v.instructionLine1=""' in section,
    'no Press A in right task':'Press A to start' not in section,
    'left action retained':'A : Start automatic sweep' in section,
    'beta22 SoC curve retained':'socTuneIndex' in main and 'storeSocForTable' in main,
    'private force pass retained':'HidNpadButton_Plus' in Path('source/stress_tests.cpp').read_text(),
    'private force fail retained':'HidNpadButton_Minus' in Path('source/stress_tests.cpp').read_text(),
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad: raise SystemExit('Beta23 source audit failed: '+', '.join(bad))
