#include "asi/pso.hpp"

#include <algorithm>
#include <cmath>
#include <random>

namespace asi {

ParticleSwarmOptimizer::ParticleSwarmOptimizer(int numParticles, int maxIterations, int seed)
    : numParticles_(std::max(6, numParticles)),
      maxIterations_(std::max(3, maxIterations)),
      seed_(seed) {}

PsoDispatchResult ParticleSwarmOptimizer::optimizeHour(
    double demand,
    double solarAvail,
    double windAvail,
    double prevGenPower,
    double currentSoc,
    const Settings& s
) {
    std::mt19937 rng(seed_++);

    // Generator dispatch bounds enforcing ramp-rate limits
    double genMin = std::max(0.0, prevGenPower - s.generatorRampLimit);
    double genMax = std::min(s.generatorCapacity, prevGenPower + s.generatorRampLimit);
    if (genMin > genMax) genMin = genMax;

    // Battery dispatch bounds (positive = discharge, negative = charge)
    double maxDischarge = std::min(s.batteryPower, std::max(0.0, currentSoc - s.reserveSoc) * s.dischargeEff);
    double maxCharge = std::min(s.batteryPower, std::max(0.0, s.batteryCapacity - currentSoc) / s.chargeEff);
    double batMin = -maxCharge;
    double batMax = maxDischarge;

    // Cost evaluation objective function
    auto evaluate = [&](double pgen, double pbat) -> double {
        double ren = solarAvail + windAvail;
        double net = ren + pgen + pbat;
        double unserved = std::max(0.0, demand - net);

        double fuel = pgen * s.generatorCost;

        // Battery degradation: wear cost increases exponentially with deep discharge
        double dodFactor = std::max(0.0, 0.30 - currentSoc / s.batteryCapacity) * 3.0;
        double effectiveWear = s.wearCost + s.batteryDegradationCost * dodFactor;
        double wear = std::abs(pbat) * effectiveWear;

        double unservedCost = unserved * s.unservedPenalty;
        return fuel + wear + unservedCost;
    };

    struct Particle {
        double pgen = 0.0;
        double pbat = 0.0;
        double vgen = 0.0;
        double vbat = 0.0;
        double pbestGen = 0.0;
        double pbestBat = 0.0;
        double pbestCost = 1e30;
    };

    std::vector<Particle> swarm(numParticles_);
    std::uniform_real_distribution<double> distGen(genMin, genMax);
    std::uniform_real_distribution<double> distBat(batMin, batMax);

    for (auto& p : swarm) {
        p.pgen = distGen(rng);
        p.pbat = distBat(rng);
        p.vgen = (distGen(rng) - distGen(rng)) * 0.1;
        p.vbat = (distBat(rng) - distBat(rng)) * 0.1;
        p.pbestGen = p.pgen;
        p.pbestBat = p.pbat;
        p.pbestCost = evaluate(p.pgen, p.pbat);
    }

    // Swarm optimization with local ring neighborhood topology
    const double w = 0.729;    // Inertia weight
    const double c1 = 1.494;   // Cognitive coefficient
    const double c2 = 1.494;   // Social coefficient (local neighbor)

    std::uniform_real_distribution<double> dist01(0.0, 1.0);

    for (int iter = 0; iter < maxIterations_; ++iter) {
        for (int i = 0; i < numParticles_; ++i) {
            // Determine local neighborhood best (ring topology: left, self, right)
            int left = (i - 1 + numParticles_) % numParticles_;
            int right = (i + 1) % numParticles_;

            int lbestIdx = i;
            if (swarm[left].pbestCost < swarm[lbestIdx].pbestCost) lbestIdx = left;
            if (swarm[right].pbestCost < swarm[lbestIdx].pbestCost) lbestIdx = right;

            double lbestGen = swarm[lbestIdx].pbestGen;
            double lbestBat = swarm[lbestIdx].pbestBat;

            auto& p = swarm[i];
            double r1 = dist01(rng);
            double r2 = dist01(rng);

            p.vgen = w * p.vgen + c1 * r1 * (p.pbestGen - p.pgen) + c2 * r2 * (lbestGen - p.pgen);
            p.vbat = w * p.vbat + c1 * r1 * (p.pbestBat - p.pbat) + c2 * r2 * (lbestBat - p.pbat);

            // Clamp velocity
            double maxVGen = (genMax - genMin) * 0.25;
            double maxVBat = (batMax - batMin) * 0.25;
            p.vgen = std::clamp(p.vgen, -maxVGen, maxVGen);
            p.vbat = std::clamp(p.vbat, -maxVBat, maxVBat);

            // Update position
            p.pgen = std::clamp(p.pgen + p.vgen, genMin, genMax);
            p.pbat = std::clamp(p.pbat + p.vbat, batMin, batMax);

            // Evaluate
            double currentCost = evaluate(p.pgen, p.pbat);
            if (currentCost < p.pbestCost) {
                p.pbestCost = currentCost;
                p.pbestGen = p.pgen;
                p.pbestBat = p.pbat;
            }
        }
    }

    // Find best overall particle
    int globalBestIdx = 0;
    for (int i = 1; i < numParticles_; ++i) {
        if (swarm[i].pbestCost < swarm[globalBestIdx].pbestCost) {
            globalBestIdx = i;
        }
    }

    PsoDispatchResult res;
    res.generatorPower = swarm[globalBestIdx].pbestGen;
    res.batteryAction = swarm[globalBestIdx].pbestBat;
    res.expectedCost = swarm[globalBestIdx].pbestCost;
    res.iterationsUsed = maxIterations_;
    return res;
}

} // namespace asi

