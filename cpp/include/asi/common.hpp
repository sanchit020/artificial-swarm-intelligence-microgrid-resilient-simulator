#pragma once

#include <array>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace asi {

// Mathematical and system constants
constexpr double PI = 3.14159265358979323846;
constexpr int NUM_CONSUMERS = 50;
constexpr int HOURS_PER_DAY = 24;
constexpr int SUBSTATION_COUNT = 8;

// Aliases for compact mathematical notation
constexpr int N = NUM_CONSUMERS;
constexpr int H = HOURS_PER_DAY;

// Edge between two named grid entities (e.g., {"Solar", "S1"}, {"S1", "S2"}, {"S1", "C001"})
using Edge = std::pair<std::string, std::string>;

// Microgrid simulation parameters and cost weights
struct Settings {
    double demandScale = 1.0;
    double solarScale = 1.0;
    double windScale = 1.0;
    double generatorCapacity = 150.0;
    double batteryCapacity = 120.0;
    double batteryPower = 35.0;
    double initialSoc = 60.0;
    double reserveSoc = 18.0;
    double chargeEff = 0.94;
    double dischargeEff = 0.94;
    double generatorCost = 115.0;
    double wearCost = 8.0;
    double unservedPenalty = 18000.0;
    double reservePenalty = 350.0;
    int population = 8;
    int generations = 3;
    int seed = 2026;
};

// Simulation and network configuration including contingency overrides
struct Config {
    Settings s;
    int seed = 2026;
    std::string mode = "simulate";
    std::array<int, HOURS_PER_DAY> actions{};
    std::map<Edge, double> lineOverrides;
    std::map<Edge, double> feederOverrides;
    std::map<std::string, double> subOverrides;
    std::map<Edge, double> feeders;
};

// Flow allocation results for a single dispatch hour
struct FlowResult {
    double demand = 0.0;
    double delivered = 0.0;
    double unserved = 0.0;
    double criticalDelivered = 0.0;
    double criticalDemand = 0.0;
    std::map<std::string, double> sourceUsed;
    std::map<std::string, double> cd;  // Consumer delivered power (MW)
    std::map<std::string, double> cu;  // Consumer unserved power (MW)
    std::map<Edge, double> sourceFlow;
    std::map<Edge, double> meshFlow;
    std::map<Edge, double> feedFlow;
};

// 24-hour simulation results including hourly telemetry rows and system metrics
struct Sim {
    std::vector<std::map<std::string, double>> rows;
    double cost = 0.0;
    double unserved = 0.0;
    double delivered = 0.0;
    double demand = 0.0;
    double generator = 0.0;
    double curtailment = 0.0;
    double throughput = 0.0;
    double finalSoc = 0.0;
    double objective = 0.0;
    double criticalDelivered = 0.0;
    double criticalDemand = 0.0;
    double criticalPct = 100.0;
};

} // namespace asi
