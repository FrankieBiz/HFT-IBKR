"""Offline research utilities. Diagnostics never authorize trading."""
from .methods import triple_barrier, cpcv, reconstruct_paths, walk_forward, sharpe, psr, dsr, pbo
from .registry import Registry
from .pipeline import evaluate
