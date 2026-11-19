"""The H100's hybrid technique (D138, P1). Importing this package registers its arms in live2's
`arms.ARMS` registry under fixed configuration names, so `make_arm(name)` (which passes no kwargs to
factories) builds them without any change to flash-owned files."""
from .hybrid_arm import HybridArm, CONFIGS, register  # noqa: F401

register()
