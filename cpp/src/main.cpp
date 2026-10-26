#include "asi/common.hpp"
#include "asi/network.hpp"
#include "asi/optimizer.hpp"
#include "asi/output.hpp"
#include "asi/simulation.hpp"

#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc == 2 && (std::string(argv[1]) == "-h" || std::string(argv[1]) == "--help")) {
        std::cout << "Usage: asi_engine config.txt hourly.csv summary.txt\n\n"
                  << "Arguments:\n"
                  << "  config.txt    Path to microgrid scenario configuration file\n"
                  << "  hourly.csv    Output path for 24-hour hourly results CSV\n"
                  << "  summary.txt   Output path for scenario summary key-value file\n";
        return 0;
    }

    if (argc != 4) {
        std::cerr << "usage: asi_engine config.txt hourly.csv summary.txt\n";
        return 2;
    }

    try {
        const std::string configPath  = argv[1];
        const std::string hourlyPath  = argv[2];
        const std::string summaryPath = argv[3];

        asi::Config config = asi::readConfig(configPath);

        std::array<int, asi::HOURS_PER_DAY> chosenActions = config.actions;
        asi::Sim result;

        if (config.mode == "optimize") {
            auto [optActions, optResult] = asi::optimize(config);
            chosenActions = optActions;
            result = std::move(optResult);
        } else {
            result = asi::simulate(config, chosenActions);
        }

        asi::exportHourlyCsv(hourlyPath, result);
        asi::exportSummary(summaryPath, chosenActions, result);

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ASI C++ engine error: " << e.what() << "\n";
        return 1;
    }
}
