from pathlib import Path
import re


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta25 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile')
s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.24','APP_VERSION := 0.1.0-beta.25','version')
p.write_text(s)

p=Path('source/main_oc.cpp')
s=p.read_text()

# Hardware Detection only: YOUR TASK is just Continue once hardware is detected.
start=s.find('case Stage::Hardware:{')
end=s.find('case Stage::BenchmarkPrep:', start)
if start < 0 or end < 0:
    raise SystemExit('beta25 Hardware stage block missing')
hw=s[start:end]
hw=must_replace(hw,
    'v.instructionTitle=detected?"Hardware detected":"Detect this console";',
    'v.instructionTitle=detected?"Continue":"Detect this console";',
    'hardware task title')
hw=must_replace(hw,
    'v.instructionLine1=detected?"Review the detected RAM before tuning begins.":"The Wizard will identify the installed RAM and select its HOC table.";',
    'v.instructionLine1=detected?"":"The Wizard will identify the installed RAM and select its HOC table.";',
    'hardware task subtitle')
hw=must_replace(hw,
    'v.instructionLine2=detected?"A  Continue":"A  Detect hardware";',
    'v.instructionLine2=detected?"":"A  Detect hardware";',
    'hardware task duplicate action')

# Hardware Detection ACTUAL ACTIVE VALUES: show SoC VMAX config, not a current SoC table point.
old_soc = '''                    int activeRam=int(std::lround(g_active.realHz[2]/1e6));if(activeRam<1866)activeRam=1866;\n                    int socCfg=0;std::string se;const int socFreq=nearestSocFreq(activeRam);\n                    setValue(1,"SoC",occonfig::getSocPoint(socFreq,socCfg,se)?fmtSocConfigMv(socCfg):"unavailable");'''
new_soc = '''                    setValue(1,"SoC Max Voltage",std::to_string(rc.socVmaxMv)+" mV");'''
hw=must_replace(hw,old_soc,new_soc,'hardware SoC VMAX active value')

s=s[:start]+hw+s[end:]
p.write_text(s)

# Audit only the requested UI changes; tuning logic must stay untouched.
main=p.read_text()
start=main.find('case Stage::Hardware:{')
end=main.find('case Stage::BenchmarkPrep:',start)
hw=main[start:end]
checks={
    'beta25 version':'0.1.0-beta.25' in Path('Makefile').read_text(),
    'hardware task Continue only':'v.instructionTitle=detected?"Continue"' in hw,
    'hardware detected subtitle empty':'v.instructionLine1=detected?""' in hw,
    'hardware duplicate action removed':'v.instructionLine2=detected?""' in hw,
    'hardware SoC VMAX label':'setValue(1,"SoC Max Voltage"' in hw,
    'hardware SoC VMAX config value':'std::to_string(rc.socVmaxMv)+" mV"' in hw,
    'old hardware SoC point removed':'setValue(1,"SoC",' not in hw,
    'beta24 benchmark flow retained':'Stage::RamBenchmark' in main and 'Final RAM Benchmark Sweep' in main,
    'beta22 force shortcuts retained':'HidNpadButton_Plus' in Path('source/stress_tests.cpp').read_text() and 'HidNpadButton_Minus' in Path('source/stress_tests.cpp').read_text(),
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
bad=[name for name,ok in checks.items() if not ok]
if bad: raise SystemExit('Beta25 source audit failed: '+', '.join(bad))
