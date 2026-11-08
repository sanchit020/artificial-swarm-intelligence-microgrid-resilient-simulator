#include "asi/flow.hpp"
#include "asi/network.hpp"

#include <algorithm>
#include <numeric>
#include <queue>
#include <stdexcept>

namespace asi {

MaxFlow::MaxFlow(size_t n) : g(n) {}

void MaxFlow::add(int u, int v, double c, double priority) {
    int ui = static_cast<int>(g[u].size());
    int vi = static_cast<int>(g[v].size());
    g[u].push_back({v, vi, c, c, priority});
    g[v].push_back({u, ui, 0.0, 0.0, 0.0});
    refs.push_back({u, ui});
}

double MaxFlow::run(int s, int t) {
    double total = 0.0;
    for (;;) {
        std::vector<std::pair<int, int>> p(g.size(), {-1, -1});
        std::queue<int> q;
        q.push(s);
        p[s] = {s, -1};

        while (!q.empty() && p[t].first < 0) {
            int u = q.front();
            q.pop();

            // Check if any outgoing arcs have prioritized ordering
            bool hasPriority = false;
            for (const auto& a : g[u]) {
                if (a.priority > 0.0) {
                    hasPriority = true;
                    break;
                }
            }

            if (hasPriority) {
                std::vector<int> order(g[u].size());
                std::iota(order.begin(), order.end(), 0);
                std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
                    return g[u][a].priority > g[u][b].priority;
                });
                for (int i : order) {
                    if (g[u][i].cap > 1e-9 && p[g[u][i].to].first < 0) {
                        p[g[u][i].to] = {u, i};
                        q.push(g[u][i].to);
                        if (g[u][i].to == t) break;
                    }
                }
            } else {
                for (int i = 0; i < static_cast<int>(g[u].size()); ++i) {
                    if (g[u][i].cap > 1e-9 && p[g[u][i].to].first < 0) {
                        p[g[u][i].to] = {u, i};
                        q.push(g[u][i].to);
                        if (g[u][i].to == t) break;
                    }
                }
            }
        }

        if (p[t].first < 0) {
            break;
        }

        double f = 1e100;
        for (int v = t; v != s; ) {
            auto [u, i] = p[v];
            f = std::min(f, g[u][i].cap);
            v = u;
        }

        for (int v = t; v != s; ) {
            auto [u, i] = p[v];
            auto& a = g[u][i];
            a.cap -= f;
            g[v][a.rev].cap += f;
            v = u;
        }
        total += f;
    }
    return total;
}

FlowResult allocate(const Config& cfg, double solar, double wind, double hydro,
                    double batt, double gen, double scale,
                    const std::map<Edge, double>& routingWeights,
                    const std::map<std::string, double>& subStorageAvail) {
    const auto base = baselineDemands();
    std::map<std::string, double> d;
    for (const auto& [consumer, value] : base) {
        d[consumer] = value * scale;
    }

    const auto& subs = substations();
    std::map<std::string, double> subcap;
    for (const auto& sub : subs) {
        subcap[sub] = 82.0;
    }
    for (const auto& [sub, value] : cfg.subOverrides) {
        if (!subcap.count(sub) || value < 0.0) {
            throw std::runtime_error("Invalid substation override: " + sub);
        }
        subcap[sub] = value;
    }

    std::map<Edge, double> sourceCaps = defaultSourceCapacities();
    std::map<Edge, double> meshCaps;
    for (const auto& [a, b] : meshCorridors()) {
        meshCaps[{a, b}] = 48.0;
        meshCaps[{b, a}] = 48.0;
    }
    std::map<Edge, double> feederCaps = cfg.feeders;

    // Apply substation storage capacity overrides if provided
    double totalSubStorage = 0.0;
    for (const auto& sub : subs) {
        auto it = subStorageAvail.find(sub);
        double avail = (it != subStorageAvail.end()) ? std::max(0.0, it->second) : 0.0;
        sourceCaps[{"Substation Storage", sub}] = avail;
        totalSubStorage += avail;
    }

    auto knownLine = [&](const Edge& edge) {
        return sourceCaps.count(edge) || meshCaps.count(edge);
    };

    for (const auto& [edge, cap] : cfg.lineOverrides) {
        if (cap < 0.0 || !knownLine(edge)) {
            throw std::runtime_error("Unknown/negative source or transmission edge override: " + edge.first + " -> " + edge.second);
        }
        if (sourceCaps.count(edge)) {
            sourceCaps[edge] = cap;
        } else {
            meshCaps[edge] = cap;
        }
    }

    for (const auto& [edge, cap] : cfg.feederOverrides) {
        if (cap < 0.0 || !feederCaps.count(edge)) {
            throw std::runtime_error("Unknown/negative feeder override: " + edge.first + " -> " + edge.second);
        }
        feederCaps[edge] = cap;
    }

    for (const auto& sub : subs) {
        if (subcap[sub] == 0.0) {
            for (auto& [edge, cap] : sourceCaps) {
                if (edge.second == sub) cap = 0.0;
            }
            for (auto& [edge, cap] : meshCaps) {
                if (edge.first == sub || edge.second == sub) cap = 0.0;
            }
            for (auto& [edge, cap] : feederCaps) {
                if (edge.first == sub) cap = 0.0;
            }
        }
    }

    std::map<std::string, double> supply = {
        {"Solar", std::max(0.0, solar)},
        {"Wind", std::max(0.0, wind)},
        {"Hydro", std::max(0.0, hydro)},
        {"Battery", std::max(0.0, batt)},
        {"Substation Storage", totalSubStorage},
        {"Main Generator", std::max(0.0, gen)}
    };

    FlowResult out;
    out.demand = std::accumulate(d.begin(), d.end(), 0.0,
        [](double total, const auto& item) { return total + item.second; });

    for (const auto& [consumer, value] : d) {
        out.cd[consumer] = 0.0;
        out.cu[consumer] = value;
    }
    for (const auto& source : energySources()) {
        out.sourceUsed[source] = 0.0;
    }
    for (const auto& [edge, cap] : sourceCaps) {
        out.sourceFlow[edge] = 0.0;
    }
    for (const auto& [edge, cap] : meshCaps) {
        out.meshFlow[edge] = 0.0;
    }
    for (const auto& [edge, cap] : feederCaps) {
        out.feedFlow[edge] = 0.0;
    }

    std::vector<std::string> nodes = {"SRC", "SINK"};
    auto addNode = [&](const std::string& node) {
        if (std::find(nodes.begin(), nodes.end(), node) == nodes.end()) {
            nodes.push_back(node);
        }
    };

    for (const auto& [source, value] : supply) {
        addNode("SUP:" + source);
    }
    for (const auto& [edge, cap] : sourceCaps) {
        addNode("SRC:" + edge.first);
        addNode(edge.second + ":in");
    }
    for (const auto& sub : subs) {
        addNode(sub + ":in");
        addNode(sub + ":out");
    }
    for (const auto& [edge, cap] : meshCaps) {
        addNode(edge.first + ":out");
        addNode(edge.second + ":in");
    }
    for (const auto& [edge, cap] : feederCaps) {
        addNode(edge.first + ":out");
        addNode(edge.second);
    }
    for (int i = 1; i <= NUM_CONSUMERS; ++i) {
        addNode(consumerId(i));
    }

    auto id = [&](const std::string& node) {
        auto it = std::find(nodes.begin(), nodes.end(), node);
        if (it == nodes.end()) {
            throw std::runtime_error("Internal network node missing: " + node);
        }
        return static_cast<int>(it - nodes.begin());
    };

    struct ArcKey {
        std::string type;
        std::string a;
        std::string b;
    };

    std::vector<ArcKey> keys;
    MaxFlow mf(nodes.size());

    auto addArc = [&](const std::string& u, const std::string& v, double cap, ArcKey key, double priority = 0.0) {
        mf.add(id(u), id(v), std::max(0.0, cap), priority);
        keys.push_back(std::move(key));
    };

    for (const auto& [source, cap] : supply) {
        addArc("SRC", "SUP:" + source, cap, {"supply", source, ""});
    }
    for (const auto& [edge, cap] : sourceCaps) {
        addArc("SUP:" + edge.first, edge.second + ":in", cap, {"source", edge.first, edge.second});
    }
    for (const auto& sub : subs) {
        addArc(sub + ":in", sub + ":out", subcap[sub], {"sub", sub, ""});
    }
    for (const auto& [edge, cap] : meshCaps) {
        double prio = 0.0;
        auto itP = routingWeights.find(edge);
        if (itP != routingWeights.end()) prio = itP->second;
        addArc(edge.first + ":out", edge.second + ":in", cap, {"mesh", edge.first, edge.second}, prio);
    }
    for (const auto& [edge, cap] : feederCaps) {
        addArc(edge.first + ":out", edge.second, cap, {"feed", edge.first, edge.second});
    }

    // First maximize critical service
    for (int i = 1; i <= NUM_CONSUMERS; ++i) {
        const std::string consumer = consumerId(i);
        if (isCriticalConsumer(i)) {
            addArc(consumer, "SINK", d[consumer], {"consumer", consumer, ""});
        }
    }
    mf.run(id("SRC"), id("SINK"));

    // Then maximize total service while retaining critical priority on the same residual graph
    for (int i = 1; i <= NUM_CONSUMERS; ++i) {
        const std::string consumer = consumerId(i);
        if (!isCriticalConsumer(i)) {
            addArc(consumer, "SINK", d[consumer], {"consumer", consumer, ""});
        }
    }
    mf.run(id("SRC"), id("SINK"));

    for (size_t ix = 0; ix < keys.size(); ++ix) {
        const auto [u, j] = mf.refs[ix];
        const auto& arc = mf.g[u][j];
        const double used = std::max(0.0, arc.original - arc.cap);
        const auto& key = keys[ix];
        if (key.type == "supply") {
            out.sourceUsed[key.a] += used;
        } else if (key.type == "source") {
            out.sourceFlow[{key.a, key.b}] += used;
        } else if (key.type == "mesh") {
            out.meshFlow[{key.a, key.b}] += used;
        } else if (key.type == "feed") {
            out.feedFlow[{key.a, key.b}] += used;
        } else if (key.type == "consumer") {
            out.cd[key.a] += used;
            out.cu[key.a] = std::max(0.0, d[key.a] - out.cd[key.a]);
        }
    }

    out.delivered = std::accumulate(out.cd.begin(), out.cd.end(), 0.0,
        [](double total, const auto& item) { return total + item.second; });
    out.unserved = std::max(0.0, out.demand - out.delivered);
    out.hydroUsed = out.sourceUsed["Hydro"];
    out.substationStorageDischarged = out.sourceUsed["Substation Storage"];

    for (int i = 1; i <= NUM_CONSUMERS; ++i) {
        if (isCriticalConsumer(i)) {
            out.criticalDemand += d[consumerId(i)];
            out.criticalDelivered += out.cd[consumerId(i)];
        }
    }

    return out;
}

} // namespace asi
