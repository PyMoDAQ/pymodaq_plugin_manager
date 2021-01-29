import json
from pathlib import Path
base_path = Path(__file__).parent

with open(str(base_path.joinpath('data/PluginList.json'))) as f:
    __version__ = json.load(f)['version']
