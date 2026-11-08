#pragma once

#include "asi/common.hpp"
#include <map>
#include <string>
#include <vector>

namespace asi {

// Dynamic corridor routing weights determined by Ant Colony Optimization
struct AcoRoutingWeights {
    std::map<Edge, double> corridorPriority;  // Higher priority = preferred path for ants
    std::map<Edge, double> pheromoneLevels;    // Current pheromone intensity [tau_min, tau_max]
    std::vector<std::vector<std::string>> discoveredDetours; // Alternate paths around tripped lines
};

// Ant Colony Optimization solver for adaptive transmission rerouting
class AntColonyOptimizer {
public:
    AntColonyOptimizer(int numAnts = 10, double evaporation = 0.15, int seed = 2026);

    // Updates pheromone matrix and returns routing weights for current grid condition
    AcoRoutingWeights optimizeRoutes(
        const std::map<Edge, double>& activeLineCaps,
        const std::map<std::string, double>& subSurplus,
        const std::map<std::string, double>& subDeficit
    );

    // Resets or re-initializes pheromone levels
    void reset();

private:
    int numAnts_;
    double evaporation_;
    int seed_;
    std::map<Edge, double> pheromone_;
};

} // namespace asi

