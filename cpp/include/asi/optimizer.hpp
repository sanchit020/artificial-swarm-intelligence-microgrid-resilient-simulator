#pragma once

#include "asi/common.hpp"

#include <array>
#include <utility>

namespace asi {

// Genetic algorithm optimizer for 24-hour battery schedule optimization
// Optimizes chromosome of discrete actions a_h in {-2, -1, 0, 1, 2}
// Returns the best schedule and its complete simulation results
std::pair<std::array<int, HOURS_PER_DAY>, Sim> optimize(Config cfg);

} // namespace asi
