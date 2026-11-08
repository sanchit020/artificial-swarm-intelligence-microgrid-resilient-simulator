#include "asi/optimizer.hpp"
#include "asi/simulation.hpp"

#include <algorithm>
#include <map>
#include <random>
#include <vector>

namespace asi {

// Genetic Algorithm Day-Ahead Battery Dispatch Optimizer
// (Swarm intelligence is handled by the Multi-Agent System, PSO, and ACO)
std::pair<std::array<int, HOURS_PER_DAY>, Sim> optimize(Config cfg) {
    std::mt19937 rng(cfg.seed);
    int pop = std::max(8, cfg.s.population);
    int gens = std::max(1, cfg.s.generations);

    std::vector<std::array<int, HOURS_PER_DAY>> p(pop);
    std::uniform_int_distribution<int> gene(-2, 2);

    for (auto& a : p) {
        for (auto& x : a) {
            x = gene(rng);
        }
    }
    p.back().fill(0);

    std::map<std::array<int, HOURS_PER_DAY>, Sim> cache;
    auto score = [&](const std::array<int, HOURS_PER_DAY>& a) -> double {
        auto it = cache.find(a);
        if (it == cache.end()) {
            it = cache.emplace(a, simulate(cfg, a)).first;
        }
        return it->second.objective;
    };

    for (int g = 0; g < gens; ++g) {
        // Rank sort population by fitness score
        std::sort(p.begin(), p.end(), [&](const auto& a, const auto& b) {
            return score(a) < score(b);
        });

        // Elitism: retain top 2 candidate schedules
        std::vector<std::array<int, HOURS_PER_DAY>> q{p[0], p[1]};

        // 3-way Tournament Selection
        auto tournamentSelect = [&](int k) -> const std::array<int, HOURS_PER_DAY>& {
            std::uniform_int_distribution<int> dist(0, pop - 1);
            int bestIdx = dist(rng);
            double bestScore = score(p[bestIdx]);
            for (int i = 1; i < k; ++i) {
                int cand = dist(rng);
                double candScore = score(p[cand]);
                if (candScore < bestScore) {
                    bestIdx = cand;
                    bestScore = candScore;
                }
            }
            return p[bestIdx];
        };

        std::uniform_int_distribution<int> cutd(1, HOURS_PER_DAY - 1);
        std::uniform_real_distribution<double> prob(0.0, 1.0);

        while (static_cast<int>(q.size()) < pop) {
            const auto& a = tournamentSelect(3);
            const auto& b = tournamentSelect(3);
            int cut = cutd(rng);

            // Single-point crossover
            std::array<int, HOURS_PER_DAY> c = a;
            for (int i = cut; i < HOURS_PER_DAY; ++i) {
                c[i] = b[i];
            }

            // Uniform gene mutation
            for (auto& x : c) {
                if (prob(rng) < 0.1) {
                    x = gene(rng);
                }
            }
            q.push_back(c);
        }
        p = std::move(q);
    }

    std::array<int, HOURS_PER_DAY> noAction{};
    auto best = *std::min_element(p.begin(), p.end(), [&](const auto& a, const auto& b) {
        return score(a) < score(b);
    });

    // Invariant guarantee: never perform worse than the unmanaged all-zero schedule
    if (score(noAction) < score(best)) {
        best = noAction;
    }

    return {best, simulate(cfg, best)};
}

} // namespace asi
