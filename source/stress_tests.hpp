#pragma once

#include <cstdint>
#include <string>

namespace stress {

enum class Kind : int {
    Cpu = 1,
    Ram = 2,
    Combined = 3,
    Gpu = 4,
};

enum class Outcome : int {
    Pass = 0,
    Fail,
    Cancelled,
    InitError,
};

struct Result {
    Outcome outcome = Outcome::InitError;
    std::uint64_t elapsedMs = 0;
    std::uint64_t iterations = 0;
    std::uint64_t errors = 0;
    std::uint64_t mismatches = 0;
    std::string detail;
};

const char* kindName(Kind kind);
Result run(Kind kind, int durationSeconds, const std::string& displayTitle = {}, const std::string& displayContext = {});

} // namespace stress
