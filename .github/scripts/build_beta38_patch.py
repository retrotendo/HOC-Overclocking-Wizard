from pathlib import Path


def must_replace(s, old, new, name, count=1):
    if old not in s:
        raise SystemExit(f"beta38 marker missing: {name}")
    return s.replace(old, new, count)

# Version
p=Path('Makefile'); s=p.read_text()
s=must_replace(s,'APP_VERSION := 0.1.0-beta.37','APP_VERSION := 0.1.0-beta.38','version')
p.write_text(s)

# Recovery modal UI only. Keep all recovery behavior unchanged.
p=Path('source/main_oc.cpp'); m=p.read_text()
old='''    if(g_recoveryModal){gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED TEST";m.title="Previous candidate did not finish";m.body={"A crash, freeze or reboot occurred while a candidate was being tested.","The Wizard will restore the last known good value before continuing."};m.primaryAction="A  Recover last good value";m.secondaryAction="B  Exit";m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;}'''
new='''    if(g_recoveryModal){
        gui::ModalView m;m.version=HOC_WIZARD_VERSION;m.eyebrow="INTERRUPTED TEST";
        if(g.stage==Stage::RamConfirm && g.ramConfirmInProgress && g.ramConfirmMHz>0){
            m.title="RAM "+std::to_string(g.ramConfirmMHz)+" MHz confirmation did not finish";
            m.body={"A crash, freeze or reboot occurred during the 1-hour RAM confirmation.",
                    "The Wizard will restore the last known good value before continuing."};
        }else{
            m.title="Previous candidate did not finish";
            m.body={"A crash, freeze or reboot occurred while a candidate was being tested.",
                    "The Wizard will restore the last known good value before continuing."};
        }
        // The modal renderer already supplies the controller button icons.
        // Do not duplicate A/B inside the action labels.
        m.primaryAction="Recover last good value";
        m.secondaryAction="Exit";
        m.tone=gui::ModalTone::Amber;gui::presentModal(m);return;
    }'''
m=must_replace(m,old,new,'generic recovery modal')
p.write_text(m)

# Audit
main=Path('source/main_oc.cpp').read_text()
checks={
    'beta38 version':'0.1.0-beta.38' in Path('Makefile').read_text(),
    'confirm frequency in recovery':'RAM "+std::to_string(g.ramConfirmMHz)+" MHz confirmation did not finish' in main,
    'confirm uses active MHz':'g.stage==Stage::RamConfirm && g.ramConfirmInProgress && g.ramConfirmMHz>0' in main,
    'no duplicate A action':'m.primaryAction="Recover last good value"' in main,
    'no duplicate B action':'m.secondaryAction="Exit"' in main,
    'generic recovery retained':'m.title="Previous candidate did not finish"' in main,
    'recovery behavior retained':'recoverInterrupted();' in main,
    'one hour confirmation retained':'runStress(stress::Kind::Ram,3600' in main,
    'beta37 transition retained':'Next RAM candidate: ' in main and 'Temporary RAM override is OFF.' in main,
    'beta37 pass semantics retained':'commitRamSweepPass(freq,socConfigMv,rc)' in main,
    'beta32 index retained':'recalculateRamPerformanceIndex(ramPoints)' in main,
    'DVB8 retained':'DVB8 / 66MHz Step Mode' in main,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta38 source audit failed: '+', '.join(bad))
