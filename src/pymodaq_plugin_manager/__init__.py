import json
from pathlib import Path
base_path = Path(__file__).parent

with open(str(Path(__file__).parent.joinpath('VERSION')), 'r') as fvers:
    __version__ = fvers.read().strip()

