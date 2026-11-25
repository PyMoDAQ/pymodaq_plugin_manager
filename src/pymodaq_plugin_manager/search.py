"""Search among the plugins (no Qt dependency, so it can be tested and used by scripts)"""
import re
from typing import Iterable, List


def _compact(text: str) -> str:
    """Lower case without spaces, underscores and hyphens, so that 'ixon 897', 'iXon-897' and 'ixon_897' match"""
    return re.sub(r'[\s_\-]+', '', text.lower())


def instrument_texts(plugin: dict) -> List[str]:
    """The entries ('Name: description') of all the instruments of a plugin"""
    instruments = plugin.get('instruments') or {}
    if not isinstance(instruments, dict):
        return []
    return [entry for entries in instruments.values() for entry in entries]


def instrument_names(plugin: dict) -> List[str]:
    """The names of the instruments of a plugin (no duplicates, order kept)"""
    names = [entry.split(':', 1)[0].strip() for entry in instrument_texts(plugin)]
    return list(dict.fromkeys(name for name in names if name))


def plugin_matches(plugin: dict, text: str, in_name: bool = True, in_description: bool = False,
                   in_instruments: bool = True) -> bool:
    """Whether a plugin matches a search text

    Every word of the text must be found in at least one of the selected fields (name, description or instruments),
    whatever the case, and ignoring spaces, underscores and hyphens: ``'thorlabs kpz'`` finds the Thorlabs plugin
    through its ``Kinesis_KPZ101`` instrument.
    """
    words = text.lower().split()
    if not words:
        return True
    fields: List[str] = []
    if in_name:
        fields += [plugin.get('plugin-name', ''), plugin.get('display-name', '')]
    if in_instruments:
        fields += instrument_texts(plugin)
    if in_description:
        fields.append(plugin.get('description') or '')
    lowered = [f.lower() for f in fields]
    compacted = [_compact(f) for f in fields]
    return all(any(word in low for low in lowered) or any(_compact(word) in comp for comp in compacted)
               for word in words)


def filter_plugins(plugins: Iterable[dict], text: str, **kwargs) -> List[dict]:
    """The plugins matching a search text, see :func:`plugin_matches`"""
    return [plugin for plugin in plugins if plugin_matches(plugin, text, **kwargs)]
