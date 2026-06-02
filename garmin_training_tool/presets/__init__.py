"""Preset training plans from popular coaches."""

import os
import glob

PRESETS_DIR = os.path.dirname(os.path.abspath(__file__))


def list_presets():
    """Return a list of available preset plan names."""
    plans = []
    for path in sorted(glob.glob(os.path.join(PRESETS_DIR, "*.yaml"))):
        name = os.path.splitext(os.path.basename(path))[0]
        plans.append(name)
    return plans


def get_preset_path(name):
    """Get the file path for a preset plan by name."""
    path = os.path.join(PRESETS_DIR, f"{name}.yaml")
    if not os.path.exists(path):
        available = list_presets()
        raise ValueError(
            f"Unknown preset '{name}'. Available presets:\n"
            + "\n".join(f"  - {p}" for p in available)
        )
    return path
