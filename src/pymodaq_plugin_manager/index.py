"""Static index of the PyMoDAQ plugins and of the instruments they interface

The weekly job of the repository (``write_plugins_doc``) builds ``doc/instruments.json`` together with the README
table. The manager downloads this single file (cached on disk) instead of browsing PyPI and requesting the metadata of
every release of every plugin, which is slow. If the index cannot be reached, the manager falls back to PyPI.

Content of the file::

    {"schema": 1, "generated": "2026-11-29T12:00:00+00:00",
     "plugins": [{"plugin-name": "pymodaq_plugins_thorlabs", "display-name": "Thorlabs", "version": "5.3.0",
                  "pymodaq": ">=5.3.0", "homepage": "https://...", "authors": ["..."], "contributors": ["..."],
                  "instruments": {"Actuators": [{"name": "Kinesis_KPZ101", "description": "..."}], ...},
                  "releases": [{"version": "5.3.0", "pymodaq": ">=5.3.0"}, ...]}, ...]}

``releases`` (newest first) gives the PyMoDAQ versions each release is compatible with, so that the release to
install is chosen without any request. ``instruments`` are those of the latest release.
"""
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Union

import requests
from packaging.version import Version, InvalidVersion

SCHEMA = 1
INDEX_URL = 'https://raw.githubusercontent.com/PyMoDAQ/pymodaq_plugin_manager/main/doc/instruments.json'
#: environment variables: another url (a mirror, a file), and "1" to ignore the index and browse PyPI
ENV_URL = 'PYMODAQ_PLUGIN_INDEX_URL'
ENV_LIVE = 'PYMODAQ_PLUGIN_MANAGER_LIVE'
MAX_AGE = 24 * 3600  # s, the cached index is used without any request during this time
TIMEOUT = 10  # s

logger = logging.getLogger(__name__)


def default_cache_path() -> Path:
    try:
        from pymodaq_utils.config import get_set_local_dir
        folder = get_set_local_dir(user=True)
    except Exception:
        folder = Path.home() / '.pymodaq'
    return Path(folder) / 'plugin_manager_instruments.json'


def pymodaq_specifier(requirements: Optional[List[str]]) -> str:
    """The specifier of the ``pymodaq`` requirement of a release ('' if there is none)"""
    from packaging.requirements import Requirement
    for req in requirements or []:
        try:
            requirement = Requirement(req)
        except Exception:
            continue
        if requirement.name.lower() == 'pymodaq':
            return str(requirement.specifier)
    return ''


def _release_info(name: str, version: str) -> Optional[dict]:
    from pymodaq_utils.packages import get_package_metadata
    try:
        data = get_package_metadata(name, version)
    except Exception:
        logger.exception(f'Could not get the metadata of {name} {version}')
        return None
    if data is None:
        return None
    return {'version': version, 'pymodaq': pymodaq_specifier(data['info'].get('requires_dist'))}


def get_releases(name: str, max_workers: int = 8) -> List[dict]:
    """The releases of a package, newest first, with their pymodaq specifier"""
    from pymodaq_utils.packages import get_package_metadata
    latest = get_package_metadata(name)
    if latest is None:
        return []
    versions = []
    for v in latest['releases']:
        try:
            versions.append((Version(v), v))
        except InvalidVersion:
            continue
    versions = [v for _, v in sorted(versions, reverse=True)]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        releases = list(pool.map(lambda v: _release_info(name, v), versions))
    return [rel for rel in releases if rel is not None]


def build_index(plugins: List[dict], max_workers: int = 8, print_method: Callable = logger.info) -> dict:
    """Build the index from the plugins given by ``validate.get_pypi_plugins`` (latest versions)

    Parameters
    ----------
    plugins: list of dict
        plugins with their parsed ``instruments``, ``authors``...
    max_workers: int
        number of requests made in parallel to PyPI
    """
    def one(plugin: dict) -> dict:
        print_method(f"Getting the releases of {plugin['plugin-name']}")
        releases = get_releases(plugin['plugin-name'], max_workers=max_workers)
        latest = next((r for r in releases if r['version'] == plugin['version']), None)
        return {'plugin-name': plugin['plugin-name'],
                'display-name': plugin['display-name'],
                'version': plugin['version'],
                'pymodaq': latest['pymodaq'] if latest else '',
                'homepage': plugin.get('homepage') or '',
                'authors': plugin.get('authors') or [],
                'contributors': plugin.get('contributors') or [],
                'instruments': {kind: [_split(entry) for entry in entries]
                                for kind, entries in (plugin.get('instruments') or {}).items()},
                'releases': releases}

    entries = [one(plugin) for plugin in sorted(plugins, key=lambda p: p['plugin-name'].lower())]
    return {'schema': SCHEMA, 'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'plugins': entries}


def _split(entry: str) -> dict:
    name, sep, description = entry.partition(': ')
    return {'name': name.strip(), 'description': description.strip()} if sep else {'name': entry.strip(),
                                                                                  'description': ''}


def save_index(index: dict, path: Union[str, Path]):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


def is_valid(index) -> bool:
    return isinstance(index, dict) and index.get('schema') == SCHEMA and isinstance(index.get('plugins'), list)


def load_index(path: Union[str, Path]) -> Optional[dict]:
    try:
        index = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return index if is_valid(index) else None


def fetch_index(url: Optional[str] = None, cache_path: Union[str, Path, None] = None, max_age: float = MAX_AGE,
                get: Callable = requests.get) -> Optional[dict]:
    """The index: from the cache if recent, else downloaded (and cached), else from an older cache

    Returns None if no valid index could be found (the caller should browse PyPI).
    """
    url = url or os.environ.get(ENV_URL) or INDEX_URL
    cache_path = Path(cache_path) if cache_path is not None else default_cache_path()
    cached = load_index(cache_path)
    if cached is not None and time.time() - cache_path.stat().st_mtime < max_age:
        return cached
    try:
        if url.startswith(('http://', 'https://')):
            response = get(url, timeout=TIMEOUT)
            response.raise_for_status()
            index = response.json()
        else:  # a local file
            index = json.loads(Path(url).read_text(encoding='utf-8'))
        if not is_valid(index):
            raise ValueError('not a valid plugin index')
    except Exception as e:
        logger.info(f'Could not get the plugin index ({e})')
        return cached  # may be None
    try:
        save_index(index, cache_path)
    except OSError:
        logger.info('Could not cache the plugin index')
    return index


def compatible_release(releases: List[dict], pymodaq_version: Union[str, Version, None]) -> Optional[dict]:
    """The newest release compatible with a version of PyMoDAQ (the newest one if None)

    Same rule as ``pymodaq_utils.packages.get_pypi_pymodaq``: the releases are read from the newest, a release with
    no pymodaq requirement is skipped, and the search stops at the very old ones (``>=2.0``).
    """
    from packaging.specifiers import SpecifierSet
    if not releases:
        return None
    if pymodaq_version is None:
        return releases[0]
    version = Version(str(pymodaq_version)).base_version
    for release in releases:
        specifier = release.get('pymodaq', '')
        if specifier == '>=2.0':
            return None
        if not specifier:
            continue
        try:
            if version in SpecifierSet(specifier):
                return release
        except Exception:
            continue
    return None


def _description(entry: dict) -> str:
    """A reStructuredText summary shown in the information panel (and searched with 'Description')"""
    title = f"{entry['plugin-name']}"
    lines = [title, '#' * len(title), '']
    if entry.get('homepage'):
        lines += [f"`{entry['homepage']} <{entry['homepage']}>`_", '']
    for section, key in (('Authors', 'authors'), ('Contributors', 'contributors')):
        if entry.get(key):
            lines += [section, '=' * len(section), ''] + [f'* {person}' for person in entry[key]] + ['']
    if entry.get('instruments'):
        lines += ['Instruments', '===========', '']
        for kind, instruments in entry['instruments'].items():
            lines += [kind, '+' * len(kind), '']
            for inst in instruments:
                text = f"* **{inst['name']}**"
                lines.append(f"{text}: {inst['description']}" if inst.get('description') else text)
            lines.append('')
    return '\n'.join(lines)


def plugins_from_index(index: dict, pymodaq_version: Union[str, Version, None] = None) -> List[dict]:
    """The plugins compatible with a version of PyMoDAQ, as dictionaries like the ones of ``get_pypi_plugins``"""
    plugins = []
    for entry in index['plugins']:
        release = compatible_release(entry.get('releases') or [], pymodaq_version)
        if release is None:
            continue
        instruments = {kind: [f"{i['name']}: {i['description']}" if i.get('description') else i['name']
                              for i in insts] for kind, insts in entry.get('instruments', {}).items()}
        plugins.append({'plugin-name': entry['plugin-name'], 'display-name': entry['display-name'],
                        'version': release['version'], 'id': '', 'repository': '',
                        'description': _description(entry), 'instruments': instruments,
                        'authors': entry.get('authors') or [], 'contributors': entry.get('contributors') or [],
                        'homepage': entry.get('homepage') or ''})
    return plugins
