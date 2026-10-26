#pragma once

#include "asi/common.hpp"

#include <map>
#include <string>
#include <vector>

namespace asi {

// Consumer identification and criticality classification
std::string consumerId(int i);
bool isCriticalConsumer(int i);

// Backward-compatibility inline helpers
inline std::string C(int i) { return consumerId(i); }
inline bool critical(int i) { return isCriticalConsumer(i); }

// Grid topology definitions
const std::vector<std::string>& substations();
const std::vector<Edge>& meshCorridors();
const std::vector<std::string>& energySources();
std::map<Edge, double> defaultSourceCapacities();

// Baseline consumer demand distribution (sums to 235 MW nominal)
std::map<std::string, double> baselineDemands();
inline std::map<std::string, double> demands() { return baselineDemands(); }

// Configuration parsing and validation
Config readConfig(const std::string& path);
void validateConfig(const Config& cfg);

// String utility function
std::vector<std::string> splitString(const std::string& s, char delimiter);

} // namespace asi
