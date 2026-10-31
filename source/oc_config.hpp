#pragma once

#include <cstdint>
#include <string>

namespace occonfig {

struct LayoutInfo {
    bool ok = false;
    bool hoc251 = false;
    int kipVersion = 0;
};

LayoutInfo detect();

bool setRamPreparation(bool hpMode, std::uint32_t ramMaxMHz,
                       std::uint32_t vdd2Mv, std::uint32_t vddqMv,
                       int dvbShift, int socVmaxMv,
                       const std::uint32_t timings[8], std::string& error);

bool setRamTimings(const std::uint32_t timings[8], std::string& error);
bool setRamMax(std::uint32_t mhz, std::string& error);
bool setVdd2(std::uint32_t mv, std::string& error);
bool setVdd2Uv(std::uint32_t uv, std::string& error);
bool setVddq(std::uint32_t mv, std::string& error);
bool setDvbShift(int shift, std::string& error);
bool setSocVmax(int mv, std::string& error);

bool setSocPoint(std::uint32_t mhz, int mv, std::string& error);
bool getSocPoint(std::uint32_t mhz, int& mv, std::string& error);

bool setGpuPoint(std::uint32_t mhz, int mv, std::string& error);
bool getGpuPoint(std::uint32_t mhz, int& mv, std::string& error);
bool setGpuVmin(int mv, std::string& error);
bool setGpuVmax(int mv, std::string& error);
bool setGpuUvTable(int table, std::string& error);

bool setCpuTuning(int lowUv, int highUv, int tableConf,
                  int lowVminMv, int highVminMv,
                  int maxVoltMv, std::uint32_t maxClockMHz,
                  std::string& error);

bool getCpuTuning(int& lowUv, int& highUv, int& tableConf,
                  int& lowVminMv, int& highVminMv,
                  int& maxVoltMv, std::uint32_t& maxClockMHz,
                  std::string& error);

} // namespace occonfig
