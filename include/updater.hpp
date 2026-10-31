#pragma once

#include <switch.h>

namespace updater {

// Performs the startup update check in Full Application Mode.
// Returns true when the app should exit (normally after a successful update).
bool startupCheckAndPrompt(PadState& pad, int argc, char** argv);

} // namespace updater
