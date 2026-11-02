from pathlib import Path

p=Path('source/main_oc.cpp')
s=p.read_text()
marker='void render(){'
if marker not in s:
    marker='void render() {'
if marker not in s:
    raise SystemExit('beta27-fix render marker missing')
pre=s[:s.find(marker)]
if 'void recoverInterruptedRamConfirmation();' not in pre:
    s=s.replace(marker,'void recoverInterruptedRamConfirmation();\n\n'+marker,1)
p.write_text(s)

s=p.read_text()
if s.find('void recoverInterruptedRamConfirmation();')<0 or s.find('void recoverInterruptedRamConfirmation();')>s.find(marker):
    raise SystemExit('beta27-fix forward declaration not before render')
print('PASS beta27 confirmation recovery declared before render')
