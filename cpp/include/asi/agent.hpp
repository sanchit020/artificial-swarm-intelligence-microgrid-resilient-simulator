#pragma once

#include "asi/common.hpp"
#include <map>
#include <string>
#include <vector>

namespace asi {

// Substation intelligent agent representing an autonomous node in the microgrid
class SubstationAgent {
public:
    std::string id;
    double voltageAngle = 0.0;     // Bus angle (degrees)
    double voltageMag = 1.0;       // Bus voltage (p.u.)
    double localGeneration = 0.0;  // DER injection directly at this substation (MW)
    double localDemand = 0.0;      // Consumer load served through this substation (MW)
    double netSurplus = 0.0;       // Generation minus demand (MW)
    int islandId = 0;              // Microgrid island / connected component
    bool isFaulted = false;        // Substation status

    std::vector<std::string> neighbors;
    std::map<std::string, double> lineCapacities; // Available capacity to neighbors

    SubstationAgent() = default;
    explicit SubstationAgent(std::string name);

    // Updates local sensor telemetry
    void sense(
        double genInjected,
        double demandRequested,
        double vAngle,
        double vMag,
        int island,
        const std::map<std::string, double>& neighborCaps
    );

    // Negotiates peer-to-peer power exchange with adjacent neighbors
    std::vector<AgentMessage> coordinateWithNeighbors(
        std::map<std::string, SubstationAgent>& peers,
        int hour
    );
};

// DER Agent managing generation resources (Solar, Wind, Battery, Main Generator)
class DerAgent {
public:
    std::string id;
    double maxCapacity = 0.0;
    double currentOutput = 0.0;
    double rampLimit = 35.0;
    double marginalCost = 115.0;

    DerAgent() = default;
    DerAgent(std::string name, double cap, double ramp, double cost);

    // Generates supply offer message
    AgentMessage offerPower(double wanted, int hour);
};

// Decentralized multi-agent coordinator orchestrating peer-to-peer grid operations
class MultiAgentGridSystem {
public:
    MultiAgentGridSystem(int seed = 2026);

    void initializeAgents(const Settings& settings);

    // Executes 1-hour decentralized agent sense, negotiate, and dispatch cycle
    std::vector<AgentMessage> stepHour(
        int hour,
        const std::map<std::string, double>& subGenerations,
        const std::map<std::string, double>& subDemands,
        const std::map<std::string, double>& busAngles,
        const std::map<std::string, double>& busVoltages,
        const std::map<Edge, double>& activeLineCaps
    );

    const std::map<std::string, SubstationAgent>& substationAgents() const { return subs_; }
    const std::map<std::string, DerAgent>& derAgents() const { return ders_; }
    const std::vector<AgentMessage>& messageLog() const { return messageLog_; }

private:
    int seed_;
    std::map<std::string, SubstationAgent> subs_;
    std::map<std::string, DerAgent> ders_;
    std::vector<AgentMessage> messageLog_;
};

} // namespace asi

