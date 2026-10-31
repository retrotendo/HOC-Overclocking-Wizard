#include "gui_console.hpp"

#include <switch.h>
#include <ft2build.h>
#include FT_FREETYPE_H

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace gui {
namespace {

constexpr int W = 1280;
constexpr int H = 720;

constexpr u32 C_BG        = RGBA8_MAXALPHA(8, 12, 18);
constexpr u32 C_PANEL     = RGBA8_MAXALPHA(16, 23, 34);
constexpr u32 C_PANEL_2   = RGBA8_MAXALPHA(20, 29, 42);
constexpr u32 C_BORDER    = RGBA8_MAXALPHA(43, 56, 72);
constexpr u32 C_TEXT      = RGBA8_MAXALPHA(240, 246, 252);
constexpr u32 C_MUTED     = RGBA8_MAXALPHA(137, 151, 169);
constexpr u32 C_CYAN      = RGBA8_MAXALPHA(35, 211, 238);
constexpr u32 C_CYAN_DIM  = RGBA8_MAXALPHA(15, 105, 125);
constexpr u32 C_GREEN     = RGBA8_MAXALPHA(52, 211, 153);
constexpr u32 C_BLUE      = RGBA8_MAXALPHA(59, 130, 246);
constexpr u32 C_RED       = RGBA8_MAXALPHA(239, 68, 68);
constexpr u32 C_AMBER     = RGBA8_MAXALPHA(245, 158, 11);
constexpr u32 C_DARK      = RGBA8_MAXALPHA(31, 41, 55);

Framebuffer g_fb{};
bool g_initialized = false;
bool g_plInitialized = false;
FT_Library g_ft = nullptr;
FT_Face g_face = nullptr;
u32* g_pixels = nullptr;
u32 g_stride = 0;
View g_view{};

struct Line {
    int row = 0;
    std::string text;
};
std::vector<Line> g_lines;

int red(u32 c)   { return int(c & 0xff); }
int green(u32 c) { return int((c >> 8) & 0xff); }
int blue(u32 c)  { return int((c >> 16) & 0xff); }

u32 mix(u32 a, u32 b, int pctB) {
    pctB = std::max(0, std::min(100, pctB));
    const int pctA = 100 - pctB;
    return RGBA8_MAXALPHA(
        (red(a) * pctA + red(b) * pctB) / 100,
        (green(a) * pctA + green(b) * pctB) / 100,
        (blue(a) * pctA + blue(b) * pctB) / 100);
}

void pixel(int x, int y, u32 color) {
    if (!g_pixels || x < 0 || y < 0 || x >= W || y >= H) return;
    g_pixels[y * g_stride + x] = color;
}

void blendPixel(int x, int y, u32 color, int alpha) {
    if (!g_pixels || x < 0 || y < 0 || x >= W || y >= H || alpha <= 0) return;
    if (alpha >= 255) { pixel(x, y, color); return; }
    const u32 dst = g_pixels[y * g_stride + x];
    const int inv = 255 - alpha;
    g_pixels[y * g_stride + x] = RGBA8_MAXALPHA(
        (red(color) * alpha + red(dst) * inv) / 255,
        (green(color) * alpha + green(dst) * inv) / 255,
        (blue(color) * alpha + blue(dst) * inv) / 255);
}

void fillRect(int x, int y, int w, int h, u32 color) {
    if (!g_pixels || w <= 0 || h <= 0) return;
    const int x0 = std::max(0, x), y0 = std::max(0, y);
    const int x1 = std::min(W, x + w), y1 = std::min(H, y + h);
    for (int yy = y0; yy < y1; ++yy) {
        u32* row = g_pixels + yy * g_stride + x0;
        std::fill(row, row + (x1 - x0), color);
    }
}

void fillCircle(int cx, int cy, int r, u32 color) {
    for (int y = -r; y <= r; ++y) {
        const int xx = int(std::sqrt(double(std::max(0, r * r - y * y))));
        fillRect(cx - xx, cy + y, xx * 2 + 1, 1, color);
    }
}

void roundedRect(int x, int y, int w, int h, int r, u32 color) {
    r = std::max(0, std::min(r, std::min(w, h) / 2));
    fillRect(x + r, y, w - 2 * r, h, color);
    fillRect(x, y + r, r, h - 2 * r, color);
    fillRect(x + w - r, y + r, r, h - 2 * r, color);
    for (int yy = 0; yy < r; ++yy) {
        const int dy = r - 1 - yy;
        const int dx = int(std::sqrt(double(std::max(0, r * r - dy * dy))));
        fillRect(x + r - dx, y + yy, w - 2 * r + 2 * dx, 1, color);
        fillRect(x + r - dx, y + h - 1 - yy, w - 2 * r + 2 * dx, 1, color);
    }
}

void roundedBorder(int x, int y, int w, int h, int r, u32 border, u32 fill, int thickness = 1) {
    roundedRect(x, y, w, h, r, border);
    roundedRect(x + thickness, y + thickness, w - 2 * thickness, h - 2 * thickness,
                std::max(0, r - thickness), fill);
}

std::string stripAnsi(const char* in) {
    std::string out;
    if (!in) return out;
    const unsigned char* s = reinterpret_cast<const unsigned char*>(in);
    for (size_t i = 0; s[i]; ) {
        if (s[i] == 0x1b && s[i + 1] == '[') {
            i += 2;
            while (s[i] && !std::isalpha(s[i])) ++i;
            if (s[i]) ++i;
            continue;
        }
        out.push_back(char(s[i++]));
    }
    return out;
}

bool startsWith(const std::string& s, const char* p) {
    return s.rfind(p, 0) == 0;
}

std::string trim(std::string s) {
    const auto notSpace = [](unsigned char c) { return !std::isspace(c); };
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), notSpace));
    s.erase(std::find_if(s.rbegin(), s.rend(), notSpace).base(), s.end());
    return s;
}

bool isSeparator(const std::string& s) {
    if (s.size() < 8) return false;
    return std::all_of(s.begin(), s.end(), [](char c) { return c == '-' || c == '=' || c == ' '; });
}

bool isAction(const std::string& s) {
    return startsWith(s, "A :") || startsWith(s, "Y :") || startsWith(s, "+ :") ||
           startsWith(s, "X :") || startsWith(s, "B :") || startsWith(s, "- :");
}

void setFontSize(int px) {
    if (g_face) FT_Set_Pixel_Sizes(g_face, 0, std::max(8, px));
}

int textWidth(const std::string& text, int size) {
    if (!g_face) return int(text.size()) * size / 2;
    setFontSize(size);
    int w = 0;
    for (size_t i = 0; i < text.size();) {
        uint32_t cp = 0;
        const ssize_t n = decode_utf8(&cp, reinterpret_cast<const uint8_t*>(text.c_str() + i));
        if (n <= 0) break;
        i += size_t(n);
        const FT_UInt idx = FT_Get_Char_Index(g_face, cp);
        if (!FT_Load_Glyph(g_face, idx, FT_LOAD_DEFAULT)) w += int(g_face->glyph->advance.x >> 6);
    }
    return w;
}

std::string fitText(std::string text, int size, int maxWidth) {
    if (textWidth(text, size) <= maxWidth) return text;
    const std::string dots = "...";
    while (!text.empty() && textWidth(text + dots, size) > maxWidth) text.pop_back();
    return text + dots;
}

void drawText(int x, int y, int size, u32 color, const std::string& text) {
    if (!g_face || !g_pixels) return;
    setFontSize(size);
    int penX = x;
    const int baseline = y + size;
    for (size_t i = 0; i < text.size();) {
        uint32_t cp = 0;
        const ssize_t n = decode_utf8(&cp, reinterpret_cast<const uint8_t*>(text.c_str() + i));
        if (n <= 0) break;
        i += size_t(n);
        const FT_UInt idx = FT_Get_Char_Index(g_face, cp);
        if (FT_Load_Glyph(g_face, idx, FT_LOAD_DEFAULT)) continue;
        if (FT_Render_Glyph(g_face->glyph, FT_RENDER_MODE_NORMAL)) continue;
        const FT_GlyphSlot slot = g_face->glyph;
        const FT_Bitmap& bm = slot->bitmap;
        const int gx = penX + slot->bitmap_left;
        const int gy = baseline - slot->bitmap_top;
        if (bm.pixel_mode == FT_PIXEL_MODE_GRAY) {
            for (unsigned yy = 0; yy < bm.rows; ++yy) {
                const unsigned char* src = bm.buffer + yy * bm.pitch;
                for (unsigned xx = 0; xx < bm.width; ++xx)
                    blendPixel(gx + int(xx), gy + int(yy), color, src[xx]);
            }
        }
        penX += int(slot->advance.x >> 6);
    }
}

void drawTextRight(int right, int y, int size, u32 color, const std::string& text) {
    drawText(right - textWidth(text, size), y, size, color, text);
}

void drawLabel(int x, int y, const std::string& text) {
    drawText(x, y, 15, C_CYAN, text);
}

void drawCard(int x, int y, int w, int h, bool accent = false) {
    const u32 border = accent ? mix(C_CYAN_DIM, C_CYAN, 35) : C_BORDER;
    roundedBorder(x, y, w, h, 18, border, C_PANEL, 1);
}

u32 actionColor(const std::string& text) {
    if (startsWith(text, "A :")) return C_GREEN;
    if (startsWith(text, "Y :")) return C_BLUE;
    if (startsWith(text, "+ :")) return C_CYAN;
    if (startsWith(text, "X :")) {
        if (text.find("FAIL") != std::string::npos || text.find("unstable") != std::string::npos ||
            text.find("crash") != std::string::npos || text.find("safer") != std::string::npos)
            return C_RED;
        return C_BLUE;
    }
    return C_MUTED;
}

void drawActionButton(int x, int y, int w, int h, const std::string& text) {
    if (text.size() < 3) return;
    const u32 accent = actionColor(text);
    const bool reset = startsWith(text, "- :");
    const u32 bg = reset ? C_DARK : mix(C_PANEL_2, accent, 12);
    const u32 border = reset ? C_BORDER : mix(C_BORDER, accent, 48);
    roundedBorder(x, y, w, h, 11, border, bg, 1);

    std::string key = trim(text.substr(0, text.find(':')));
    std::string label = trim(text.substr(text.find(':') + 1));
    roundedRect(x + 10, y + 7, 34, h - 14, 9, accent);
    const int kw = textWidth(key, 17);
    drawText(x + 27 - kw / 2, y + 8, 17, C_BG, key);
    drawText(x + 56, y + 8, 18, C_TEXT, fitText(label, 18, w - 70));
}

void drawHeader() {
    drawText(42, 24, 24, C_TEXT, "Horizon");
    drawText(134, 24, 24, C_CYAN, "OC");
    drawText(177, 24, 24, C_MUTED, "/");
    drawText(198, 24, 24, C_TEXT, "Undervolting Wizard");

    roundedRect(1085, 20, 150, 34, 17, C_PANEL_2);
    drawTextRight(1218, 26, 15, C_MUTED, "v" + g_view.version);

    fillRect(40, 70, 1200, 1, C_BORDER);
}

void drawProgress() {
    static const char* labels[7] = {"Baseline", "Low UV", "Low VMIN", "VDDQ", "VDD2", "High UV", "Finalize"};
    const int x0 = 72, x1 = 1208, y = 106;
    fillRect(x0, y, x1 - x0, 2, C_BORDER);
    for (int i = 0; i < 7; ++i) {
        const int step = i + 1;
        const int x = x0 + (x1 - x0) * i / 6;
        const bool done = step < g_view.activeStep;
        const bool active = step == g_view.activeStep;
        if (i > 0 && step <= g_view.activeStep)
            fillRect(x0 + (x1 - x0) * (i - 1) / 6, y, x - (x0 + (x1 - x0) * (i - 1) / 6), 2, C_CYAN_DIM);
        if (active && g_view.pulse) fillCircle(x, y + 1, 13, mix(C_BG, C_CYAN, 35));
        fillCircle(x, y + 1, active ? 8 : 6, active || done ? C_CYAN : C_BORDER);
        if (done) fillCircle(x, y + 1, 3, C_BG);
        const int tw = textWidth(labels[i], 14);
        drawText(x - tw / 2, 119, 14, active ? C_TEXT : (done ? C_MUTED : mix(C_BG, C_MUTED, 55)), labels[i]);
    }
}

void drawInstructionCard() {
    const int x = 835, y = 158, w = 405, h = 205;
    drawCard(x, y, w, h, true);
    drawLabel(x + 24, y + 20, "YOUR TASK");
    drawText(x + 24, y + 52, 23, C_TEXT,
             fitText(g_view.instructionTitle.empty() ? "Continue Wizard" : g_view.instructionTitle, 23, w - 48));
    drawText(x + 24, y + 91, 16, C_MUTED, fitText(g_view.instructionLine1, 16, w - 48));

    roundedRect(x + 22, y + 126, w - 44, 54, 12, mix(C_PANEL_2, C_CYAN, 11));
    drawText(x + 38, y + 137, 25, C_CYAN, fitText(g_view.instructionLine2, 25, w - 76));
}

void drawPreparationCard() {
    const int x = 715, y = 158, w = 525, h = 522;
    drawCard(x, y, w, h, true);
    drawLabel(x + 24, y + 20, "YOUR TASK");
    drawText(x + 24, y + 48, 25, C_TEXT, "Set the Preparation values");
    drawText(x + 24, y + 80, 14, C_MUTED, "Open Horizon OC / HOC Toolkit and match SET.");

    const int setRight = x + 393;
    const int activeRight = x + w - 24;
    drawTextRight(setRight, y + 107, 13, C_MUTED, "SET");
    drawTextRight(activeRight, y + 107, 13, C_MUTED, "ACTIVE");
    fillRect(x + 24, y + 130, w - 48, 1, C_BORDER);

    int yy = y + 143;
    std::string currentGroup;
    for (const PreparationRow& r : g_view.preparationRows) {
        if (r.group != currentGroup) {
            if (!currentGroup.empty()) {
                fillRect(x + 24, yy + 1, w - 48, 1, C_BORDER);
                yy += 13;
            }
            drawText(x + 24, yy, 14, C_CYAN, r.group);
            yy += 24;
            currentGroup = r.group;
        }

        if (r.mismatch)
            roundedRect(x + 18, yy - 3, w - 36, 26, 8, mix(C_PANEL_2, C_RED, 10));
        drawText(x + 28, yy, 14, C_MUTED, fitText(r.label, 14, 235));
        drawTextRight(setRight, yy, 14, C_TEXT, fitText(r.setValue, 14, 104));
        const u32 activeColor = !g_view.havePreparationActiveValues ? C_MUTED : (r.mismatch ? C_RED : C_TEXT);
        drawTextRight(activeRight, yy, 14, activeColor, fitText(r.activeValue, 14, 105));
        yy += 23;
    }
}

void drawValuesCard() {
    const int x = 835, y = 382, w = 405, h = 298;
    drawCard(x, y, w, h, false);
    drawLabel(x + 24, y + 20, "ACTUAL ACTIVE VALUES");
    if (!g_view.haveActiveValues) {
        roundedRect(x + 22, y + 62, w - 44, 52, 12, mix(C_PANEL_2, C_RED, 11));
        drawText(x + 38, y + 74, 18, C_RED, "Horizon OC values unavailable");
        return;
    }

    int yy = y + 61;
    for (int i = 0; i < 5; ++i, yy += 43) {
        const ValueRow& v = g_view.values[i];
        if (v.mismatch) roundedRect(x + 18, yy - 5, w - 36, 36, 10, mix(C_PANEL_2, C_RED, 11));
        if (i) fillRect(x + 25, yy - 9, w - 50, 1, mix(C_PANEL, C_BORDER, 70));
        drawText(x + 26, yy, 16, C_MUTED, v.label);
        drawTextRight(x + w - 26, yy - 1, 18, v.mismatch ? C_RED : C_TEXT, v.value);
        fillCircle(x + 13, yy + 10, 3, v.mismatch ? C_RED : C_GREEN);
    }
}

int drawWrappedText(int x, int y, int size, u32 color, const std::string& text,
                    int maxWidth, int lineHeight, int maxLines);

void drawMainCard() {
    const int x = 40, y = 158, w = g_view.fullWidthLayout ? 1200 : (g_view.preparationLayout ? 650 : 765), h = 522;
    drawCard(x, y, w, h, false);
    drawLabel(x + 26, y + 20, "GUIDED TUNING");
    drawText(x + 26, y + 49, 29, C_TEXT, fitText(g_view.stageTitle, 29, w - 52));
    fillRect(x + 26, y + 94, w - 52, 1, C_BORDER);

    std::vector<std::string> body;
    std::vector<std::string> actions;
    std::string reset;
    for (const auto& ln : g_lines) {
        std::string s = trim(ln.text);
        if (s.empty() || startsWith(s, "Step :") || isSeparator(s)) continue;
        if (startsWith(s, "- :")) { reset = s; continue; }
        if (isAction(s)) actions.push_back(s);
        else body.push_back(s);
    }

    // Old console pages sometimes split one sentence across several uiPrintf rows.
    // Rejoin only obvious prose fragments, then let the graphical renderer wrap
    // them to the actual card width. This removes unnecessary legacy line breaks
    // without merging headings, values or numbered rows.
    std::vector<std::string> compactBody;
    auto isPlainFragment = [](const std::string& text) {
        if (text.empty() || !std::isalpha(static_cast<unsigned char>(text[0]))) return false;
        if (text.find(':') != std::string::npos || startsWith(text, "http")) return false;
        return true;
    };
    for (const std::string& raw : body) {
        if (!compactBody.empty() && isPlainFragment(compactBody.back()) && isPlainFragment(raw)) {
            const char last = compactBody.back().empty() ? '\0' : compactBody.back().back();
            if (last != '.' && last != '!' && last != '?' && last != ':' && last != ';') {
                compactBody.back() += " " + raw;
                continue;
            }
        }
        compactBody.push_back(raw);
    }
    body.swap(compactBody);

    const bool completeSummary = g_view.fullWidthLayout && g_view.stageTitle == "Complete";
    if (completeSummary) {
        auto drawCentered = [&](int yy, int size, u32 color, const std::string& text) {
            drawText(x + (w - textWidth(text, size)) / 2, yy, size, color, text);
        };

        drawCentered(y + 124, 20, C_GREEN, "UNDERVOLTING COMPLETE");
        drawCentered(y + 164, 16, C_CYAN, "Final values");

        const int tableW = 470;
        const int tableX = x + (w - tableW) / 2;
        int sy = y + 205;
        int rows = 0;
        std::string savedLine;
        for (const std::string& raw : body) {
            if (raw == "UNDERVOLTING COMPLETE" || raw == "Final values:") continue;
            if (startsWith(raw, "Saved to ")) {
                savedLine = raw;
                continue;
            }
            const size_t colon = raw.find(':');
            if (colon == std::string::npos || colon == 0 || colon >= raw.size() - 1) continue;
            const std::string label = trim(raw.substr(0, colon));
            const std::string value = trim(raw.substr(colon + 1));
            if (rows) fillRect(tableX, sy - 8, tableW, 1, mix(C_PANEL, C_BORDER, 65));
            drawText(tableX + 8, sy, 17, C_MUTED, label);
            drawTextRight(tableX + tableW - 8, sy, 18, C_TEXT, value);
            sy += 39;
            ++rows;
        }
        if (!savedLine.empty()) {
            sy += 12;
            drawCentered(sy, 17, C_CYAN, savedLine);
        }
    } else if (g_view.preparationLayout) {
        int by = y + 120;
        if (g_view.stageTitle.find("not ready") != std::string::npos) {
            by = drawWrappedText(x + 28, by, 18, C_TEXT,
                "Some required Preparation values still do not match.", w - 56, 27, 2);
            by += 12;
            drawWrappedText(x + 28, by, 17, C_MUTED,
                "Correct the red ACTIVE values shown on the right, then check again.", w - 56, 25, 3);
        } else {
            by = drawWrappedText(x + 28, by, 18, C_TEXT,
                "Before tuning starts, the Wizard needs a known baseline.", w - 56, 27, 3);
            by += 12;
            drawWrappedText(x + 28, by, 17, C_MUTED,
                "You can set the recommended values manually, use your current settings as the baseline, or let the Wizard apply the recommended values automatically.",
                w - 56, 25, 5);
        }
    } else {
        const int bodyMax = actions.empty() ? 15 : (actions.size() >= 5 ? 8 : 11);
        int by = y + 116;
        int shown = 0;
        for (const std::string& raw : body) {
            if (shown >= bodyMax || by > y + h - 190) break;
            const bool heading = raw == "Objective:" || raw == "Test:" || raw == "Keys:" ||
                                 raw == "Required test clocks:" || raw == "Current Temporary Overrides:" ||
                                 raw == "Final values:" || raw == "Temporary Overrides:";
            if (heading) {
                drawText(x + 28, by, 15, C_CYAN, raw);
                by += 26;
                ++shown;
                continue;
            }

            const bool numberedRow = raw.size() >= 3 && std::isdigit(static_cast<unsigned char>(raw[0])) &&
                                     raw[1] == '.' && raw[2] == ' ';
            if (numberedRow) {
                drawText(x + 28, by, 15, C_TEXT, fitText(raw, 15, w - 56));
                by += 22;
                ++shown;
                continue;
            }

            const size_t colon = raw.find(':');
            const bool valueRow = colon != std::string::npos && colon > 0 && colon < raw.size() - 1 &&
                                  raw.find("http") != 0;
            if (valueRow) {
                const std::string label = trim(raw.substr(0, colon));
                const std::string value = trim(raw.substr(colon + 1));
                if (shown) fillRect(x + 28, by - 7, w - 56, 1, mix(C_PANEL, C_BORDER, 65));
                drawText(x + 28, by, 16, C_MUTED, fitText(label, 16, (w - 70) / 2));
                drawTextRight(x + w - 28, by, 17, C_TEXT, fitText(value, 17, (w - 70) / 2));
                by += 31;
            } else {
                by = drawWrappedText(x + 28, by, 17, C_TEXT, raw, w - 56, 25, 3);
                by += 5;
            }
            ++shown;
        }
        if (shown < int(body.size()) && by < y + h - 175)
            drawText(x + 28, by, 15, C_MUTED, "More details continue in this step...");
    }

    if (!actions.empty()) {
        const int gap = 8;
        const int ah = actions.size() >= 5 ? 35 : 39;
        const int total = int(actions.size()) * ah + (int(actions.size()) - 1) * gap;
        int ay = y + h - 24 - total - (reset.empty() ? 0 : 28);
        ay = std::max(ay, y + (g_view.preparationLayout ? 255 : 260));
        for (const auto& a : actions) {
            drawActionButton(x + 26, ay, w - 52, ah, a);
            ay += ah + gap;
        }
    }
    if (!reset.empty()) drawText(x + 28, y + h - 24, 14, C_MUTED, reset);
}

void beginFrame() {
    if (!g_initialized) return;
    u32 strideBytes = 0;
    g_pixels = static_cast<u32*>(framebufferBegin(&g_fb, &strideBytes));
    g_stride = strideBytes / sizeof(u32);
    fillRect(0, 0, W, H, C_BG);
}

void endFrame() {
    if (!g_initialized || !g_pixels) return;
    framebufferEnd(&g_fb);
    g_pixels = nullptr;
}

u32 modalToneColor(ModalTone tone) {
    switch (tone) {
        case ModalTone::Green: return C_GREEN;
        case ModalTone::Amber: return C_AMBER;
        case ModalTone::Red: return C_RED;
        case ModalTone::Cyan:
        default: return C_CYAN;
    }
}

int drawWrappedText(int x, int y, int size, u32 color, const std::string& text,
                    int maxWidth, int lineHeight, int maxLines = 4) {
    if (text.empty()) return y;
    std::string line;
    std::string word;
    int lines = 0;
    auto flushWord = [&]() {
        if (word.empty()) return;
        const std::string candidate = line.empty() ? word : line + " " + word;
        if (!line.empty() && textWidth(candidate, size) > maxWidth) {
            drawText(x, y, size, color, line);
            y += lineHeight;
            ++lines;
            line = word;
        } else {
            line = candidate;
        }
        word.clear();
    };
    for (size_t i = 0; i <= text.size(); ++i) {
        const char c = i < text.size() ? text[i] : ' ';
        if (c == ' ' || c == '\n' || i == text.size()) {
            flushWord();
            if (c == '\n' && !line.empty() && lines < maxLines) {
                drawText(x, y, size, color, line);
                y += lineHeight;
                ++lines;
                line.clear();
            }
            if (lines >= maxLines) break;
        } else {
            word.push_back(c);
        }
    }
    if (!line.empty() && lines < maxLines) {
        drawText(x, y, size, color, fitText(line, size, maxWidth));
        y += lineHeight;
    }
    return y;
}

void drawModalFrame(const ModalView& m) {
    beginFrame();
    if (!g_pixels) return;

    // Same visual language as the Wizard, but without the two right-side cards.
    drawText(42, 24, 24, C_TEXT, "Horizon");
    drawText(134, 24, 24, C_CYAN, "OC");
    drawText(177, 24, 24, C_MUTED, "/");
    drawText(198, 24, 24, C_TEXT, "Undervolting Wizard");
    roundedRect(1085, 20, 150, 34, 17, C_PANEL_2);
    drawTextRight(1218, 26, 15, C_MUTED, "v" + m.version);
    fillRect(40, 70, 1200, 1, C_BORDER);

    // Quiet/dimmed guide backdrop behind the modal.
    roundedRect(40, 103, 1200, 557, 22, mix(C_BG, C_PANEL, 50));
    fillRect(72, 126, 1136, 2, mix(C_BG, C_BORDER, 65));
    for (int i = 0; i < 7; ++i) {
        const int x = 72 + 1136 * i / 6;
        fillCircle(x, 127, 5, mix(C_BG, C_BORDER, 70));
    }

    const int x = 145, y = 120, w = 990, h = 515;
    const u32 accent = modalToneColor(m.tone);
    roundedBorder(x, y, w, h, 22, mix(C_BORDER, accent, 52), C_PANEL, 2);
    drawText(x + 38, y + 28, 15, accent, m.eyebrow.empty() ? "HOC UNDERVOLTING WIZARD" : m.eyebrow);
    drawText(x + 38, y + 61, 34, C_TEXT, fitText(m.title, 34, w - 76));
    fillRect(x + 38, y + 111, w - 76, 1, C_BORDER);

    int yy = y + 136;
    for (const std::string& paragraph : m.body) {
        if (paragraph.empty()) { yy += 12; continue; }
        const bool warning = paragraph.rfind("If normal CFW", 0) == 0 ||
                             paragraph.rfind("Important:", 0) == 0;
        yy = drawWrappedText(x + 38, yy, 19, warning ? accent : C_TEXT, paragraph,
                             w - 76, 27, 3);
        yy += 8;
        if (yy > y + h - 135) break;
    }

    if (!m.primaryAction.empty()) {
        const int by = y + h - 78;
        if (!m.tertiaryAction.empty()) {
            // Decision modal: one clear Yes / No / Exit row.
            drawActionButton(x + 38,  by, 296, 48, "A : " + m.primaryAction);
            drawActionButton(x + 347, by, 296, 48, "X : " + m.tertiaryAction);
            if (!m.secondaryAction.empty())
                drawActionButton(x + 656, by, 296, 48, "B : " + m.secondaryAction);
        } else if (!m.secondaryAction.empty()) {
            drawActionButton(x + 38, by, 445, 48, "A : " + m.primaryAction);
            drawActionButton(x + 507, by, 445, 48, "B : " + m.secondaryAction);
        } else {
            drawActionButton(x + 38, by, w - 76, 48, "A : " + m.primaryAction);
        }
    }

    endFrame();
}

void drawStressFrame(const StressView& s) {
    beginFrame();
    if (!g_pixels) return;

    drawText(42, 24, 24, C_TEXT, "Horizon");
    drawText(134, 24, 24, C_CYAN, "OC");
    drawText(177, 24, 24, C_MUTED, "/");
    drawText(198, 24, 24, C_TEXT, "Stability Test");
    fillRect(40, 70, 1200, 1, C_BORDER);

    const int x = 90, y = 110, w = 1100, h = 530;
    drawCard(x, y, w, h, true);
    drawLabel(x + 34, y + 28, "BUILT-IN STABILITY TEST");
    drawText(x + 34, y + 61, 31, C_TEXT, fitText(s.title, 31, w - 68));
    drawText(x + 34, y + 104, 16, C_MUTED, fitText(s.subtitle, 16, w - 68));

    const std::uint64_t totalMs = std::uint64_t(std::max(1, s.durationSeconds)) * 1000ULL;
    const double progress = std::min(1.0, double(s.elapsedMs) / double(totalMs));
    const int barX = x + 34, barY = y + 161, barW = w - 68;
    roundedRect(barX, barY, barW, 18, 9, C_DARK);
    roundedRect(barX, barY, std::max(18, int(barW * progress)), 18, 9, C_CYAN);

    const std::uint64_t sec = s.elapsedMs / 1000ULL;
    char timeBuf[64];
    std::snprintf(timeBuf, sizeof(timeBuf), "%02llu:%02llu / %02d:%02d",
                  (unsigned long long)(sec / 60ULL), (unsigned long long)(sec % 60ULL),
                  s.durationSeconds / 60, s.durationSeconds % 60);
    drawText(x + 34, y + 192, 24, C_TEXT, timeBuf);
    char pctBuf[16];
    std::snprintf(pctBuf, sizeof(pctBuf), "%d%%", int(progress * 100.0));
    drawTextRight(x + w - 34, y + 194, 20, C_CYAN, pctBuf);

    const int statY = y + 250;
    const int colW = 245;
    struct Stat { const char* label; std::uint64_t value; u32 color; } stats[4] = {
        {"CPU passes", s.cpuPasses, C_TEXT}, {"RAM loops", s.ramLoops, C_TEXT},
        {"Errors", s.errors, s.errors ? C_RED : C_GREEN}, {"Mismatches", s.mismatches, s.mismatches ? C_RED : C_GREEN}
    };
    for (int i = 0; i < 4; ++i) {
        const int sx = x + 34 + i * (colW + 10);
        roundedRect(sx, statY, colW, 88, 13, C_PANEL_2);
        drawText(sx + 16, statY + 13, 14, C_MUTED, stats[i].label);
        drawText(sx + 16, statY + 40, 26, stats[i].color, std::to_string(stats[i].value));
    }

    if (!s.detail1.empty()) drawText(x + 34, y + 365, 17, C_MUTED, fitText(s.detail1, 17, w - 68));
    if (!s.detail2.empty()) drawText(x + 34, y + 395, 17, C_MUTED, fitText(s.detail2, 17, w - 68));
    if (!s.ramTest.empty()) drawText(x + 34, y + 425, 17, C_TEXT, fitText("RAM test: " + s.ramTest, 17, w - 68));

    roundedRect(x + 34, y + h - 66, w - 68, 42, 11, C_DARK);
    drawText(x + 49, y + h - 57, 17, C_MUTED, "B");
    drawText(x + 78, y + h - 57, 17, C_TEXT, "Cancel test - does not count as FAIL");

    endFrame();
}

} // namespace

bool init() {
    if (g_initialized) return true;

    Result rc = plInitialize(PlServiceType_User);
    if (R_FAILED(rc)) return false;
    g_plInitialized = true;

    PlFontData font{};
    rc = plGetSharedFontByType(&font, PlSharedFontType_Standard);
    if (R_FAILED(rc)) { shutdown(); return false; }

    if (FT_Init_FreeType(&g_ft)) { shutdown(); return false; }
    if (FT_New_Memory_Face(g_ft, static_cast<const FT_Byte*>(font.address), FT_Long(font.size), 0, &g_face)) {
        shutdown();
        return false;
    }

    rc = framebufferCreate(&g_fb, nwindowGetDefault(), W, H, PIXEL_FORMAT_RGBA_8888, 2);
    if (R_FAILED(rc)) { shutdown(); return false; }
    rc = framebufferMakeLinear(&g_fb);
    if (R_FAILED(rc)) { shutdown(); return false; }

    g_initialized = true;
    return true;
}

void shutdown() {
    if (g_initialized) {
        framebufferClose(&g_fb);
        g_initialized = false;
    }
    if (g_face) { FT_Done_Face(g_face); g_face = nullptr; }
    if (g_ft) { FT_Done_FreeType(g_ft); g_ft = nullptr; }
    if (g_plInitialized) { plExit(); g_plInitialized = false; }
    g_pixels = nullptr;
    g_lines.clear();
}

bool isInitialized() { return g_initialized; }

void begin(const View& view) {
    g_view = view;
    g_lines.clear();
}

void printLeft(int logicalRow, const char* text) {
    if (!text) return;
    g_lines.push_back({logicalRow, stripAnsi(text)});
}

void present() {
    if (!g_initialized) return;
    beginFrame();
    if (!g_pixels) return;
    drawHeader();
    drawProgress();
    drawMainCard();
    if (!g_view.fullWidthLayout) {
        if (g_view.preparationLayout) {
            drawPreparationCard();
        } else {
            drawInstructionCard();
            if (!g_view.hideValuesCard) drawValuesCard();
        }
    }
    endFrame();
}

void presentModal(const ModalView& view) {
    if (!g_initialized) return;
    drawModalFrame(view);
}

void presentStress(const StressView& view) {
    if (!g_initialized) return;
    drawStressFrame(view);
}

} // namespace gui
