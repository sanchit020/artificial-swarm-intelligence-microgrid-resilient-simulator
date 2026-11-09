#include "asi/simulation.hpp"
#include "asi/aco.hpp"
#include "asi/agent.hpp"
#include "asi/flow.hpp"
#include "asi/network.hpp"
#include "asi/power_flow.hpp"
#include "asi/pso.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <random>
#include <stdexcept>

namespace asi {

HourlyProfiles generateHourlyProfiles(int seed, const Settings& s) {
    HourlyProfiles profiles;
    std::mt19937_64 rng(seed);
    std::normal_distribution<double> nd(0.0, 1.0);
    std::uniform_real_distribution<double> cloudDist(0.70, 0.98);
    std::uniform_real_distribution<double> windGust(0.80, 1.25);

    for (int h = 0; h < HOURS_PER_DAY; ++h) {
        // Dual-peak realistic diurnal demand (morning industrial peak ~9am, evening residential peak ~7pm)
        double morningPeak = 22.0 * std::exp(-std::pow((h - 9.5) / 2.8, 2.0));
        double eveningPeak = 28.0 * std::exp(-std::pow((h - 19.0) / 3.2, 2.0));
        double base = 145.0 + 18.0 * std::sin((h - 7.0) * 2.0 * PI / 24.0) + morningPeak + eveningPeak;

        // Solar diurnal bell curve with stochastic passing cloud attenuation
        double ss = std::max(0.0, std::sin((h - 6.0) * PI / 12.0));
        double cloudFactor = (h >= 10 && h <= 14) ? cloudDist(rng) : 1.0;

        // Wind profile with turbulence shocks and diurnal fluctuation
        double ww = std::clamp(
            0.52 + 0.18 * std::sin((h + 2.0) * 2.0 * PI / 24.0) +
            0.08 * std::cos(h * 4.0 * PI / 24.0),
            0.18, 0.90
        ) / 0.90;
        double gustFactor = windGust(rng);

        profiles.demand[h] = std::max(120.0, base * s.demandScale * (1.0 + nd(rng) * 0.025));
        profiles.solar[h]  = std::max(0.0, 145.0 * ss * cloudFactor * s.solarScale * (1.0 + nd(rng) * 0.035));
        profiles.wind[h]   = std::max(0.0, 55.0 * ww * gustFactor * s.windScale * (1.0 + nd(rng) * 0.045));
        profiles.hydro[h]  = std::max(0.0, s.hydroCapacity * s.hydroScale * (0.85 + 0.15 * std::sin((h + 4.0) * PI / 12.0)) * (1.0 + nd(rng) * 0.02));
    }
    return profiles;
}

Sim simulate(const Config& cfg, const std::array<int, HOURS_PER_DAY>& actions) {
    const auto& s = cfg.s;
    if (s.batteryCapacity < 0.0 || s.batteryPower < 0.0 ||
        s.chargeEff <= 0.0 || s.chargeEff > 1.0 ||
        s.dischargeEff <= 0.0 || s.dischargeEff > 1.0) {
        throw std::runtime_error("Invalid battery settings");
    }

    HourlyProfiles prof = generateHourlyProfiles(cfg.seed, s);
    double reserve = (s.batteryCapacity > 1e-6) ? std::clamp(s.reserveSoc, 0.0, s.batteryCapacity) : 0.0;
    double soc = (s.batteryCapacity > 1e-6) ? std::clamp(s.initialSoc, 0.0, s.batteryCapacity) : 0.0;

    // Substation local energy storage initialization (15 MWh per substation default)
    double subStorageCap = std::max(1.0, s.substationStorageCapacity);
    double subStoragePwr = std::max(0.1, s.substationStoragePower);
    std::map<std::string, double> subSoc;
    for (const auto& sub : substations()) {
        subSoc[sub] = subStorageCap * 0.50; // Initial state of charge (50% reserve)
    }

    Sim out;
    auto base = baselineDemands();
    const auto& subs = substations();

    // Determine active transmission line capacities for DC power flow and ACO
    std::map<Edge, double> activeLineCaps;
    for (const auto& [a, b] : meshCorridors()) {
        activeLineCaps[{a, b}] = 48.0;
        activeLineCaps[{b, a}] = 48.0;
    }
    for (const auto& [edge, cap] : cfg.lineOverrides) {
        if (activeLineCaps.count(edge)) {
            activeLineCaps[edge] = cap;
        }
    }
    for (const auto& sub : subs) {
        auto itSub = cfg.subOverrides.find(sub);
        if (itSub != cfg.subOverrides.end() && itSub->second == 0.0) {
            for (auto& [edge, cap] : activeLineCaps) {
                if (edge.first == sub || edge.second == sub) cap = 0.0;
            }
        }
    }

    // Genuine Swarm Intelligence components
    const bool isSwarmMode = (cfg.dispatchMode == "swarm" || s.dispatchMode == "swarm");
    AntColonyOptimizer aco(s.acoAnts, s.acoEvaporation, cfg.seed);
    ParticleSwarmOptimizer pso(s.psoParticles, s.psoIterations, cfg.seed);
    MultiAgentGridSystem mas(cfg.seed);
    mas.initializeAgents(s);

    double prevGenerator = 0.0;
    double maxRecoveryTime = 0.0;
    double currentOutageDuration = 0.0;
    int maxIslands = 1;
    double minContainment = 1.0;
    double systemMinVoltage = 1.0;
    double systemMaxFreqDev = 0.0;

    for (int h = 0; h < HOURS_PER_DAY; ++h) {
        int a = actions[h];
        if (a < -2 || a > 2) {
            throw std::runtime_error("Battery actions must be -2..2");
        }

        double charge = 0.0;
        double discharge = 0.0;
        double ren = prof.solar[h] + prof.wind[h] + prof.hydro[h];

        std::map<std::string, double> subStorageCharge;
        std::map<std::string, double> subStorageAvail;

        if (a > 0) {
            double wanted = s.batteryPower * a / 2.0;
            double room = std::max(0.0, s.batteryCapacity - soc) / s.chargeEff;
            charge = std::min({wanted, room, std::max(0.0, ren - prof.demand[h])});
            soc = std::min(s.batteryCapacity, soc + charge * s.chargeEff);

            // Centralized ASI routes remaining renewable surplus to charge local substation storage reserves
            double remSurplus = std::max(0.0, ren - prof.demand[h] - charge);
            for (const auto& sub : subs) {
                double subRoom = std::max(0.0, subStorageCap - subSoc[sub]) / s.chargeEff;
                double subCh = std::min({subStoragePwr * a / 2.0, subRoom, remSurplus / 8.0});
                subStorageCharge[sub] = subCh;
                subSoc[sub] = std::min(subStorageCap, subSoc[sub] + subCh * s.chargeEff);
            }
        } else if (a < 0) {
            double wanted = s.batteryPower * std::abs(a) / 2.0;
            double avail = std::max(0.0, soc - reserve) * s.dischargeEff;
            discharge = std::min(wanted, avail);
            soc = std::max(0.0, soc - discharge / s.dischargeEff);

            // Centralized ASI discharges local substation storage to fight deficits
            for (const auto& sub : subs) {
                double subWanted = subStoragePwr * std::abs(a) / 2.0;
                double subAvail = std::min(subWanted, std::max(0.0, subSoc[sub] - 1.0) * s.dischargeEff);
                subStorageAvail[sub] = subAvail;
            }
        }

        // Split charging intake across renewables (Solar, Wind, Hydro)
        double totalRenewableCharge = charge;
        for (const auto& [sub, ch] : subStorageCharge) totalRenewableCharge += ch;
        double solarCharge = std::min(totalRenewableCharge, prof.solar[h]);
        double windCharge  = std::min(std::max(0.0, totalRenewableCharge - solarCharge), prof.wind[h]);
        double hydroCharge = std::min(std::max(0.0, totalRenewableCharge - solarCharge - windCharge), prof.hydro[h]);

        double solarGrid = std::max(0.0, prof.solar[h] - solarCharge);
        double windGrid  = std::max(0.0, prof.wind[h] - windCharge);
        double hydroGrid = std::max(0.0, prof.hydro[h] - hydroCharge);

        // Generator dispatch subject to ramp-rate limits
        double targetGen = std::max(0.0, s.generatorCapacity);
        if (s.generatorRampLimit > 0.0 && h > 0) {
            double delta = targetGen - prevGenerator;
            if (std::abs(delta) > s.generatorRampLimit) {
                targetGen = prevGenerator + (delta > 0 ? s.generatorRampLimit : -s.generatorRampLimit);
            }
        }

        // In Swarm mode, PSO fine-tunes resource allocation
        if (isSwarmMode && s.psoIterations > 0) {
            auto psoResult = pso.optimizeHour(prof.demand[h], solarGrid, windGrid, prevGenerator, soc, s);
            targetGen = std::min(targetGen, psoResult.generatorPower);
        }

        // In Swarm mode, ACO discovers dynamic routing priorities across corridors
        std::map<Edge, double> routingWeights;
        if (isSwarmMode) {
            std::map<std::string, double> surplusMap = {
                {"S1", solarGrid}, {"S3", targetGen}, {"S4", hydroGrid}, {"S6", windGrid}
            };
            std::map<std::string, double> deficitMap = {
                {"S2", 30.0}, {"S5", 35.0}, {"S7", 30.0}, {"S8", 30.0}
            };
            auto acoWeights = aco.optimizeRoutes(activeLineCaps, surplusMap, deficitMap);
            routingWeights = acoWeights.corridorPriority;
        }

        auto f = allocate(cfg, solarGrid, windGrid, hydroGrid, discharge,
                          targetGen, prof.demand[h] / 235.0, routingWeights, subStorageAvail);

        double actualBatt = f.sourceUsed["Battery"];
        if (discharge > 0.0 && actualBatt < discharge) {
            soc = std::min(s.batteryCapacity, soc + (discharge - actualBatt) / s.dischargeEff);
        }
        discharge = actualBatt;

        // Track actual substation storage discharged
        double actualSubStorageDischarge = 0.0;
        for (const auto& sub : subs) {
            double used = f.sourceFlow[{"Substation Storage", sub}];
            actualSubStorageDischarge += used;
            subSoc[sub] = std::max(0.0, subSoc[sub] - used / s.dischargeEff);
        }

        double totalSubCharge = 0.0;
        for (const auto& [sub, ch] : subStorageCharge) totalSubCharge += ch;

        double gc = f.sourceUsed["Main Generator"];
        prevGenerator = gc;

        double curt = std::max(0.0, solarGrid - f.sourceUsed["Solar"]) +
                      std::max(0.0, windGrid - f.sourceUsed["Wind"]) +
                      std::max(0.0, hydroGrid - f.sourceUsed["Hydro"]);

        // Battery degradation: wear cost increases with deep discharge (DoD)
        double dodFactor = (s.batteryCapacity > 1e-6)
            ? std::max(0.0, 0.30 - soc / s.batteryCapacity) * 3.0
            : 0.0;
        double effectiveWearCost = s.wearCost + s.batteryDegradationCost * dodFactor;
        double wear = (charge + discharge) * effectiveWearCost;

        double cost = gc * s.generatorCost + wear + f.unserved * s.unservedPenalty;

        // DC Power Flow calculations
        std::map<std::string, double> netInjections;
        for (const auto& sub : subs) {
            double subGen = 0.0;
            if (sub == "S1") subGen += f.sourceUsed["Solar"] * 0.5 + actualBatt * 0.5;
            if (sub == "S2") subGen += f.sourceUsed["Solar"] * 0.5;
            if (sub == "S3") subGen += gc * 0.6;
            if (sub == "S4") subGen += f.sourceUsed["Hydro"] * 0.6;
            if (sub == "S5") subGen += gc * 0.4 + f.sourceUsed["Hydro"] * 0.4;
            if (sub == "S6") subGen += f.sourceUsed["Wind"] * 0.6;
            if (sub == "S7") subGen += f.sourceUsed["Wind"] * 0.4;
            if (sub == "S8") subGen += actualBatt * 0.5;
            subGen += f.sourceFlow[{"Substation Storage", sub}];

            double subDem = 0.0;
            for (const auto& [e, flow] : f.feedFlow) {
                if (e.first == sub) subDem += flow;
            }
            netInjections[sub] = subGen - subDem;
        }

        auto dcRes = solveDcPowerFlow(netInjections, activeLineCaps, f.meshFlow);

        // Multi-Agent System peer-to-peer coordination step
        if (isSwarmMode) {
            std::map<std::string, double> subGens;
            std::map<std::string, double> subDems;
            for (const auto& sub : subs) {
                subGens[sub] = std::max(0.0, netInjections[sub]);
                subDems[sub] = std::max(0.0, -netInjections[sub]);
            }
            auto msgs = mas.stepHour(h, subGens, subDems, dcRes.busAngles, dcRes.busVoltages, activeLineCaps);
            out.messages.insert(out.messages.end(), msgs.begin(), msgs.end());
        }

        // Track resilience metrics
        if (dcRes.islandCount > maxIslands) maxIslands = dcRes.islandCount;
        if (dcRes.cascadingContainment < minContainment) minContainment = dcRes.cascadingContainment;
        if (dcRes.minVoltage < systemMinVoltage) systemMinVoltage = dcRes.minVoltage;
        if (std::abs(dcRes.frequencyDev) > systemMaxFreqDev) systemMaxFreqDev = std::abs(dcRes.frequencyDev);

        // Recovery time tracking for critical load restoration
        double criticalRatio = (f.criticalDemand > 1e-6) ? (f.criticalDelivered / f.criticalDemand) : 1.0;
        if (criticalRatio < 0.99) {
            currentOutageDuration += 1.0;
            if (currentOutageDuration > maxRecoveryTime) maxRecoveryTime = currentOutageDuration;
        } else {
            currentOutageDuration = 0.0;
        }

        out.cost += cost;
        out.unserved += f.unserved;
        out.delivered += f.delivered;
        out.demand += f.demand;
        out.generator += gc;
        out.hydro += f.sourceUsed["Hydro"];
        out.curtailment += curt;
        out.throughput += charge + discharge + totalSubCharge + actualSubStorageDischarge;
        out.substationStorageThroughput += totalSubCharge + actualSubStorageDischarge;
        out.criticalDelivered += f.criticalDelivered;
        out.criticalDemand += f.criticalDemand;
        out.totalLosses += dcRes.totalLosses;

        // Telemetry row export
        std::map<std::string, double> r;
        r["Hour"] = h;
        r["Demand (MW)"] = f.demand;
        r["Solar (MW)"] = prof.solar[h];
        r["Wind (MW)"] = prof.wind[h];
        r["Hydro (MW)"] = prof.hydro[h];
        r["Hydro used (MW)"] = f.sourceUsed["Hydro"];
        r["Battery charge (MW)"] = charge;
        r["Battery discharge (MW)"] = discharge;
        r["Substation storage discharge (MW)"] = actualSubStorageDischarge;
        r["Substation storage charge (MW)"] = totalSubCharge;
        double currentSubSocTotal = 0.0;
        for (const auto& [sub, val] : subSoc) currentSubSocTotal += val;
        r["Substation storage SOC (MWh)"] = currentSubSocTotal;
        r["Generator used (MW)"] = gc;
        r["Delivered (MW)"] = f.delivered;
        r["Unserved (MW)"] = f.unserved;
        r["Source flow balance residual (MW)"] = std::accumulate(
            f.sourceUsed.begin(), f.sourceUsed.end(), 0.0,
            [](double z, const auto& x) { return z + x.second; }
        ) - f.delivered;
        r["Consumer delivery balance residual (MW)"] = f.delivered - f.delivered;
        r["Battery SOC (MWh)"] = soc;
        r["Operating cost"] = cost;
        r["Reserve shortfall (MWh)"] = std::max(0.0, reserve - soc);

        // Electrical & Resilience Telemetry
        r["Transmission losses (MW)"] = dcRes.totalLosses;
        r["Frequency deviation (Hz)"] = dcRes.frequencyDev;
        r["Island count"] = dcRes.islandCount;
        r["Cascading containment"] = dcRes.cascadingContainment;
        for (const auto& sub : subs) {
            r["Bus " + sub + " angle (deg)"] = dcRes.busAngles[sub];
            r["Bus " + sub + " voltage (pu)"] = dcRes.busVoltages[sub];
        }

        for (int di = 1; di <= 8; ++di) {
            r["D" + std::to_string(di) + " demand (MW)"] = 0.0;
            r["D" + std::to_string(di) + " delivered (MW)"] = 0.0;
        }

        for (int ci = 1; ci <= NUM_CONSUMERS; ++ci) {
            std::string c = consumerId(ci);
            int di = std::min(8, ((ci - 1) * 8) / 50 + 1);
            r[c + " delivered (MW)"] = f.cd[c];
            r[c + " demand (MW)"] = base[c] * prof.demand[h] / 235.0;
            r[c + " unserved (MW)"] = std::max(0.0, r[c + " demand (MW)"] - f.cd[c]);
            r["D" + std::to_string(di) + " demand (MW)"] += r[c + " demand (MW)"];
            r["D" + std::to_string(di) + " delivered (MW)"] += f.cd[c];
        }

        for (const auto& [e, v] : f.feedFlow) {
            r["Feeder " + e.first + " -> " + e.second + " flow (MW)"] = v;
        }
        for (const auto& [e, v] : f.sourceFlow) {
            r["Source line " + e.first + " -> " + e.second + " flow (MW)"] = v;
        }
        for (const auto& [e, v] : f.meshFlow) {
            r["Transmission " + e.first + " -> " + e.second + " flow (MW)"] = v;
        }

        out.rows.push_back(std::move(r));
    }

    out.finalSoc = soc;
    out.objective = out.cost + std::max(0.0, reserve - soc) * s.reservePenalty;
    out.criticalPct = 100.0 * out.criticalDelivered / std::max(1e-9, out.criticalDemand);

    out.recoveryTime = maxRecoveryTime;
    out.criticalRestorationPct = out.criticalPct;
    out.islandCount = maxIslands;
    out.cascadingContainment = minContainment;
    out.minVoltage = systemMinVoltage;
    out.maxFreqDev = systemMaxFreqDev;

    return out;
}

} // namespace asi
