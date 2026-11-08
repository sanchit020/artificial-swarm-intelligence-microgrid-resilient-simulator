#include "asi/aco.hpp"
#include "asi/network.hpp"
#include "asi/power_flow.hpp"

#include <algorithm>
#include <cmath>
#include <random>

namespace asi {

AntColonyOptimizer::AntColonyOptimizer(int numAnts, double evaporation, int seed)
    : numAnts_(std::max(4, numAnts)), evaporation_(std::clamp(evaporation, 0.01, 0.90)), seed_(seed) {
    reset();
}

void AntColonyOptimizer::reset() {
    pheromone_.clear();
    const auto& corridors = meshCorridors();
    for (const auto& [u, v] : corridors) {
        pheromone_[{u, v}] = 1.0;
        pheromone_[{v, u}] = 1.0;
    }
}

AcoRoutingWeights AntColonyOptimizer::optimizeRoutes(
    const std::map<Edge, double>& activeLineCaps,
    const std::map<std::string, double>& subSurplus,
    const std::map<std::string, double>& subDeficit
) {
    AcoRoutingWeights result;
    const auto& corridors = meshCorridors();
    const auto& lineParams = transmissionLineParams();
    std::mt19937 rng(seed_++);

    // 1. Evaporation: tau = max(tau_min, (1 - rho) * tau)
    for (const auto& [e, tau] : pheromone_) {
        double newTau = std::max(0.05, (1.0 - evaporation_) * tau);
        auto itCap = activeLineCaps.find(e);
        if (itCap != activeLineCaps.end() && itCap->second < 1e-4) {
            newTau = 0.01; // Outage/tripped corridor loses pheromone rapidly
        }
        pheromone_[e] = newTau;
    }

    // 2. Identify surplus sources and deficit sinks
    std::vector<std::string> sources;
    std::vector<std::string> sinks;
    for (const auto& [sub, val] : subSurplus) {
        if (val > 1.0) sources.push_back(sub);
    }
    for (const auto& [sub, val] : subDeficit) {
        if (val > 1.0) sinks.push_back(sub);
    }
    if (sources.empty()) sources = {"S1", "S3"};
    if (sinks.empty()) sinks = {"S5", "S7"};

    // 3. Ants search for optimal / alternative routing paths
    std::vector<std::vector<std::string>> successfulPaths;

    for (int a = 0; a < numAnts_; ++a) {
        std::string current = sources[a % sources.size()];
        std::string target = sinks[(a / sources.size()) % sinks.size()];
        if (current == target) continue;

        std::vector<std::string> path = {current};
        std::vector<std::string> visited = {current};

        for (int step = 0; step < 6 && current != target; ++step) {
            // Find candidates
            std::vector<std::pair<std::string, double>> candidates;
            for (const auto& [u, v] : corridors) {
                std::string nxt;
                if (u == current) nxt = v;
                else if (v == current) nxt = u;
                else continue;

                if (std::find(visited.begin(), visited.end(), nxt) != visited.end()) continue;

                auto itCap = activeLineCaps.find({current, nxt});
                double cap = (itCap != activeLineCaps.end()) ? itCap->second : 0.0;
                if (cap < 1e-4) continue; // Tripped corridor

                double tau = pheromone_[{current, nxt}];
                auto itP = lineParams.find({current, nxt});
                double x = (itP != lineParams.end()) ? itP->second.x : 0.08;
                double eta = (1.0 / (x + 0.01)) * (cap / 48.0);

                double prob = std::pow(tau, 1.0) * std::pow(eta, 2.0);
                candidates.push_back({nxt, prob});
            }

            if (candidates.empty()) break;

            // Roulette wheel selection
            double sumProb = 0.0;
            for (const auto& c : candidates) sumProb += c.second;
            std::uniform_real_distribution<double> dist(0.0, sumProb);
            double pick = dist(rng);
            double accum = 0.0;
            std::string nextNode = candidates.front().first;
            for (const auto& c : candidates) {
                accum += c.second;
                if (pick <= accum) {
                    nextNode = c.first;
                    break;
                }
            }

            current = nextNode;
            path.push_back(current);
            visited.push_back(current);
        }

        if (current == target && path.size() >= 2) {
            successfulPaths.push_back(path);

            // Calculate path quality
            double pathReactance = 0.0;
            for (size_t i = 0; i + 1 < path.size(); ++i) {
                auto itP = lineParams.find({path[i], path[i + 1]});
                pathReactance += (itP != lineParams.end()) ? itP->second.x : 0.08;
            }
            double deltaTau = 2.0 / std::max(0.01, pathReactance);

            // Deposit pheromone along path
            for (size_t i = 0; i + 1 < path.size(); ++i) {
                pheromone_[{path[i], path[i + 1]}] = std::min(5.0, pheromone_[{path[i], path[i + 1]}] + deltaTau);
                pheromone_[{path[i + 1], path[i]}] = std::min(5.0, pheromone_[{path[i + 1], path[i]}] + deltaTau);
            }
        }
    }

    result.pheromoneLevels = pheromone_;
    result.discoveredDetours = successfulPaths;

    // Normalize corridor priorities
    for (const auto& [e, tau] : pheromone_) {
        result.corridorPriority[e] = tau / 5.0; // Normalized in [0, 1]
    }

    return result;
}

} // namespace asi

