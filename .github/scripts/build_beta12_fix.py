from pathlib import Path

p = Path('source/main_oc.cpp')
s = p.read_text()

bad1 = '''        case Stage::RamHpTest:if(g.ramHpMode){occonfig::setHpMode(false,e);g.ramHpMode=0;requestReboot(Stage::RamStSet);return;}break;\n'''
bad2 = '''        case Stage::RamStTest:if(g.ramTimingMode){const auto*pr=profile();if(pr){std::uint32_t t[8];for(int i=0;i<8;++i)t[i]=pr->common.t[i];occonfig::setRamTimings(t,e);}g.ramTimingMode=0;requestReboot(Stage::RamSoc);return;}break;\n'''

if bad1 not in s or bad2 not in s:
    raise SystemExit('Expected misplaced beta12 recovery cases were not found')

s = s.replace(bad1, '', 1).replace(bad2, '', 1)
p.write_text(s)
print('Removed misplaced HP/ST recovery cases; tuning flow unchanged.')
