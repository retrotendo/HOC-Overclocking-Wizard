from pathlib import Path
import re


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta51 marker missing: {name}")
    return s.replace(old, new, count)


def find_case_block(src, needle):
    pos=src.find(needle)
    if pos<0:
        raise SystemExit(f"beta51 target marker missing: {needle}")
    start=src.rfind('case Stage::',0,pos)
    if start<0:
        raise SystemExit('beta51 enclosing case not found')
    brace=src.find('{',start)
    if brace<0:
        raise SystemExit('beta51 opening brace not found')
    depth=0
    end=None
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:
                end=i+1
                break
    if end is None:
        raise SystemExit('beta51 unbalanced target case')
    return start,end,src[start:end]


# Version only. No tuning, score, benchmark or recommendation math changes.
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.50','APP_VERSION := 0.1.0-beta.51','version')
p.write_text(s)

p=Path('source/main_oc.cpp'); m=p.read_text()
start,end,block=find_case_block(m,'Choose RAM Target')
original=block

# Remove the redundant recommendation row from the left content area.
# Keep any non-UI recommendation logic intact.
lines=block.splitlines(True)
filtered=[]
for line in lines:
    ui_call=('print(' in line or 'drawText(' in line)
    redundant_eff=ui_call and ('"Efficiency"' in line or 'ramEfficiencyRecommendedMHz' in line)
    old_hint=ui_call and ('Use Left / Right' in line or 'Use the Left / Right' in line)
    if redundant_eff or old_hint:
        continue
    filtered.append(line)
block=''.join(filtered)

# Put the Left/Right guidance in YOUR TASK, explicitly saying buttons.
title='Choose your RAM target'
line1='Use the Left / Right buttons to inspect and'
line2='select another measured stable RAM point.'

# Replace existing task strings when present.
block,n1=re.subn(r'v\.instructionTitle\s*=\s*"[^"]*"\s*;',f'v.instructionTitle="{title}";',block,count=1)
block,n2=re.subn(r'v\.instructionLine1\s*=\s*"[^"]*"\s*;',f'v.instructionLine1="{line1}";',block,count=1)
block,n3=re.subn(r'v\.instructionLine2\s*=\s*"[^"]*"\s*;',f'v.instructionLine2="{line2}";',block,count=1)

# If this older block had only a title assignment, inject both lines after it.
if n1==0:
    raise SystemExit('beta51 task title assignment not found in RAM target case')
if n2==0 or n3==0:
    marker=f'v.instructionTitle="{title}";'
    insert='\n            v.instructionLine1="'+line1+'";\n            v.instructionLine2="'+line2+'";'
    block=block.replace(marker,marker+insert,1)

m=m[:start]+block+m[end:]
p.write_text(m)

# Presentation-only audit.
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text()
_,_,target=find_case_block(main,'Choose RAM Target')
perf_start=main.find('int findRamSuggestedTargetIndex()'); perf_end=main.find('void refreshRamSuggestedTarget()',perf_start)
rec_region=main[perf_start:perf_end] if perf_start>=0 and perf_end>perf_start else ''
checks={
    'beta51 version':'0.1.0-beta.51' in Path('Makefile').read_text(),
    'task title':'v.instructionTitle="Choose your RAM target"' in target,
    'task left right buttons':'Use the Left / Right buttons to inspect and' in target and 'select another measured stable RAM point.' in target,
    'old left right hint removed':'Use Left / Right to inspect' not in target,
    'efficiency row removed':not any(('print(' in ln or 'drawText(' in ln) and ('"Efficiency"' in ln or 'ramEfficiencyRecommendedMHz' in ln) for ln in target.splitlines()),
    'selected target retained':'Selected Target' in target,
    'RAM score retained':'RAM Score' in target,
    'SoC retained':'SoC' in target,
    'beta50 explanation retained':'only negligible additional performance' in main and 'retune VDD2/VDDQ for that higher target' in main,
    'score formula retained':'bandwidth/p.latencyNs' in main and '1000.0*raw/base' in main,
    'recommendation remains raw':'ramDisplayScore' not in rec_region and '.performance' in rec_region,
    'hidden debug retained':'debugChord=HidNpadButton_ZL | HidNpadButton_ZR' in main and 'B : Back to RAM graph' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
    'graph beta49 retained':'gh=190' in gui and 'Recommended for:' in gui,
    'raw composite retained':'0.35*std::log(gpuGroup)' in eng and '0.35*std::log(cpuGroup)' in eng,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta51 source audit failed: '+', '.join(bad))
