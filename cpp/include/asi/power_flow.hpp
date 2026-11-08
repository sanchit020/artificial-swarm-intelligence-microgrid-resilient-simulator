#pragma once

#include "asi/common.hpp"
#include <map>
#include <string>
#include <vector>

namespace asi {

// Electrical line branch parameters (per-unit on 100 MVA base, 138 kV)
struct LineParam {
    double r = 0.01;      // Resistance (p.u.)
    double x = 0.10;      // Reactance (p.u.)
    double rating = 48.0; // Thermal capacity (MW)
};

// Returns standard electrical parameters for all 16 transmission corridors
const std::map<Edge, LineParam>& transmissionLineParams();

// DC Power Flow solution results
struct DcPowerFlowResult {
    std::map<std::string, double> busAngles;   // Bus voltage angle (degrees)
    std::map<std::string, double> busVoltages; // Estimated voltage magnitude (p.u.)
    std::map<Edge, double> lineLosses;         // I^2 * R transmission losses (MW)
    double totalLosses = 0.0;                  // Total network losses (MW)
    double frequencyDev = 0.0;                 // Frequency deviation (Hz)
    double minVoltage = 1.0;                   // Minimum bus voltage (p.u.)
    int islandCount = 1;                       // Connected components count
    double cascadingContainment = 1.0;         // Fraction of operational lines not cascaded
};

// Solves DC power-flow equations on the active transmission mesh
DcPowerFlowResult solveDcPowerFlow(
    const std::map<std::string, double>& netInjections,
    const std::map<Edge, double>& activeLineCaps,
    const std::map<Edge, double>& allocatedFlows
);

} // namespace asi

