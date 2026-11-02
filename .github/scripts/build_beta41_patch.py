from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta41 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.40','APP_VERSION := 0.1.0-beta.41','version')
p.write_text(s)

# RAM sweep resume modal: exactly two decisions for an active interrupted
# candidate. A = YES/fail, X = NO/retry. No Exit action on this prompt.
p=Path('source/main_oc.cpp'); m=p.read_text()
old_active='''            m.primaryAction="A  YES - mark "+std::to_string(candidate)+" MHz failed";\n            m.secondaryAction="X  NO - retry "+std::to_string(candidate)+" MHz     B  Exit";'''
new_active='''            m.primaryAction="YES - mark "+std::to_string(candidate)+" MHz failed";\n            m.tertiaryAction="NO - retry "+std::to_string(candidate)+" MHz";\n            m.secondaryAction.clear();'''
m=must_replace(m,old_active,new_active,'active RAM resume actions')

# Between-candidate resume is informational: just continue. Remove Exit here too.
old_safe='''            m.primaryAction="A  Continue with "+std::to_string(candidate)+" MHz";\n            m.secondaryAction="B  Exit";'''
new_safe='''            m.primaryAction="Continue with "+std::to_string(candidate)+" MHz";\n            m.tertiaryAction.clear();\n            m.secondaryAction.clear();'''
m=must_replace(m,old_safe,new_safe,'safe handoff resume action')

# The dedicated RAM sweep resume dialog no longer has a B/Exit path.
old_b='''            if(k&HidNpadButton_B){saveState();break;}\n            continue;\n        }'''
new_b='''            continue;\n        }'''
# Restrict replacement to the explicit resume handler region so generic B/Exit remains elsewhere.
rs=m.find('if(g_ramSweepResumeModal){', m.find('while(appletMainLoop())'))
re=m.find('if(g_recoveryModal)', rs)
if rs<0 or re<0:
    raise SystemExit('beta41 marker missing: RAM resume input region')
region=m[rs:re]
region=must_replace(region,old_b,new_b,'RAM resume B exit removal')
m=m[:rs]+region+m[re:]
p.write_text(m)

# Modal renderer: when A + X are present and B is absent, render two wide
# buttons instead of reserving a three-column layout with an empty B slot.
p=Path('source/gui_console.cpp'); g=p.read_text()
old_renderer='''        if (!m.tertiaryAction.empty()) {\n            // Decision modal: one clear Yes / No / Exit row.\n            drawActionButton(x + 38,  by, 296, 48, "A : " + m.primaryAction);\n            drawActionButton(x + 347, by, 296, 48, "X : " + m.tertiaryAction);\n            if (!m.secondaryAction.empty())\n                drawActionButton(x + 656, by, 296, 48, "B : " + m.secondaryAction);\n        } else if (!m.secondaryAction.empty()) {'''
new_renderer='''        if (!m.tertiaryAction.empty()) {\n            if (m.secondaryAction.empty()) {\n                // Two-choice decision modal: A / X only.\n                drawActionButton(x + 38,  by, 445, 48, "A : " + m.primaryAction);\n                drawActionButton(x + 507, by, 445, 48, "X : " + m.tertiaryAction);\n            } else {\n                // Three-choice decision modal: A / X / B.\n                drawActionButton(x + 38,  by, 296, 48, "A : " + m.primaryAction);\n                drawActionButton(x + 347, by, 296, 48, "X : " + m.tertiaryAction);\n                drawActionButton(x + 656, by, 296, 48, "B : " + m.secondaryAction);\n            }\n        } else if (!m.secondaryAction.empty()) {'''
g=must_replace(g,old_renderer,new_renderer,'two-choice modal renderer')
p.write_text(g)

# Audit
main=Path('source/main_oc.cpp').read_text(); gui=Path('source/gui_console.cpp').read_text(); stress=Path('source/stress_tests.cpp').read_text(); eng=Path('source/oc_engine.cpp').read_text()
rs=main.find('if(g_ramSweepResumeModal){', main.find('while(appletMainLoop())'))
re=main.find('if(g_recoveryModal)', rs)
resume_input=main[rs:re] if rs>=0 and re>=0 else ''
checks={
    'beta41 version':'0.1.0-beta.41' in Path('Makefile').read_text(),
    'active yes action':'m.primaryAction="YES - mark "+std::to_string(candidate)+" MHz failed"' in main,
    'active no action':'m.tertiaryAction="NO - retry "+std::to_string(candidate)+" MHz"' in main,
    'active no B action':'m.secondaryAction.clear();' in main[main.find('if(g.ramSweepCandidateInProgress)'):main.find('m.tone=gui::ModalTone::Amber',main.find('if(g.ramSweepCandidateInProgress)'))],
    'resume B exit removed':'HidNpadButton_B' not in resume_input,
    'A fail behavior retained':'recoverInterruptedRamSweep();' in resume_input,
    'X retry behavior retained':'HidNpadButton_X' in resume_input and 'runRamSweepAutomatic();' in resume_input,
    'two wide A X buttons':'Two-choice decision modal: A / X only.' in gui and '445, 48, "X : " + m.tertiaryAction' in gui,
    'three choice support retained':'Three-choice decision modal: A / X / B.' in gui,
    'beta40 dual recommendations retained':'ramEfficiencyRecommendedMHz' in main and 'EFFICIENCY' in main and 'PERFORMANCE' in main,
    'beta39 performance model retained':'costPer100=dV/dMHz*100.0' in main and 'valuePerMv=dV>1e-9?dPerf/dV' in main,
    'beta37 transition retained':'Next RAM candidate: ' in main and 'Temporary RAM override is OFF.' in main,
    'beta38 confirm recovery retained':'MHz confirmation did not finish' in main,
    'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
    'beta32 index retained':'recalculateRamPerformanceIndex(ramPoints)' in main and '0.35*std::log(gpuGroup)' in eng,
    'RAM fail cleanup retained':'RAM safety: remove CPU/GPU/RAM temporary overrides immediately' in stress,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta41 source audit failed: '+', '.join(bad))
