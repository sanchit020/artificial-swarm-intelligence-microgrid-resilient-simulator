#include "asi/power_flow.hpp"
#include "asi/network.hpp"

#include <algorithm>
#include <cmath>
#include <queue>
#include <stdexcept>
#include <vector>

namespace asi {

const std::map<Edge, LineParam>& transmissionLineParams() {
    static const std::map<Edge, LineParam> params = []() {
        std::map<Edge, LineParam> p;
        // Impedance parameters for 16 corridors: X in [0.06, 0.12], R = 0.10 * X
        const auto& corridors = meshCorridors();
        for (const auto& [u, v] : corridors) {
            double x = 0.08;
            if (u == "S3" || v == "S3" || u == "S8" || v == "S8") {
                x = 0.06; // Heavy spine corridors have lower reactance
            } else if ((u == "S5" && v == "S6") || (u == "S6" && v == "S7")) {
                x = 0.11; // Peripheral rural corridors have higher reactance
            }
            double r = 0.10 * x;
            p[{u, v}] = LineParam{r, x, 48.0};
            p[{v, u}] = LineParam{r, x, 48.0};
        }
        return p;
    }();
    return params;
}

DcPowerFlowResult solveDcPowerFlow(
    const std::map<std::string, double>& netInjections,
    const std::map<Edge, double>& activeLineCaps,
    const std::map<Edge, double>& allocatedFlows
) {
    DcPowerFlowResult result;
    const auto& subs = substations();
    const int numSubs = static_cast<int>(subs.size());
    const auto& params = transmissionLineParams();

    // Map substation names to indices 0..7
    std::map<std::string, int> subIdx;
    for (int i = 0; i < numSubs; ++i) {
        subIdx[subs[i]] = i;
        result.busAngles[subs[i]] = 0.0;
        result.busVoltages[subs[i]] = 1.0;
    }

    // Determine active corridors and connected components (islanding)
    std::vector<std::vector<int>> adj(numSubs);
    for (int i = 0; i < numSubs; ++i) {
        for (int j = i + 1; j < numSubs; ++j) {
            Edge e{subs[i], subs[j]};
            auto itCap = activeLineCaps.find(e);
            if (itCap != activeLineCaps.end() && itCap->second > 1e-4) {
                adj[i].push_back(j);
                adj[j].push_back(i);
            }
        }
    }

    std::vector<int> islandId(numSubs, -1);
    int currentIsland = 0;
    for (int i = 0; i < numSubs; ++i) {
        if (islandId[i] >= 0) continue;
        std::queue<int> q;
        q.push(i);
        islandId[i] = currentIsland;
        while (!q.empty()) {
            int u = q.front();
            q.pop();
            for (int v : adj[u]) {
                if (islandId[v] < 0) {
                    islandId[v] = currentIsland;
                    q.push(v);
                }
            }
        }
        currentIsland++;
    }
    result.islandCount = currentIsland;

    // Solve DC power flow independently for each island
    for (int isl = 0; isl < currentIsland; ++isl) {
        std::vector<int> islandBuses;
        for (int i = 0; i < numSubs; ++i) {
            if (islandId[i] == isl) {
                islandBuses.push_back(i);
            }
        }

        if (islandBuses.empty()) continue;

        // Slack bus for this island: pick first bus with generation or bus 0
        int slackBus = islandBuses[0];
        for (int b : islandBuses) {
            if (subs[b] == "S3" || subs[b] == "S1") {
                slackBus = b;
                break;
            }
        }

        int m = static_cast<int>(islandBuses.size());
        if (m == 1) {
            result.busAngles[subs[slackBus]] = 0.0;
            continue;
        }

        // Build B_bus matrix for the island
        std::vector<int> nonSlack;
        for (int b : islandBuses) {
            if (b != slackBus) nonSlack.push_back(b);
        }
        int k = static_cast<int>(nonSlack.size());

        std::vector<std::vector<double>> B(k, std::vector<double>(k, 0.0));
        std::vector<double> P(k, 0.0);

        for (int r = 0; r < k; ++r) {
            int u = nonSlack[r];
            auto itInj = netInjections.find(subs[u]);
            P[r] = (itInj != netInjections.end() ? itInj->second : 0.0) / 100.0; // p.u. base

            for (int c = 0; c < k; ++c) {
                int v = nonSlack[c];
                if (r == c) {
                    // Diagonal: sum of susceptances connected to u
                    for (int n : adj[u]) {
                        Edge e{subs[u], subs[n]};
                        auto itP = params.find(e);
                        double x = (itP != params.end() ? itP->second.x : 0.08);
                        B[r][c] += 1.0 / x;
                    }
                } else {
                    // Off-diagonal: -b_uv if connected
                    auto itN = std::find(adj[u].begin(), adj[u].end(), v);
                    if (itN != adj[u].end()) {
                        Edge e{subs[u], subs[v]};
                        auto itP = params.find(e);
                        double x = (itP != params.end() ? itP->second.x : 0.08);
                        B[r][c] -= 1.0 / x;
                    }
                }
            }
        }

        // Gaussian elimination with partial pivoting to solve B * theta = P
        std::vector<double> theta(k, 0.0);
        bool singular = false;
        for (int r = 0; r < k; ++r) {
            int pivot = r;
            for (int i = r + 1; i < k; ++i) {
                if (std::abs(B[i][r]) > std::abs(B[pivot][r])) {
                    pivot = i;
                }
            }
            if (std::abs(B[pivot][r]) < 1e-9) {
                singular = true;
                break;
            }
            std::swap(B[r], B[pivot]);
            std::swap(P[r], P[pivot]);

            for (int i = r + 1; i < k; ++i) {
                double factor = B[i][r] / B[r][r];
                for (int j = r; j < k; ++j) {
                    B[i][j] -= factor * B[r][j];
                }
                P[i] -= factor * P[r];
            }
        }

        if (!singular) {
            for (int i = k - 1; i >= 0; --i) {
                double sum = P[i];
                for (int j = i + 1; j < k; ++j) {
                    sum -= B[i][j] * theta[j];
                }
                theta[i] = sum / B[i][i];
            }
            for (int r = 0; r < k; ++r) {
                result.busAngles[subs[nonSlack[r]]] = theta[r] * (180.0 / PI); // Convert rad to deg
            }
        }
        result.busAngles[subs[slackBus]] = 0.0;
    }

    // Compute branch flows, losses, and bus voltage estimates
    double totalLosses = 0.0;
    int operationalLines = 0;
    int overloadedLines = 0;
    double minV = 1.0;

    for (const auto& [e, p] : params) {
        if (e.first >= e.second) continue; // Process each undirected line once

        double flow = 0.0;
        auto itF1 = allocatedFlows.find(e);
        auto itF2 = allocatedFlows.find({e.second, e.first});
        if (itF1 != allocatedFlows.end()) flow += itF1->second;
        if (itF2 != allocatedFlows.end()) flow -= itF2->second;
        double absFlow = std::abs(flow);

        auto itCap = activeLineCaps.find(e);
        bool isLineActive = (itCap != activeLineCaps.end() && itCap->second > 1e-4);

        if (isLineActive) {
            operationalLines++;
            if (absFlow > p.rating * 1.02) {
                overloadedLines++; // Exceeded thermal limit
            }

            // Transmission I^2 * R loss in MW
            double flowPu = absFlow / 100.0;
            double lossMw = flowPu * flowPu * p.r * 100.0;
            result.lineLosses[e] = lossMw;
            result.lineLosses[{e.second, e.first}] = lossMw;
            totalLosses += lossMw;
        } else {
            result.lineLosses[e] = 0.0;
            result.lineLosses[{e.second, e.first}] = 0.0;
        }
    }
    result.totalLosses = totalLosses;

    // Voltage magnitude estimation (drop proxy from power flow and reactance)
    for (int i = 0; i < numSubs; ++i) {
        std::string s = subs[i];
        double drop = 0.0;
        for (int n : adj[i]) {
            Edge e{s, subs[n]};
            auto itP = params.find(e);
            double r = (itP != params.end() ? itP->second.r : 0.01);
            double x = (itP != params.end() ? itP->second.x : 0.08);

            double flow = 0.0;
            auto itF = allocatedFlows.find(e);
            if (itF != allocatedFlows.end()) flow = itF->second;
            double flowPu = flow / 100.0;
            double qPu = flowPu * 0.32; // Assuming ~0.95 power factor reactive component

            drop += (r * flowPu + x * qPu) * 0.45;
        }
        double v = std::clamp(1.0 - drop, 0.88, 1.05);
        result.busVoltages[s] = v;
        if (v < minV) minV = v;
    }
    result.minVoltage = minV;

    // Cascading failure containment factor
    result.cascadingContainment = (operationalLines > 0)
        ? std::max(0.0, 1.0 - static_cast<double>(overloadedLines) / operationalLines)
        : 1.0;

    // System frequency deviation proxy (MW mismatch relative to system inertia)
    double netTotal = 0.0;
    for (const auto& [s, inj] : netInjections) {
        netTotal += inj;
    }
    // Net total should balance delivered - demand; frequency deviation reflects transient imbalance
    result.frequencyDev = std::clamp(-netTotal / 80.0, -1.2, 1.2);

    return result;
}

} // namespace asi

