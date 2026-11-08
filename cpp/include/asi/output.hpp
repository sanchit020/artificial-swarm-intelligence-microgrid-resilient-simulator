#pragma once

#include "asi/common.hpp"

#include <array>
#include <string>
#include <vector>

namespace asi {

// Escapes special characters for RFC 4180 CSV export
std::string escapeCsv(const std::string& s);

// Exports 24-hour simulation telemetry rows to CSV
void exportHourlyCsv(const std::string& path, const Sim& result);

// Exports key-value simulation metrics summary file
void exportSummary(const std::string& path, const std::array<int, HOURS_PER_DAY>& actions, const Sim& result);

// Exports decentralized multi-agent communication log to CSV
void exportAgentMessages(const std::string& path, const std::vector<AgentMessage>& messages);

} // namespace asi
