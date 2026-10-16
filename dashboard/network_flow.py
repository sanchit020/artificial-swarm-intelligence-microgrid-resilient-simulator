"""Static grid topology metadata for the Streamlit UI.

Network allocation and Edmonds–Karp are implemented in cpp/src/main.cpp. This module
contains only capacities/topology labels and the existing map-derived feeder endpoints.
"""
SUBSTATION_POSITIONS = {
    'S1': (31, 72), 'S2': (48, 78), 'S3': (67, 69), 'S4': (76, 49),
    'S5': (65, 29), 'S6': (45, 22), 'S7': (27, 34), 'S8': (49, 49),
}
SUBSTATIONS = {s: {'capacity': 82.0} for s in SUBSTATION_POSITIONS}
SUBSTATION_CAPACITY = {s: float(v['capacity']) for s, v in SUBSTATIONS.items()}
CRITICAL_CONSUMERS = {3, 10, 17, 24, 31, 38, 45}
TRANSMISSION_LINES = [
    ('S1','S2'),('S2','S3'),('S3','S4'),('S4','S5'),('S5','S6'),('S6','S7'),('S7','S1'),
    ('S1','S8'),('S2','S8'),('S3','S8'),('S4','S8'),('S5','S8'),('S6','S8'),('S7','S8'),
    ('S2','S6'),('S3','S5'),
]
TRANSMISSION_CAPACITY = 48.0
# The C++ engine uses a sparse source-to-substation topology so mesh corridors are
# necessary for long-distance transfers instead of being bypassed by direct source links.
SOURCE_LINE_CAPACITY = {
    'Solar': {'S1':48,'S2':42,'S3':0,'S4':0,'S5':0,'S6':0,'S7':24,'S8':30},
    'Wind': {'S1':0,'S2':35,'S3':43,'S4':0,'S5':30,'S6':36,'S7':0,'S8':0},
    'Battery': {s: (40 if s in {'S1','S4','S8'} else 0) for s in SUBSTATIONS},
    'Main Generator': {s: (55 if s in {'S3','S4','S7'} else 0) for s in SUBSTATIONS},
}

def consumer_feeder_edges():
    """Return each consumer's two nearest substations from the existing visual topology."""
    from .topology import NODES, SUB_POS
    result = {}
    for consumer in (f'C{i:03d}' for i in range(1, 51)):
        x, y, _ = NODES[consumer]
        nearest = sorted(SUB_POS, key=lambda s: (SUB_POS[s][0]-x)**2 + (SUB_POS[s][1]-y)**2)[:2]
        for sub in nearest:
            result[(sub, consumer)] = 5.5
    return result
