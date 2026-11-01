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

    // Network sockets are owned by main(). Re-initializing libnx sockets here
    // can fail immediately and silently skip the entire startup update check.
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        return false;
    }
'''
if old not in s:
    raise SystemExit('startup socket init block not found')
s = s.replace(old, new, 1)

s = s.replace('            socketExit();\n            return false;', '            return false;')
s = s.replace('                socketExit();\n                return false;', '                return false;')
s = s.replace('            socketExit();\n            return true;', '            return true;')
s = s.replace('                    socketExit();\n                    drawInstalled(latest);', '                    drawInstalled(latest);')
s = s.replace('                    socketExit();\n                    return false;', '                    return false;')
s = s.replace('                    socketExit();\n                    return true;', '                    return true;')
s = s.replace('    socketExit();\n    return true;', '    return true;')

s = s.replace('HOC Undervolting Wizard - Update', 'HOC Overclocking Wizard - Update')
s = s.replace('HOC Undervolting Wizard\\x1b[0m', 'HOC Overclocking Wizard\\x1b[0m')
s = s.replace('launch HOC Undervolting Wizard again.', 'launch HOC Overclocking Wizard again.')

p.write_text(s)

mf = Path('Makefile')
m = mf.read_text()
if 'APP_VERSION := 0.1.0-beta.2' not in m:
    raise SystemExit('beta2 version not found in Makefile')
mf.write_text(m.replace('APP_VERSION := 0.1.0-beta.2', 'APP_VERSION := 0.1.0-beta.3', 1))

Path('RELEASE_NOTES_v0.1.0-beta.3.md').write_text('''# HOC Overclocking Wizard v0.1.0-beta.3\n\n- Fixed startup update checking being skipped because the socket service was initialized twice.\n- The updater now uses the network service already owned by the main application and no longer shuts it down itself.\n- Corrected remaining updater labels from HOC Undervolting Wizard to HOC Overclocking Wizard.\n- Includes all beta2 changes: 100% battery requirement, Expected Max OC on hardware detection, and context-aware Active Values.\n''')
