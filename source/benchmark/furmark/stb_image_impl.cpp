// Benchmark Toolbox uses stb_image through Borealis, which normally provides
// the single STB_IMAGE_IMPLEMENTATION translation unit. The OC Wizard embeds
// the Furmark benchmark without Borealis, so provide that implementation here.
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
