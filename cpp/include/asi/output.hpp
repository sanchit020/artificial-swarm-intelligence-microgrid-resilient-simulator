#pragma once

#include "asi/common.hpp"

#include <array>
#include <string>

namespace asi {

// Escape a string for CSV formatting (handles quotes, commas, newlines)
std::string escapeCsv(const std::string& s);

// Export hourly detailed results (all metrics, feeder/transmission/source flows) to CSV
void exportHourlyCsv(const std::string& path, const Sim& result);

// Export 24-hour summary metrics and chosen battery action schedule to key-value summary file
void exportSummary(const std::string& path, const std::array<int, HOURS_PER_DAY>& actions, const Sim& result);

} // namespace asi
