import json

with open('./data/PluginList.json') as f:
    __version__ = json.load(f)['version']
