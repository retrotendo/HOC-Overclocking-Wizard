from pathlib import Path

p = Path('source/updater.cpp')
s = p.read_text()

old = '''bool startupCheckAndPrompt(PadState& pad, int argc, char** argv) {
    drawChecking();

    const Result socketRc = socketInitializeDefault();
    if (R_FAILED(socketRc)) return false;

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        socketExit();
        return false;
    }
'''
new = '''bool startupCheckAndPrompt(PadState& pad, int argc, char** argv) {
    drawChecking();

    // main() owns the libnx socket service. Re-initializing it here can fail
    // immediately and skip the whole startup update flow before the UI is seen.
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        return false;
    }
'''
if old not in s:
    raise SystemExit('startup updater init block not found')
s = s.replace(old, new, 1)

# startupCheckAndPrompt must not shut down the socket service owned by main().
s = s.replace('            socketExit();\n', '')
s = s.replace('                socketExit();\n', '')
s = s.replace('                    socketExit();\n', '')
s = s.replace('    socketExit();\n', '')

s = s.replace('HOC Undervolting Wizard', 'HOC Overclocking Wizard')
p.write_text(s)

mf = Path('Makefile')
m = mf.read_text()
if 'APP_VERSION := 0.1.0-beta.2' not in m:
    raise SystemExit('beta2 version not found')
mf.write_text(m.replace('APP_VERSION := 0.1.0-beta.2', 'APP_VERSION := 0.1.0-beta.3', 1))

Path('RELEASE_NOTES_v0.1.0-beta.3.md').write_text('''# HOC Overclocking Wizard v0.1.0-beta.3\n\n- Fixed the startup update check being skipped because the libnx socket service was initialized twice.\n- The updater now uses the network service owned by the main application and no longer shuts it down itself.\n- Corrected remaining updater labels from HOC Undervolting Wizard to HOC Overclocking Wizard.\n- Includes all beta2 changes: 100% battery requirement, Expected Max OC on Hardware Detection, and context-aware Active Values.\n''')
