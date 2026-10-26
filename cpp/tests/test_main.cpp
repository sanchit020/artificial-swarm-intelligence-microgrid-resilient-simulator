#include "asi/common.hpp"
#include "asi/network.hpp"
#include "asi/flow.hpp"
#include "asi/simulation.hpp"
#include "asi/optimizer.hpp"
#include "asi/output.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

#define TEST_ASSERT(cond, msg) \
    do { \
        if (!(cond)) { \
            throw std::runtime_error(std::string("Assertion failed: ") + (msg) + " at line " + std::to_string(__LINE__)); \
        } \
    } while (0)

void test_network_topology() {
    std::cout << "[TEST] Network Topology & Consumer Identification..." << std::flush;

    TEST_ASSERT(asi::consumerId(1) == "C001", "consumerId(1) should be C001");
    TEST_ASSERT(asi::consumerId(50) == "C050", "consumerId(50) should be C050");
    TEST_ASSERT(asi::consumerId(9) == "C009", "consumerId(9) should be C009");

    int criticalCount = 0;
    for (int i = 1; i <= asi::NUM_CONSUMERS; ++i) {
        if (asi::isCriticalConsumer(i)) {
            criticalCount++;
        }
    }
    TEST_ASSERT(criticalCount == 7, "There must be exactly 7 critical consumers");
    TEST_ASSERT(asi::isCriticalConsumer(3), "C003 is critical");
    TEST_ASSERT(asi::isCriticalConsumer(10), "C010 is critical");
    TEST_ASSERT(asi::isCriticalConsumer(17), "C017 is critical");
    TEST_ASSERT(asi::isCriticalConsumer(24), "C024 is critical");
    TEST_ASSERT(asi::isCriticalConsumer(31), "C031 is critical");
    TEST_ASSERT(asi::isCriticalConsumer(38), "C038 is critical");
    TEST_ASSERT(asi::isCriticalConsumer(45), "C045 is critical");
    TEST_ASSERT(!asi::isCriticalConsumer(1), "C001 is not critical");
    TEST_ASSERT(!asi::isCriticalConsumer(2), "C002 is not critical");

    const auto& subs = asi::substations();
    TEST_ASSERT(subs.size() == 8, "Must have 8 substations");

    const auto& mesh = asi::meshCorridors();
    TEST_ASSERT(mesh.size() == 16, "Must have 16 mesh corridors");

    auto demands = asi::baselineDemands();
    TEST_ASSERT(demands.size() == asi::NUM_CONSUMERS, "Demands count must match consumer count");
    double sum = 0.0;
    for (const auto& [c, d] : demands) {
        sum += d;
    }
    TEST_ASSERT(std::abs(sum - 235.0) < 1e-7, "Total baseline demand must equal 235 MW");

    std::cout << " PASSED\n";
}

void test_edmonds_karp_maxflow() {
    std::cout << "[TEST] Edmonds-Karp MaxFlow Algorithm..." << std::flush;

    // Simple 4-node flow network:
    // 0 (SRC) -> 1 (cap 10), 0 -> 2 (cap 10)
    // 1 -> 3 (SINK, cap 5), 2 -> 3 (SINK, cap 15)
    // 1 -> 2 (cap 15)
    asi::MaxFlow mf(4);
    mf.add(0, 1, 10.0);
    mf.add(0, 2, 10.0);
    mf.add(1, 3, 5.0);
    mf.add(2, 3, 15.0);
    mf.add(1, 2, 15.0);

    double flow = mf.run(0, 3);
    TEST_ASSERT(std::abs(flow - 20.0) < 1e-9, "Max flow should equal 20.0");

    std::cout << " PASSED\n";
}

void test_simulation_and_flow_conservation() {
    std::cout << "[TEST] Simulation and Demand Conservation..." << std::flush;

    asi::Config cfg;
    cfg.seed = 2026;

    // Populate 100 feeders (2 feeders per consumer)
    for (int i = 1; i <= asi::NUM_CONSUMERS; ++i) {
        std::string c = asi::consumerId(i);
        cfg.feeders[{"S1", c}] = 5.5;
        cfg.feeders[{"S2", c}] = 5.5;
    }

    std::array<int, asi::HOURS_PER_DAY> actions{};
    asi::Sim sim = asi::simulate(cfg, actions);

    TEST_ASSERT(sim.rows.size() == 24, "Simulation must yield exactly 24 hourly rows");
    TEST_ASSERT(std::abs(sim.demand - sim.delivered - sim.unserved) < 1e-5, "Conservation: demand == delivered + unserved");
    TEST_ASSERT(sim.delivered > 0.0, "Delivered energy should be strictly positive");
    TEST_ASSERT(sim.criticalPct >= 0.0 && sim.criticalPct <= 100.0, "Critical percent within [0, 100]");

    for (const auto& r : sim.rows) {
        double d = r.at("Demand (MW)");
        double del = r.at("Delivered (MW)");
        double uns = r.at("Unserved (MW)");
        TEST_ASSERT(std::abs(d - del - uns) < 1e-5, "Hourly conservation error");
    }

    std::cout << " PASSED\n";
}

void test_optimizer_baseline_guarantee() {
    std::cout << "[TEST] Optimizer Baseline Guarantee..." << std::flush;

    asi::Config cfg;
    cfg.seed = 17;
    cfg.s.population = 8;
    cfg.s.generations = 1;

    for (int i = 1; i <= asi::NUM_CONSUMERS; ++i) {
        std::string c = asi::consumerId(i);
        cfg.feeders[{"S1", c}] = 5.5;
        cfg.feeders[{"S2", c}] = 5.5;
    }

    auto [bestActions, optSim] = asi::optimize(cfg);
    TEST_ASSERT(bestActions.size() == asi::HOURS_PER_DAY, "Optimized schedule must have 24 actions");
    for (int a : bestActions) {
        TEST_ASSERT(a >= -2 && a <= 2, "Each action must be in [-2, 2]");
    }

    std::array<int, asi::HOURS_PER_DAY> noAction{};
    asi::Sim baselineSim = asi::simulate(cfg, noAction);

    // Optimizer must never return a schedule worse than no-action schedule
    TEST_ASSERT(optSim.objective <= baselineSim.objective + 1e-7, "Optimized objective must not exceed baseline");

    std::cout << " PASSED\n";
}

void test_csv_escaping() {
    std::cout << "[TEST] Output CSV Escaping..." << std::flush;

    TEST_ASSERT(asi::escapeCsv("SimpleHeader") == "SimpleHeader", "Simple string unescaped");
    TEST_ASSERT(asi::escapeCsv("Header,with,comma") == "\"Header,with,comma\"", "Comma requires quotes");
    TEST_ASSERT(asi::escapeCsv("Header \"with\" quotes") == "\"Header \"\"with\"\" quotes\"", "Quotes doubled");

    std::cout << " PASSED\n";
}

int main() {
    std::cout << "=== Running ASI C++ Unit Tests ===\n";
    try {
        test_network_topology();
        test_edmonds_karp_maxflow();
        test_simulation_and_flow_conservation();
        test_optimizer_baseline_guarantee();
        test_csv_escaping();
        std::cout << "All C++ Unit Tests PASSED successfully!\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "C++ Unit Test FAILED: " << e.what() << "\n";
        return 1;
    }
}
