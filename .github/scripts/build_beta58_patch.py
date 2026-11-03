from pathlib import Path


def must_replace_once(s, old, new, name):
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"beta58 expected exactly one {name}, found {count}")
    return s.replace(old, new, 1)

# Version only. No tuning logic changes.
p = Path('Makefile')
s = p.read_text()
s = must_replace_once(s, 'APP_VERSION := 0.1.0-beta.57', 'APP_VERSION := 0.1.0-beta.58', 'version marker')
p.write_text(s)

# VDD2 task wording only: make it clear that A continues into applying/rebooting.
p = Path('source/main_oc.cpp')
m = p.read_text()
m = must_replace_once(m, '"Apply VDD2 ', '"Continue to apply VDD2 ', 'VDD2 task wording')
p.write_text(m)

# Audit: wording changed, behavior preserved.
main = Path('source/main_oc.cpp').read_text()
stress = Path('source/stress_tests.cpp').read_text()
checks = {
    'beta58 version': '0.1.0-beta.58' in Path('Makefile').read_text(),
    'new VDD2 task wording': '"Continue to apply VDD2 ' in main,
    'old VDD2 task wording gone': '"Apply VDD2 ' not in main,
    'VDD2 optimization retained': 'VDD2' in main,
    'RAM fail cleanup retained': 'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for name, ok in checks.items():
    print(('PASS ' if ok else 'FAIL ') + name)
bad = [name for name, ok in checks.items() if not ok]
if bad:
    raise SystemExit('Beta58 source audit failed: ' + ', '.join(bad))
