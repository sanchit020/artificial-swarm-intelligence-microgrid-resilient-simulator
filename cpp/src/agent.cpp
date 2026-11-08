#include "asi/agent.hpp"
#include "asi/network.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace asi {

SubstationAgent::SubstationAgent(std::string name) : id(std::move(name)) {
    // Populate static neighbors from mesh topology
    const auto& corridors = meshCorridors();
    for (const auto& [u, v] : corridors) {
        if (u == id) neighbors.push_back(v);
        else if (v == id) neighbors.push_back(u);
    }
    // Remove duplicates
    std::sort(neighbors.begin(), neighbors.end());
    neighbors.erase(std::unique(neighbors.begin(), neighbors.end()), neighbors.end());
}

void SubstationAgent::sense(
    double genInjected,
    double demandRequested,
    double vAngle,
    double vMag,
    int island,
    const std::map<std::string, double>& neighborCaps
) {
    localGeneration = genInjected;
    localDemand = demandRequested;
    netSurplus = genInjected - demandRequested;
    voltageAngle = vAngle;
    voltageMag = vMag;
    islandId = island;
    lineCapacities = neighborCaps;
}

std::vector<AgentMessage> SubstationAgent::coordinateWithNeighbors(
    std::map<std::string, SubstationAgent>& peers,
    int hour
) {
    std::vector<AgentMessage> msgs;

    // Check for tripped corridors
    for (const auto& n : neighbors) {
        double cap = lineCapacities.count(n) ? lineCapacities[n] : 0.0;
        if (cap < 1e-4) {
            AgentMessage alert;
            alert.hour = hour;
            alert.sender = id;
            alert.receiver = n;
            alert.type = "LINE_TRIPPED";
            alert.powerMw = 0.0;
            alert.detail = "Corridor " + id + " <-> " + n + " unavailable. Initiating autonomous rerouting.";
            msgs.push_back(alert);
        }
    }

    // If local deficit exists, negotiate power transfer from neighbors
    if (netSurplus < -0.5) {
        double needed = -netSurplus;

        // Sort neighbors by available line capacity
        std::vector<std::string> sortedNeighbors = neighbors;
        std::sort(sortedNeighbors.begin(), sortedNeighbors.end(), [&](const std::string& a, const std::string& b) {
            double capA = lineCapacities.count(a) ? lineCapacities[a] : 0.0;
            double capB = lineCapacities.count(b) ? lineCapacities[b] : 0.0;
            return capA > capB;
        });

        for (const auto& n : sortedNeighbors) {
            if (needed <= 0.1) break;
            double cap = lineCapacities.count(n) ? lineCapacities[n] : 0.0;
            if (cap < 1.0) continue; // Tripped or congested

            auto itPeer = peers.find(n);
            if (itPeer == peers.end()) continue;

            auto& peer = itPeer->second;

            // Send request message
            double reqPower = std::min({needed, cap, 25.0});
            AgentMessage req;
            req.hour = hour;
            req.sender = id;
            req.receiver = n;
            req.type = "REQUEST_POWER";
            req.powerMw = reqPower;
            req.detail = "Deficit of " + std::to_string(static_cast<int>(needed)) + " MW. Requesting transfer.";
            msgs.push_back(req);

            // Peer evaluates offer
            if (peer.netSurplus > 0.5) {
                double grant = std::min({reqPower, peer.netSurplus, cap});
                peer.netSurplus -= grant;
                netSurplus += grant;
                needed -= grant;

                AgentMessage offer;
                offer.hour = hour;
                offer.sender = n;
                offer.receiver = id;
                offer.type = "OFFER_POWER";
                offer.powerMw = grant;
                offer.detail = "Granted " + std::to_string(static_cast<int>(grant)) + " MW from local reserve.";
                msgs.push_back(offer);
            }
        }

        // If deficit persists, broadcast alert to protect critical consumers
        if (needed > 2.0) {
            AgentMessage alert;
            alert.hour = hour;
            alert.sender = id;
            alert.receiver = "ALL";
            alert.type = "SHED_ALERT";
            alert.powerMw = needed;
            alert.detail = "Autonomous load shed active: prioritizing critical facilities (C003, C010, etc.).";
            msgs.push_back(alert);
        }
    }

    return msgs;
}

DerAgent::DerAgent(std::string name, double cap, double ramp, double cost)
    : id(std::move(name)), maxCapacity(cap), currentOutput(0.0), rampLimit(ramp), marginalCost(cost) {}

AgentMessage DerAgent::offerPower(double wanted, int hour) {
    double possible = std::min(wanted, maxCapacity);
    if (id == "Main Generator") {
        possible = std::min(possible, currentOutput + rampLimit);
    }
    currentOutput = possible;

    AgentMessage msg;
    msg.hour = hour;
    msg.sender = id;
    msg.receiver = "GRID";
    msg.type = "OFFER_POWER";
    msg.powerMw = possible;
    msg.detail = "Dispatched " + std::to_string(static_cast<int>(possible)) + " MW within physical ramp limits.";
    return msg;
}

MultiAgentGridSystem::MultiAgentGridSystem(int seed) : seed_(seed) {
    const auto& subs = substations();
    for (const auto& s : subs) {
        subs_[s] = SubstationAgent(s);
    }
    ders_["Solar"] = DerAgent("Solar", 145.0, 145.0, 0.0);
    ders_["Wind"] = DerAgent("Wind", 55.0, 55.0, 0.0);
    ders_["Battery"] = DerAgent("Battery", 35.0, 35.0, 8.0);
    ders_["Main Generator"] = DerAgent("Main Generator", 175.0, 35.0, 115.0);
}

void MultiAgentGridSystem::initializeAgents(const Settings& s) {
    ders_["Main Generator"].maxCapacity = s.generatorCapacity;
    ders_["Main Generator"].rampLimit = s.generatorRampLimit;
    ders_["Main Generator"].marginalCost = s.generatorCost;
    ders_["Battery"].maxCapacity = s.batteryPower;
}

std::vector<AgentMessage> MultiAgentGridSystem::stepHour(
    int hour,
    const std::map<std::string, double>& subGenerations,
    const std::map<std::string, double>& subDemands,
    const std::map<std::string, double>& busAngles,
    const std::map<std::string, double>& busVoltages,
    const std::map<Edge, double>& activeLineCaps
) {
    std::vector<AgentMessage> hourlyMsgs;

    // 1. Each substation agent senses local status
    for (auto& [name, agent] : subs_) {
        double gen = subGenerations.count(name) ? subGenerations.at(name) : 0.0;
        double dem = subDemands.count(name) ? subDemands.at(name) : 0.0;
        double ang = busAngles.count(name) ? busAngles.at(name) : 0.0;
        double v = busVoltages.count(name) ? busVoltages.at(name) : 1.0;

        std::map<std::string, double> caps;
        for (const auto& n : agent.neighbors) {
            Edge e{name, n};
            caps[n] = activeLineCaps.count(e) ? activeLineCaps.at(e) : 0.0;
        }

        agent.sense(gen, dem, ang, v, 0, caps);
    }

    // 2. Peer-to-peer negotiation
    for (auto& [name, agent] : subs_) {
        auto msgs = agent.coordinateWithNeighbors(subs_, hour);
        hourlyMsgs.insert(hourlyMsgs.end(), msgs.begin(), msgs.end());
    }

    messageLog_.insert(messageLog_.end(), hourlyMsgs.begin(), hourlyMsgs.end());
    return hourlyMsgs;
}

} // namespace asi

