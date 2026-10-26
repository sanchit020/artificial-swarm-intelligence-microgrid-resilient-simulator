#include "asi/output.hpp"

#include <fstream>
#include <iomanip>
#include <set>
#include <stdexcept>

namespace asi {

std::string escapeCsv(const std::string& s) {
    if (s.find_first_of(",\"\n") != std::string::npos) {
        std::string o = "\"";
        for (char c : s) {
            if (c == '\"') {
                o += "\"\"";
            } else {
                o += c;
            }
        }
        return o + "\"";
    }
    return s;
}

void exportHourlyCsv(const std::string& path, const Sim& result) {
    std::ofstream csv(path);
    if (!csv) {
        throw std::runtime_error("Cannot write hourly CSV: " + path);
    }
    csv << std::setprecision(12);

    std::set<std::string> cols;
    for (const auto& r : result.rows) {
        for (const auto& x : r) {
            cols.insert(x.first);
        }
    }

    csv << "Hour";
    for (const auto& k : cols) {
        if (k != "Hour") {
            csv << "," << escapeCsv(k);
        }
    }
    csv << "\n";

    for (const auto& r : result.rows) {
        csv << r.at("Hour");
        for (const auto& k : cols) {
            if (k != "Hour") {
                auto it = r.find(k);
                csv << "," << (it != r.end() ? it->second : 0.0);
            }
        }
        csv << "\n";
    }
}

void exportSummary(const std::string& path, const std::array<int, HOURS_PER_DAY>& actions, const Sim& result) {
    std::ofstream sum(path);
    if (!sum) {
        throw std::runtime_error("Cannot write summary file: " + path);
    }
    sum << std::setprecision(15) << "actions=";
    for (int i = 0; i < HOURS_PER_DAY; ++i) {
        sum << (i ? "," : "") << actions[i];
    }
    sum << "\ncost=" << result.cost
        << "\nunserved=" << result.unserved
        << "\ndelivered=" << result.delivered
        << "\ndemand=" << result.demand
        << "\ngenerator=" << result.generator
        << "\ncurtailment=" << result.curtailment
        << "\nthroughput=" << result.throughput
        << "\nfinal_soc=" << result.finalSoc
        << "\nobjective=" << result.objective
        << "\ncritical_delivered=" << result.criticalDelivered
        << "\ncritical_demand=" << result.criticalDemand
        << "\ncritical_service_pct=" << result.criticalPct << "\n";
}

} // namespace asi
