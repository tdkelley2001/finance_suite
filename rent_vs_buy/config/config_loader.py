from pathlib import Path
from typing import Any, Dict, List
import yaml


CONFIG_DIR = Path("rent_vs_buy/config")


def load_yaml(filename: str) -> Dict[str, Any]:
    """
    Loads and returns the parsed YAML object, which must be a top-level mapping.
    """
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{filename} must contain a top-level mapping (key: value)")

    return data


def load_yaml_keys(filename: str) -> List[str]:
    """
    Loads and returns top-level keys from a YAML file.
    Used by the UI to discover available scenarios / regions.
    """
    data = load_yaml(filename)
    return sorted(data.keys())