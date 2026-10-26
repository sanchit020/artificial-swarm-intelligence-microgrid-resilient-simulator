#pragma once

#include "asi/common.hpp"

#include <array>

namespace asi {

// 24-hour generated environmental and demand profiles
struct HourlyProfiles {
    std::array<double, HOURS_PER_DAY> demand{};
    std::array<double, HOURS_PER_DAY> solar{};
    std::array<double, HOURS_PER_DAY> wind{};
};

// Deterministic pseudo-random generation of diurnal solar, wind, and demand profiles
HourlyProfiles generateHourlyProfiles(int seed, const Settings& s);

// Execute a 24-hour simulation across battery dispatch actions, generator dispatch,
// state-of-charge tracking, and hourly flow allocations
Sim simulate(const Config& cfg, const std::array<int, HOURS_PER_DAY>& actions);

} // namespace asi
