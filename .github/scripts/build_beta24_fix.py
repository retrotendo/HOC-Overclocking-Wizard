from pathlib import Path

p=Path('source/main_oc.cpp')
s=p.read_text()
marker='void render(){'
if marker not in s:
    raise SystemExit('beta24-fix render marker missing')
protos='''int socTableForRamMHz(int ramMHz);\nint nextRamBenchmarkPoint(int from);\n\n'''
if 'int nextRamBenchmarkPoint(int from);' not in s:
    s=s.replace(marker,protos+marker,1)
p.write_text(s)

main=p.read_text()
render_pos=main.find('void render(){')
checks={
    'SoC helper declared before render':0 <= main.find('int socTableForRamMHz(int ramMHz);') < render_pos,
    'benchmark helper declared before render':0 <= main.find('int nextRamBenchmarkPoint(int from);') < render_pos,
    'helper implementations retained':main.count('int socTableForRamMHz(int ramMHz)')>=2 and main.count('int nextRamBenchmarkPoint(int from)')>=2,
}
for name,ok in checks.items():print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad:raise SystemExit('Beta24 compile fix audit failed: '+', '.join(bad))
