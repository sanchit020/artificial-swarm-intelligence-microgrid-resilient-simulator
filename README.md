# ASI Smart Power Grid — C++ engine + preserved Streamlit UI

This version keeps the existing Streamlit application and fantasy-atlas map while moving the computational path into a compiled C++17 engine.

## Architecture

- `cpp/src/main.cpp`: C++ implementation of Edmonds–Karp max flow, capacity-constrained network allocation, critical-first service, battery dispatch/state-of-charge accounting, 24-hour simulation, unserved demand accounting, and the genetic algorithm for battery actions.
- `CMakeLists.txt`: portable CMake build.
- `dashboard/microgrid.py`: thin Python adapter. It serializes inputs, invokes `asi_engine`, and loads the resulting hourly CSV and summary. It does not implement dispatch, network flow, or optimization.
- `dashboard/network_flow.py`: topology metadata and visual-map feeder endpoint discovery only. No Python max-flow allocator remains in this module.
- `dashboard/topology.py` and `dashboard/app.py`: existing Streamlit UI and map, retained.

## Requirements

- Python 3.11 recommended
- CMake 3.16+
- C++17 compiler (Visual Studio 2022 Build Tools with Desktop development with C++, or another C++17 toolchain)

## Run on Windows

1. Extract the complete project folder.
2. Run `run_dashboard.bat`. It creates `.venv` if needed, installs Python requirements, builds the C++ engine with CMake, then starts Streamlit.
3. Or run `build_cpp.bat` to build the C++ engine only.
4. Run `run_tests.bat` to exercise the C++-backed Python adapter and outage scenarios.

The first run builds the executable under `build/`. Generated build files and `.venv` should not be included in source control.

## Unserved demand and outage semantics

For every hour and consumer, the engine records demand, delivered power, and unserved power (`max(0, demand - delivered)`). System unserved energy is the sum of hourly unmet demand. The simulation checks that source delivery, consumer delivery, and demand accounting reconcile within floating-point tolerance. Failed source connections, directional corridors, substations, and consumer feeders have their modeled capacity set to zero. A failed substation also disables attached source links, mesh links, and feeder links.

The source-to-substation topology is deliberately sparse so transmission corridors are necessary for some transfers; otherwise direct source connections to every substation can make corridor failures appear irrelevant. The chosen capacities and profiles are synthetic modeling assumptions.

## Important scope

This is a research/educational capacity-constrained network-flow model, not a full AC power-flow or protection-grade grid controller. It does not calculate voltage, reactive power, frequency dynamics, transient stability, or real utility operating limits. Results should be described as simulated resilience under the model's assumptions.

## Verification status

The C++ executable has been compiled in the development environment and smoke-tested through the Python adapter. The package includes tests for accounting, corridor utilization, feeder isolation, outage handling, and optimizer repeatability. Rebuild and run the included test suite on the target Windows machine before relying on its outputs; Windows compilation and the full test suite are not represented as completed until those commands pass there.

### Unserved-energy interpretation and solver regression fix

The headline metrics are for the battery schedule optimized for the currently selected scenario. Comparing those headline values across separate runs can be misleading because the genetic algorithm may choose different battery actions for each scenario. The dashboard's **Failure impact vs. same dispatch without failures** panel is the controlled comparison: it replays the same 24 battery actions, seed, and demand/renewable profile with and without the selected network failures.

The C++ network allocator now continues the noncritical-consumer augmentation on the same Edmonds–Karp residual graph after maximizing critical-consumer service. This allows prior routes to be rearranged through reverse residual edges while retaining the critical consumers' already-established sink flow. Previously, rebuilding the graph for the second pass discarded those reverse residual edges and could make the aggregate unserved-energy result behave unexpectedly.

A regression test compares the same fixed dispatch with a multi-edge outage and checks that the constrained case does not deliver more energy than normal operation. If the dashboard ever reports lower unserved energy for a failed case than its same-dispatch no-failure reference, it displays a consistency warning instead of implying that the outage improved resilience.
