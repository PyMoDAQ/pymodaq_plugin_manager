import json
import os
import time

import pytest

from pymodaq_plugin_manager import index as idx

INSTRUMENTS = {'Actuators': ['Kinesis_KPZ101: Piezo stage (KPZ101)'], 'Viewer2D': ['UC480: camera']}


def make_index():
    return {'schema': 1, 'generated': '2026-11-29T12:00:00+00:00', 'plugins': [
        {'plugin-name': 'pymodaq_plugins_thorlabs', 'display-name': 'Thorlabs', 'version': '5.3.0',
         'pymodaq': '>=5.3.0', 'homepage': 'http://x', 'authors': ['A (a@b.org)'], 'contributors': [],
         'instruments': {'Actuators': [{'name': 'Kinesis_KPZ101', 'description': 'Piezo stage (KPZ101)'}],
                         'Viewer2D': [{'name': 'UC480', 'description': 'camera'}]},
         'releases': [{'version': '5.3.0', 'pymodaq': '>=5.3.0,<5.4'},
                      {'version': '5.0.6', 'pymodaq': '>=5.0.0,<5.1'},
                      {'version': '4.4.0', 'pymodaq': '>=4.4.0,<5'},
                      {'version': '1.0.0', 'pymodaq': '>=2.0'}]}]}


def test_pymodaq_specifier():
    assert idx.pymodaq_specifier(['numpy', 'pymodaq>=5.3.0,<5.4']) == '<5.4,>=5.3.0'
    assert idx.pymodaq_specifier(['numpy']) == ''
    assert idx.pymodaq_specifier(None) == ''


def test_compatible_release():
    releases = make_index()['plugins'][0]['releases']
    assert idx.compatible_release(releases, None)['version'] == '5.3.0'
    assert idx.compatible_release(releases, '5.3.2')['version'] == '5.3.0'
    assert idx.compatible_release(releases, '5.0.3')['version'] == '5.0.6'
    assert idx.compatible_release(releases, '4.4.7.dev0')['version'] == '4.4.0'
    assert idx.compatible_release(releases, '3.0.0') is None  # stops at the very old releases
    assert idx.compatible_release([], '5.3.0') is None


def test_plugins_from_index_same_shape_as_pypi_ones():
    plugins = idx.plugins_from_index(make_index(), '5.0.1')
    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin['version'] == '5.0.6'
    assert plugin['instruments'] == {'Actuators': ['Kinesis_KPZ101: Piezo stage (KPZ101)'],
                                     'Viewer2D': ['UC480: camera']}
    for key in ('plugin-name', 'display-name', 'version', 'id', 'repository', 'description', 'instruments',
                'authors', 'contributors', 'homepage'):
        assert key in plugin
    assert 'Kinesis_KPZ101' in plugin['description'] and 'a@b.org' in plugin['description']
    assert idx.plugins_from_index(make_index(), '3.0.0') == []


def test_split_entry():
    assert idx._split('Name: some: text') == {'name': 'Name', 'description': 'some: text'}
    assert idx._split('Name') == {'name': 'Name', 'description': ''}


def test_fetch_index_download_cache_and_fallback(tmp_path):
    cache = tmp_path / 'cache.json'
    calls = []

    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    def get(url, timeout):
        calls.append(url)
        return Response(make_index())

    # first call downloads and caches
    assert idx.fetch_index('https://example.org/i.json', cache, get=get)['schema'] == 1
    assert len(calls) == 1 and cache.exists()
    # a recent cache is used without request
    assert idx.fetch_index('https://example.org/i.json', cache, get=get) is not None
    assert len(calls) == 1
    # an old cache is refreshed
    old = time.time() - 10 * 24 * 3600
    os.utime(cache, (old, old))
    idx.fetch_index('https://example.org/i.json', cache, get=get)
    assert len(calls) == 2

    # offline: the old cache is better than nothing
    os.utime(cache, (old, old))

    def offline(url, timeout):
        raise OSError('no network')
    assert idx.fetch_index('https://example.org/i.json', cache, get=offline) is not None
    # offline and no cache: None, the caller browses PyPI
    assert idx.fetch_index('https://example.org/i.json', tmp_path / 'none.json', get=offline) is None


def test_invalid_index_is_refused(tmp_path):
    def get(url, timeout):
        class R:
            def raise_for_status(self): pass
            def json(self): return {'schema': 99, 'plugins': []}
        return R()
    assert idx.fetch_index('https://example.org/i.json', tmp_path / 'c.json', get=get) is None
    assert not (tmp_path / 'c.json').exists()


def test_local_file_index(tmp_path):
    path = tmp_path / 'instruments.json'
    idx.save_index(make_index(), path)
    assert idx.fetch_index(str(path), tmp_path / 'cache.json')['plugins'][0]['plugin-name'] == \
        'pymodaq_plugins_thorlabs'
    assert json.loads(path.read_text())['schema'] == 1
