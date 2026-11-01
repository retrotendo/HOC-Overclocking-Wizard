from pathlib import Path

# Make the YOUR TASK card instruction-only. Actions stay on the left.
p=Path('source/gui_console.cpp')
s=p.read_text()
old='''    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));

    roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));
    drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));'''
new='''    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));'''
if old not in s:
    raise SystemExit('beta21 task-card marker missing')
s=s.replace(old,new,1)
p.write_text(s)

# Remove remaining developer-oriented wording that beta17/beta18 may have introduced.
p=Path('source/main_oc.cpp')
m=p.read_text()
for old,new in {
    'DVB is optimized before HP and timings so timing changes cannot hide its real requirement.':'',
    'Common timings first; HP and ST are validated after max clock discovery.':'Set the RAM baseline before starting the clock search.',
    'ST is attempted only after clock capability and HP are known.':'Apply Super Tight timings and validate them.',
    'The split is selected only after Low and High curves are known.':'Apply the selected TBreak and reboot.',
    'This is tuned after TBreak so the lower High anchor is known.':'Apply the next High VMIN candidate.',
}.items():
    m=m.replace(old,new)
p.write_text(m)

# Audit
s=Path('source/gui_console.cpp').read_text();m=Path('source/main_oc.cpp').read_text()
checks={
 'no task button':'roundedRect(x + 22, y + 126' not in s and 'g_view.instructionLine2, 25' not in s,
 'DVB developer text removed':'DVB is optimized before HP and timings' not in m,
 'DVB user task kept':'Continue to apply DVB Shift ' in m,
 'DVB candidate label kept':'Next DVB candidate to test:' in m,
}
for n,o in checks.items(): print(('PASS ' if o else 'FAIL ')+n)
bad=[n for n,o in checks.items() if not o]
if bad: raise SystemExit('Beta21 fix audit failed: '+', '.join(bad))
