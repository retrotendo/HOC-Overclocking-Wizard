from pathlib import Path

p=Path('source/attention_sound.cpp')
s=p.read_text()
s=s.replace('#include <cstdlib>\n','#include <cstdlib>\n#include <malloc.h>\n',1)
old='''    void* raw = nullptr;\n    if (posix_memalign(&raw, 0x1000, allocBytes) != 0 || !raw) {\n        audoutExit();\n        return false;\n    }'''
new='''    void* raw = memalign(0x1000, allocBytes);\n    if (!raw) {\n        audoutExit();\n        return false;\n    }'''
if old not in s:
    raise SystemExit('beta20 fix marker missing')
s=s.replace(old,new,1)
p.write_text(s)

s=p.read_text()
assert 'memalign(0x1000, allocBytes)' in s
assert 'posix_memalign' not in s
print('PASS beta20 libnx-compatible aligned audio allocation')
