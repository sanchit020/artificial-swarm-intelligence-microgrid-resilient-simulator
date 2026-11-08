#pragma once

#include "asi/common.hpp"
#include <vector>

namespace asi {

// PSO particle dispatch solution
struct PsoDispatchResult {
    double generatorPower = 0.0; // Dispatched thermal generator (MW)
    double batteryAction = 0.0;  // Battery power (MW, positive = discharge, negative = charge)
    double expectedCost = 0.0;   // Estimated operating cost ($)
    int iterationsUsed = 0;      // Iterations executed
};

// Particle Swarm Optimization for decentralized resource dispatch
class ParticleSwarmOptimizer {
public:
    ParticleSwarmOptimizer(int numParticles = 12, int maxIterations = 10, int seed = 2026);

    // Optimizes generator output and battery charge/discharge with ramp and SOC bounds
    PsoDispatchResult optimizeHour(
        double demand,
        double solarAvail,
        double windAvail,
        double prevGenPower,
        double currentSoc,
        const Settings& settings
    );

private:
    int numParticles_;
    int maxIterations_;
    int seed_;
};

} // namespace asi

