#include "asi/optimizer.hpp"
#include "asi/simulation.hpp"

#include <algorithm>
#include <map>
#include <random>
#include <vector>

namespace asi {

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
        std::sort(p.begin(), p.end(), [&](const auto& a, const auto& b) {
            return score(a) < score(b);
        });

        std::vector<std::array<int, HOURS_PER_DAY>> q{p[0], p[1]};
        while (static_cast<int>(q.size()) < pop) {
            std::uniform_int_distribution<int> pick(0, pop - 1);
            std::uniform_int_distribution<int> cutd(1, HOURS_PER_DAY - 1);

            const auto& a = p[pick(rng)];
            const auto& b = p[pick(rng)];
            int cut = cutd(rng);

            std::array<int, HOURS_PER_DAY> c = a;
            for (int i = cut; i < HOURS_PER_DAY; ++i) {
                c[i] = b[i];
            }

            std::uniform_real_distribution<double> prob(0.0, 1.0);
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

    if (score(noAction) < score(best)) {
        best = noAction;
    }

    return {best, simulate(cfg, best)};
}

} // namespace asi
