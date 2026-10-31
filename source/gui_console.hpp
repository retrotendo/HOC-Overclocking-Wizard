#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace gui {

struct ValueRow {
    std::string label;
    std::string value;
    bool mismatch = false;
};

struct PreparationRow {
    std::string group;
    std::string label;
    std::string setValue;
    std::string activeValue;
    bool mismatch = false;
};

struct ChartPoint {
    double x = 0.0;
    double performance = 0.0;
    double voltage = 0.0;
    double power = 0.0;
    bool stable = true;
    bool sweetSpot = false;
    bool stableMax = false;
    bool recommended = false;
};

struct View {
    std::string version;
    std::string stageTitle;
    int activeStep = 1;
    bool pulse = false;

    std::string instructionTitle;
    std::string instructionLine1;
    std::string instructionLine2;

    bool haveActiveValues = false;
    ValueRow values[5];

    bool preparationLayout = false;
    bool hideValuesCard = false;
    bool fullWidthLayout = false;
    bool havePreparationActiveValues = false;
    std::vector<PreparationRow> preparationRows;

    bool chartLayout = false;
    std::string chartTitle;
    std::string chartXLabel;
    std::string chartPerformanceLabel = "Performance";
    std::string chartCostLabel = "Voltage";
    std::vector<ChartPoint> chartPoints;
    std::string chartSummary;
};

enum class ModalTone { Cyan, Green, Amber, Red };

struct ModalView {
    std::string version;
    std::string eyebrow;
    std::string title;
    std::vector<std::string> body;
    std::string primaryAction;
    std::string tertiaryAction;
    std::string secondaryAction;
    ModalTone tone = ModalTone::Cyan;
};

struct StressView {
    std::string title;
    std::string subtitle;
    std::string detail1;
    std::string detail2;
    std::uint64_t elapsedMs = 0;
    int durationSeconds = 0;
    std::uint64_t cpuPasses = 0;
    std::uint64_t ramLoops = 0;
    std::uint64_t gpuPasses = 0;
    std::uint64_t errors = 0;
    std::uint64_t mismatches = 0;
    std::string ramTest;
    std::uint64_t ramBytes = 0;
};

bool init();
void shutdown();
bool isInitialized();
void begin(const View& view);
void printLeft(int logicalRow, const char* text);
void present();
void presentModal(const ModalView& view);
void presentStress(const StressView& view);

} // namespace gui
