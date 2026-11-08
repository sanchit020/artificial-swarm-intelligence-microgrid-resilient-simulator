#include "asi/network.hpp"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace asi {

std::string consumerId(int i) {
    std::ostringstream o;
    o << 'C' << std::setw(3) << std::setfill('0') << i;
    return o.str();
}

bool isCriticalConsumer(int i) {
    return i == 3 || i == 10 || i == 17 || i == 24 || i == 31 || i == 38 || i == 45;
}

const std::vector<std::string>& substations() {
    static const std::vector<std::string> subs = {
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"
    };
    return subs;
}

const std::vector<Edge>& meshCorridors() {
    static const std::vector<Edge> mesh = {
        {"S1", "S2"}, {"S2", "S3"}, {"S3", "S4"}, {"S4", "S5"},
        {"S5", "S6"}, {"S6", "S7"}, {"S7", "S1"}, {"S1", "S8"},
        {"S2", "S8"}, {"S3", "S8"}, {"S4", "S8"}, {"S5", "S8"},
        {"S6", "S8"}, {"S7", "S8"}, {"S2", "S6"}, {"S3", "S5"}
    };
    return mesh;
}

const std::vector<std::string>& energySources() {
    static const std::vector<std::string> sources = {
        "Solar", "Wind", "Hydro", "Battery", "Substation Storage", "Main Generator"
    };
    return sources;
}

std::map<Edge, double> defaultSourceCapacities() {
    std::map<Edge, double> sourceCaps;
    const double solarCap[8] = {48.0, 42.0, 24.0, 18.0, 22.0, 18.0, 24.0, 30.0};
    const double windCap[8]  = {22.0, 35.0, 43.0, 28.0, 30.0, 36.0, 24.0, 32.0};
    const auto& subs = substations();

    for (int i = 0; i < 8; ++i) {
        const bool solarHere = (i == 0 || i == 1 || i == 6 || i == 7);
        const bool windHere = (i == 1 || i == 2 || i == 4 || i == 5);
        const bool batteryHere = (i == 0 || i == 3 || i == 7);
        const bool generatorHere = (i == 2 || i == 3 || i == 6);
        const bool hydroHere = (i == 3 || i == 4); // S4 (35 MW) and S5 (25 MW)

        sourceCaps[{"Solar", subs[i]}] = solarHere ? solarCap[i] : 0.0;
        sourceCaps[{"Wind", subs[i]}] = windHere ? windCap[i] : 0.0;
        sourceCaps[{"Hydro", subs[i]}] = hydroHere ? (i == 3 ? 35.0 : 25.0) : 0.0;
        sourceCaps[{"Battery", subs[i]}] = batteryHere ? 40.0 : 0.0;
        sourceCaps[{"Substation Storage", subs[i]}] = 10.0; // Local direct storage feeder
        sourceCaps[{"Main Generator", subs[i]}] = generatorHere ? 55.0 : 0.0;
    }
    return sourceCaps;
}

std::map<std::string, double> baselineDemands() {
    std::map<std::string, double> w;
    double sum = 0.0;
    for (int i = 1; i <= NUM_CONSUMERS; ++i) {
        double x = (0.82 + 0.22 * (0.5 + 0.5 * std::sin(i * 1.73))) * (isCriticalConsumer(i) ? 1.3 : 1.0);
        w[consumerId(i)] = x;
        sum += x;
    }
    for (auto& x : w) {
        x.second = 235.0 * x.second / sum;
    }
    return w;
}

std::vector<std::string> splitString(const std::string& s, char delimiter) {
    std::vector<std::string> v;
    std::stringstream ss(s);
    std::string x;
    while (std::getline(ss, x, delimiter)) {
        v.push_back(x);
    }
    return v;
}

void validateConfig(const Config& cfg) {
    if (cfg.feeders.size() != 2 * NUM_CONSUMERS) {
        throw std::runtime_error("Config must provide two feeders for every consumer (100 edges)");
    }
    const auto& s = cfg.s;
    if (s.batteryCapacity <= 0.0 || s.batteryPower < 0.0 ||
        s.chargeEff <= 0.0 || s.chargeEff > 1.0 ||
        s.dischargeEff <= 0.0 || s.dischargeEff > 1.0) {
        throw std::runtime_error("Invalid battery settings");
    }
}

Config readConfig(const std::string& path) {
    Config c;
    std::ifstream f(path);
    if (!f) {
        throw std::runtime_error("Cannot read config: " + path);
    }

    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }
        auto p = line.find('=');
        if (p == std::string::npos) {
            continue;
        }

        std::string k = line.substr(0, p);
        std::string v = line.substr(p + 1);

        auto num = [&]() { return std::stod(v); };
        auto integer = [&]() { return std::stoi(v); };

        if (k == "mode") {
            c.mode = v;
        } else if (k == "dispatch_mode") {
            c.dispatchMode = c.s.dispatchMode = v;
        } else if (k == "generator_ramp_limit") {
            c.s.generatorRampLimit = num();
        } else if (k == "battery_degradation_cost") {
            c.s.batteryDegradationCost = num();
        } else if (k == "pso_particles") {
            c.s.psoParticles = integer();
        } else if (k == "pso_iterations") {
            c.s.psoIterations = integer();
        } else if (k == "aco_ants") {
            c.s.acoAnts = integer();
        } else if (k == "aco_evaporation") {
            c.s.acoEvaporation = num();
        } else if (k == "seed") {
            c.seed = c.s.seed = integer();
        } else if (k == "demand_scale") {
            c.s.demandScale = num();
        } else if (k == "solar_scale") {
            c.s.solarScale = num();
        } else if (k == "wind_scale") {
            c.s.windScale = num();
        } else if (k == "hydro_scale") {
            c.s.hydroScale = num();
        } else if (k == "hydro_capacity") {
            c.s.hydroCapacity = num();
        } else if (k == "sub_storage_capacity" || k == "substation_storage_capacity") {
            c.s.substationStorageCapacity = num();
        } else if (k == "sub_storage_power" || k == "substation_storage_power") {
            c.s.substationStoragePower = num();
        } else if (k == "generator_capacity") {
            c.s.generatorCapacity = num();
        } else if (k == "battery_capacity") {
            c.s.batteryCapacity = num();
        } else if (k == "battery_power") {
            c.s.batteryPower = num();
        } else if (k == "initial_soc") {
            c.s.initialSoc = num();
        } else if (k == "reserve_soc") {
            c.s.reserveSoc = num();
        } else if (k == "charge_efficiency") {
            c.s.chargeEff = num();
        } else if (k == "discharge_efficiency") {
            c.s.dischargeEff = num();
        } else if (k == "generator_cost") {
            c.s.generatorCost = num();
        } else if (k == "battery_wear_cost") {
            c.s.wearCost = num();
        } else if (k == "unserved_penalty") {
            c.s.unservedPenalty = num();
        } else if (k == "reserve_penalty") {
            c.s.reservePenalty = num();
        } else if (k == "population") {
            c.s.population = integer();
        } else if (k == "generations") {
            c.s.generations = integer();
        } else if (k == "actions") {
            auto a = splitString(v, ',');
            if (a.size() != HOURS_PER_DAY) {
                throw std::runtime_error("actions must contain 24 genes");
            }
            for (int i = 0; i < HOURS_PER_DAY; ++i) {
                c.actions[i] = std::stoi(a[i]);
            }
        } else if (k == "line_override" || k == "feeder_override") {
            auto a = splitString(v, ',');
            if (a.size() != 3) {
                throw std::runtime_error("bad edge override");
            }
            (k == "line_override" ? c.lineOverrides : c.feederOverrides)[{a[0], a[1]}] = std::stod(a[2]);
        } else if (k == "sub_override") {
            auto a = splitString(v, ',');
            if (a.size() != 2) {
                throw std::runtime_error("bad substation override");
            }
            c.subOverrides[a[0]] = std::stod(a[1]);
        } else if (k == "feeder") {
            auto a = splitString(v, ',');
            if (a.size() != 3) {
                throw std::runtime_error("bad feeder");
            }
            c.feeders[{a[0], a[1]}] = 5.5;
        }
    }

    validateConfig(c);
    return c;
}

} // namespace asi
