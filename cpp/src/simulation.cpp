#include "asi/simulation.hpp"
#include "asi/flow.hpp"
#include "asi/network.hpp"

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

    for (int h = 0; h < HOURS_PER_DAY; ++h) {
        double base = 150.0 + 25.0 * std::sin((h - 7.0) * 2.0 * PI / 24.0) +
                      18.0 * std::exp(-std::pow((h - 19.0) / 3.2, 2.0));
        double ss = std::max(0.0, std::sin((h - 6.0) * PI / 12.0));
        double ww = std::clamp(
            0.52 + 0.18 * std::sin((h + 2.0) * 2.0 * PI / 24.0) +
            0.08 * std::cos(h * 4.0 * PI / 24.0),
            0.18, 0.9
        ) / 0.9;

        profiles.demand[h] = std::max(120.0, base * s.demandScale * (1.0 + nd(rng) * 0.025));
        profiles.solar[h]  = std::max(0.0, 145.0 * ss * s.solarScale * (1.0 + nd(rng) * 0.04));
        profiles.wind[h]   = std::max(0.0, 55.0 * ww * s.windScale * (1.0 + nd(rng) * 0.05));
    }
    return profiles;
}

Sim simulate(const Config& cfg, const std::array<int, HOURS_PER_DAY>& actions) {
    const auto& s = cfg.s;
    if (s.batteryCapacity <= 0.0 || s.batteryPower < 0.0 ||
        s.chargeEff <= 0.0 || s.chargeEff > 1.0 ||
        s.dischargeEff <= 0.0 || s.dischargeEff > 1.0) {
        throw std::runtime_error("Invalid battery settings");
    }

    HourlyProfiles prof = generateHourlyProfiles(cfg.seed, s);
    double reserve = std::clamp(s.reserveSoc, 0.0, s.batteryCapacity);
    double soc = std::clamp(s.initialSoc, 0.0, s.batteryCapacity);

    Sim out;
    auto base = baselineDemands();

    for (int h = 0; h < HOURS_PER_DAY; ++h) {
        int a = actions[h];
        if (a < -2 || a > 2) {
            throw std::runtime_error("Battery actions must be -2..2");
        }

        double charge = 0.0;
        double discharge = 0.0;
        double ren = prof.solar[h] + prof.wind[h];

        if (a > 0) {
            double wanted = s.batteryPower * a / 2.0;
            double room = std::max(0.0, s.batteryCapacity - soc) / s.chargeEff;
            charge = std::min({wanted, room, std::max(0.0, ren - prof.demand[h])});
            soc = std::min(s.batteryCapacity, soc + charge * s.chargeEff);
        } else if (a < 0) {
            double wanted = s.batteryPower * std::abs(a) / 2.0;
            double avail = std::max(0.0, soc - reserve) * s.dischargeEff;
            discharge = std::min(wanted, avail);
            soc = std::max(0.0, soc - discharge / s.dischargeEff);
        }

        double solarCharge = std::min(charge, prof.solar[h]);
        double windCharge  = std::max(0.0, charge - solarCharge);
        double solarGrid   = std::max(0.0, prof.solar[h] - solarCharge);
        double windGrid    = std::max(0.0, prof.wind[h] - windCharge);

        auto f = allocate(cfg, solarGrid, windGrid, discharge,
                          std::max(0.0, s.generatorCapacity), prof.demand[h] / 235.0);

        double actualBatt = f.sourceUsed["Battery"];
        if (discharge > 0.0 && actualBatt < discharge) {
            soc = std::min(s.batteryCapacity, soc + (discharge - actualBatt) / s.dischargeEff);
        }
        discharge = actualBatt;

        double gc = f.sourceUsed["Main Generator"];
        double curt = std::max(0.0, solarGrid - f.sourceUsed["Solar"]) +
                      std::max(0.0, windGrid - f.sourceUsed["Wind"]);
        double wear = (charge + discharge) * s.wearCost;
        double cost = gc * s.generatorCost + wear + f.unserved * s.unservedPenalty;

        out.cost += cost;
        out.unserved += f.unserved;
        out.delivered += f.delivered;
        out.demand += f.demand;
        out.generator += gc;
        out.curtailment += curt;
        out.throughput += charge + discharge;
        out.criticalDelivered += f.criticalDelivered;
        out.criticalDemand += f.criticalDemand;

        std::map<std::string, double> r;
        r["Hour"] = h;
        r["Demand (MW)"] = f.demand;
        r["Solar (MW)"] = prof.solar[h];
        r["Wind (MW)"] = prof.wind[h];
        r["Battery charge (MW)"] = charge;
        r["Battery discharge (MW)"] = discharge;
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
    return out;
}

} // namespace asi
