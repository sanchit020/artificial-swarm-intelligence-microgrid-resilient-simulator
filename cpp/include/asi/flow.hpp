#pragma once

#include "asi/common.hpp"

#include <map>
#include <vector>

namespace asi {

// Residual network directed arc
struct Arc {
    int to;
    int rev;
    double cap;
    double original;
    double priority = 0.0;
};

// Edmonds–Karp algorithm for maximum flow with residual capacity tracking
class MaxFlow {
public:
    std::vector<std::vector<Arc>> g;
    std::vector<std::pair<int, int>> refs;

    explicit MaxFlow(size_t n);
    void add(int u, int v, double c, double priority = 0.0);
    double run(int s, int t);
};

// Capacity-constrained electricity flow allocation with two-stage priority:
// 1. Critical consumer load maximization
// 2. Standard consumer load maximization (continuing on same residual graph)
FlowResult allocate(const Config& cfg, double solar, double wind, double hydro,
                    double batt, double gen, double scale,
                    const std::map<Edge, double>& routingWeights = {},
                    const std::map<std::string, double>& subStorageAvail = {});

} // namespace asi
