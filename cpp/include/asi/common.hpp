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

// Agent peer-to-peer coordination message
struct AgentMessage {
    int hour = 0;
    std::string sender;
    std::string receiver;
    std::string type;       // "REQUEST_POWER", "OFFER_POWER", "REROUTE_ALERT", "LINE_TRIPPED", "SHED_ALERT"
    double powerMw = 0.0;
    std::string detail;
};

// Microgrid simulation parameters and physical operational constraints
struct Settings {
    double demandScale = 1.0;
    double solarScale = 1.0;
    double windScale = 1.0;
    double hydroScale = 1.0;
    double hydroCapacity = 40.0;
    double generatorCapacity = 175.0;
    double batteryCapacity = 160.0;
    double batteryPower = 50.0;
    double initialSoc = 80.0;
    double reserveSoc = 25.0;
    double chargeEff = 0.94;
    double dischargeEff = 0.94;
    double substationStorageCapacity = 15.0; // MWh per substation (120 MWh total across 8 substations)
    double substationStoragePower = 6.0;     // Max MW charge/discharge per substation
    double generatorCost = 115.0;
    double wearCost = 8.0;
    double unservedPenalty = 18000.0;
    double reservePenalty = 350.0;
    int population = 8;
    int generations = 3;
    int seed = 2026;

    // Physical constraints and electrical engineering parameters
    double generatorRampLimit = 35.0;    // Max MW/hour ramp rate for thermal generation
    double batteryDegradationCost = 2.5; // Additional $/MWh DoD aging wear
    double commLatencyMs = 15.0;         // Inter-agent communication delay (ms)
    double commPacketDropRate = 0.02;    // Simulated packet loss rate

    // Centralized ASI and Swarm Intelligence parameters
    int psoParticles = 12;               // Number of particles in PSO resource swarm
    int psoIterations = 10;              // Iterations per dispatch hour
    int acoAnts = 10;                    // Artificial ants for dynamic rerouting
    double acoEvaporation = 0.15;        // Pheromone evaporation rate
    std::string dispatchMode = "swarm";  // "swarm" (Decentralized ASI) or "centralized" (Baseline)
};

// Simulation and network configuration including contingency overrides
struct Config {
    Settings s;
    int seed = 2026;
    std::string mode = "simulate";       // "simulate" or "optimize"
    std::string dispatchMode = "swarm";  // "swarm" (Decentralized ASI) or "centralized"
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
    double hydroUsed = 0.0;
    double substationStorageDischarged = 0.0;
    double substationStorageCharged = 0.0;
    std::map<std::string, double> sourceUsed;
    std::map<std::string, double> cd;  // Consumer delivered power (MW)
    std::map<std::string, double> cu;  // Consumer unserved power (MW)
    std::map<Edge, double> sourceFlow;
    std::map<Edge, double> meshFlow;
    std::map<Edge, double> feedFlow;

    // Electrical DC power flow telemetry
    std::map<std::string, double> busAngles;   // Bus voltage angle in degrees
    std::map<std::string, double> busVoltages; // Estimated bus voltage in p.u.
    std::map<Edge, double> lineLosses;         // I^2 * R transmission losses in MW
    double totalLosses = 0.0;                  // Total hourly transmission losses (MW)
    double frequencyDeviation = 0.0;           // Delta f from nominal 60.0 Hz
    double minVoltage = 1.0;                   // Minimum bus voltage p.u.
    int islandCount = 1;                       // Number of electrical islands
    double cascadingContainment = 1.0;         // 1.0 = zero cascading failure
};

// 24-hour simulation results including hourly telemetry rows and system metrics
struct Sim {
    std::vector<std::map<std::string, double>> rows;
    double cost = 0.0;
    double unserved = 0.0;
    double delivered = 0.0;
    double demand = 0.0;
    double generator = 0.0;
    double hydro = 0.0;
    double curtailment = 0.0;
    double throughput = 0.0;
    double substationStorageThroughput = 0.0;
    double finalSoc = 0.0;
    double objective = 0.0;
    double criticalDelivered = 0.0;
    double criticalDemand = 0.0;
    double criticalPct = 100.0;

    // Advanced Resilience & Electrical Metrics
    double recoveryTime = 0.0;             // Hours required to restore critical load to >=99%
    double criticalRestorationPct = 100.0; // Mean critical load service across 24h
    int islandCount = 1;                   // Number of microgrid islands formed
    double cascadingContainment = 1.0;     // Ratio of un-tripped lines after overload check
    double totalLosses = 0.0;              // Cumulative 24h transmission losses (MWh)
    double minVoltage = 1.0;               // System minimum bus voltage p.u.
    double maxFreqDev = 0.0;               // Maximum system frequency deviation (Hz)

    // Decentralized agent communication log
    std::vector<AgentMessage> messages;
};

} // namespace asi
