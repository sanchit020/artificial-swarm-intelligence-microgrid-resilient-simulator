# Resilient Microgrid Power Dispatch & Critical Flow Allocation under N-k Multi-Contingencies

[![C++17](https://img.shields.io/badge/Language-C%2B%2B17-00599C?logo=c%2B%2B)](CMakeLists.txt)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](requirements.txt)
[![Build Tool](https://img.shields.io/badge/CMake-3.16%2B-064F8C?logo=cmake)](CMakeLists.txt)
[![Framework](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?logo=streamlit)](dashboard/app.py)
[![Architecture](https://img.shields.io/badge/Docs-ARCHITECTURE.md-2ea44f)](ARCHITECTURE.md)

An engineering decision-support framework coupling **Artificial Swarm Intelligence (Genetic Algorithm)** with a **two-stage critical-first Edmonds–Karp network flow allocator** to model and analyze microgrid resilience under simultaneous, multi-element ($N-k$) grid failures.

![Dashboard Preview](dashboard/dashboard_preview.png)

---

## What the Project Is

This framework simulates an autonomous, fault-tolerant **50-consumer, 8-substation meshed microgrid** equipped with distributed generation and storage assets:
- **Solar Photovoltaic (PV) & Wind Turbine generation**: Diurnal stochastic generation profiles.
- **Battery Energy Storage System (BESS)**: State-of-charge (SOC) tracking, charge/discharge power limits, efficiency modeling, and protected reserve margins.
- **Main Dispatchable Generator**: Baseline thermal backup power.
- **8 Modeled Substations (`S1`–`S8`)**: Interconnected via a 16-corridor mesh transmission network.
- **50 Individually Modeled Consumers**:
  - **7 Critical Priority Consumers**: Healthcare facilities and emergency services (`C003`, `C010`, `C017`, `C024`, `C031`, `C038`, `C045`).
  - **43 Standard Commercial & Residential Consumers**.
  - **Dual Redundant Feeders**: Every consumer is connected to their two nearest substations via independent 5.5 MW distribution feeders (100 total distribution edges).

The system allows operators and researchers to inject arbitrary **$N-k$ multi-contingencies** (simultaneous cuts to transmission corridors, substations, generation sources, and consumer feeders) and observe how power is autonomously rerouted to protect critical infrastructure.

---

## Modular System Architecture

The project is structured into clean, decoupled components. The computational core is written in compiled **C++17** and packaged as a static library (`asi_core`), linked to the standalone solver executable (`asi_engine`) and test runner (`asi_tests`). The Python layer serves as a dashboard adapter and visualization interface.

```
                    ┌──────────────────────────────────────────────┐
                    │               Streamlit UI                   │
                    │   • Interactive Cartographic Topology Map    │
                    │   • Multi-Element Contingency Injection      │
                    │   • 24-hr Dispatch & Battery SOC Plots       │
                    └──────────────────────┬───────────────────────┘
                                           │
                                  config.txt / JSON
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   Compiled C++17 Solver Engine (asi_engine)                      │
│                                                                                  │
│   network.cpp       • Topology, 50 consumers, baseline demands, config parsing   │
│   flow.cpp          • Edmonds–Karp algorithm & 2-stage priority allocation       │
│   simulation.cpp    • 24-hr diurnal profiles, generator dispatch, battery SOC    │
│   optimizer.cpp     • Genetic algorithm battery scheduler (GA swarm)             │
│   output.cpp        • High-precision hourly CSV export & key-value summaries     │
│   main.cpp          • Program CLI entrypoint, argument parsing, orchestration    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

> **Full Architectural Details**: See [**ARCHITECTURE.md**](ARCHITECTURE.md) for the module dependency graph, lifecycle sequence diagrams, and mathematical formulations.

---

## Core Algorithms

### 1. Artificial Swarm Intelligence (Genetic Algorithm Dispatch)
- Optimizes a 24-hour chromosome of discrete battery actions $a_h \in \{-2, -1, 0, 1, 2\}$ (full/half discharge, idle, half/full charge).
- Balances generation against demand, minimizes expensive generator fuel consumption and battery wear, and prevents costly unserved energy penalties ($18,000/MWh).
- Implements fitness caching, elitism, tournament/rank selection, single-point crossover, and mutation.
- **Guaranteed Baseline Invariant**: Optimized schedules are verified against the unmanaged all-zero schedule to ensure $score(\text{best}) \le score(\text{noAction})$.

### 2. Two-Stage Priority Edmonds–Karp Network Flow
- Formulates power routing as a directed capacity-constrained flow graph: `Sources → Substations → Transmission Mesh → Feeders → Consumers`.
- Enforces an 82 MW throughput limit on each substation using node-splitting (`sub:in → sub:out`).
- **Stage 1 (Critical Maximization)**: Directs flow from critical consumers to `SINK` using Edmonds–Karp shortest-augmenting paths.
- **Stage 2 (System Maximization)**: Opens arcs from standard consumers to `SINK` and continues flow augmentation on the **exact same residual graph**. Reverse residual arcs permit earlier routes to be rearranged dynamically without diminishing secured critical delivery.

---

## Repository Structure

```
ASI_Smart_Power_Grid/
├── CMakeLists.txt              # CMake build configuration (asi_core, asi_engine, asi_tests)
├── ARCHITECTURE.md             # Complete architecture and dependency specification
├── README.md                   # Project overview, quickstart, and documentation
├── build_cpp.bat               # Windows batch script to build C++ engine
├── run_dashboard.bat           # Setup virtual environment and launch Streamlit UI
├── run_tests.bat               # Run C++ unit tests and Python test suite
├── requirements.txt            # Python dependencies (Streamlit, Plotly, Pandas, Pytest)
├── cpp/
│   ├── include/
│   │   └── asi/
│   │       ├── common.hpp      # System constants, Settings, Config, FlowResult, Sim
│   │       ├── network.hpp     # Grid topology, consumer IDs, baseline demands, parser
│   │       ├── flow.hpp        # MaxFlow class & two-stage flow allocation logic
│   │       ├── simulation.hpp  # Diurnal profiles, battery dispatch, simulation loop
│   │       ├── optimizer.hpp   # Genetic algorithm optimizer
│   │       └── output.hpp      # CSV escaping, hourly data export, summary output
│   ├── src/
│   │   ├── network.cpp         # Topology definitions, baseline demand, config reading
│   │   ├── flow.cpp            # Edmonds-Karp residual graph and allocation implementation
│   │   ├── simulation.cpp      # State-of-charge machine, costs, and hourly metrics
│   │   ├── optimizer.cpp       # GA population, crossover, mutation, elitism
│   │   ├── output.cpp          # Telemetry formatting and summary serialization
│   │   └── main.cpp            # CLI entrypoint, argument parsing, mode dispatch
│   └── tests/
│       └── test_main.cpp       # Standalone C++ unit test suite
├── dashboard/
│   ├── app.py                  # Interactive Streamlit dashboard UI
│   ├── microgrid.py            # Python adapter invoking asi_engine executable
│   ├── network_flow.py         # Static topology metadata and feeder endpoint mapping
│   └── topology.py             # Plotly cartographic visualization of microgrid
├── tests/
│   ├── test_core.py            # Pytest suite for flow balance and optimizer repeatability
│   └── test_network_scenarios.py # Pytest suite for N-k outage & capacity contingencies
├── sweep_corridors.py          # Batch evaluation script for N-1 transmission line cuts
├── test_corridor_outage.py     # Standalone S3-S5 physical corridor cut benchmark
└── test_line_outage.py         # Standalone transmission line outage benchmark
```

---

## Quickstart & How to Run

### 1. Launch the Web Dashboard (Windows)
Double-click `run_dashboard.bat` or run:
```cmd
run_dashboard.bat
```
Alternatively, using Python directly:
```bash
.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### 2. Run All Automated Tests
To run both the compiled **C++ unit tests** and the **Python pytest suite**:
```cmd
run_tests.bat
```
Or run individually:
```bash
# C++ unit tests
build\Release\asi_tests.exe

# Python integration tests
.venv\Scripts\python.exe -m pytest -v tests
```

### 3. Build the C++ Solver Engine Standalone
```cmd
build_cpp.bat
```
Or via CMake:
```bash
cmake -S . -B build
cmake --build build --config Release --parallel
```

### 4. Run the C++ Engine from the CLI
```bash
build\Release\asi_engine.exe <config_path> <hourly_csv_path> <summary_txt_path>
```
To view available options:
```bash
build\Release\asi_engine.exe --help
```

### 5. Run Outage and Contingency Analysis Scripts
```bash
# Evaluate N-1 cuts across all 16 transmission lines
.venv\Scripts\python.exe sweep_corridors.py

# Evaluate targeted corridor cut (S3 -> S5)
.venv\Scripts\python.exe test_corridor_outage.py

# Evaluate single transmission line outage
.venv\Scripts\python.exe test_line_outage.py
```

---

## Requirements

- **Python**: 3.11 recommended (requires packages listed in `requirements.txt`)
- **CMake**: 3.16 or higher
- **C++ Compiler**: Compatible with C++17 (Visual Studio 2022 C++ Build Tools, GCC 9+, or Clang 10+)

---

## Unserved Demand and Outage Semantics

For every hour and consumer, the engine records demand, delivered power, and unserved power:
$$\text{Unserved} = \max(0, \text{Demand} - \text{Delivered})$$

The simulation verifies that source delivery, consumer delivery, and demand accounting reconcile within floating-point tolerance ($< 10^{-5}\text{ MW}$). Failed source connections, directional corridors, substations, and consumer feeders have their capacity set to zero. A failed substation disables attached source links, mesh lines, and distribution feeders.

The source-to-substation topology is intentionally sparse so transmission corridors are necessary for transfers; otherwise, direct source links to all substations would make corridor cuts trivial.

---

## Controlled Baseline Comparison

The headline dashboard metrics report values for a battery schedule optimized for the currently active scenario. Comparing raw metrics across separate runs can be misleading because the Genetic Algorithm may select different battery actions for each scenario.

The dashboard's **Failure impact vs. same dispatch without failures** panel isolates physical impact: it replays the identical 24 battery actions, random seed, and renewable profile with and without the selected network failures.

---

## Technical Scope & Modeling Boundaries

This is a research and educational **capacity-constrained network-flow (transport) model**, not a full AC power-flow or protection-grade grid controller:
- It tracks active power ($MW$) and energy balance ($MWh$) under linear/directed capacity constraints.
- It does **not** compute complex bus voltages, reactive power ($MVAR$), phase angles, frequency regulation, or transient electromechanical stability limits.
- The Genetic Algorithm operates as a centralized scheduler for the 24-hour battery chromosome, rather than a decentralized physical multi-agent swarm.
