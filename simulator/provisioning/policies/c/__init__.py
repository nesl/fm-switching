from .joint_c import JointC
from .fidelity_first import FidelityFirst
from .fidelity_first_lifecycle import FidelityFirstLifecycle
from .placement_first import PlacementFirst
from .cache_value_c import CacheValueC
from .oracle_c import OracleC
from .reactive_c import ReactiveC
from .replication_c import ReplicationC
from .libra_c import LibraC
from .handover_c import HandoverC

ALL_POLICIES_C = [
    JointC(), FidelityFirst(), FidelityFirstLifecycle(), PlacementFirst(), CacheValueC(),
    OracleC(), ReactiveC(), ReplicationC(), LibraC(), HandoverC(),
]
