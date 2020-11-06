from distlib.index import PackageIndex
from distlib.locators import SimpleScrapingLocator
from hashlib import sha256
import json
from .validate import validate_json_plugin_list

#using pip directly https://pip.pypa.io/en/latest/reference/pip_install/#git


pypi_index = PackageIndex()
s = SimpleScrapingLocator(pypi_index.url)

def get_pypi_plugins():
    plugins = []
    for ss in pypi_index.search('pymodaq'):
        if 'pymodaq-plugin' in ss['name']:
            d = s.locate(ss['name'])
            if d is not None:
                plugins.append([{"plugin-name": ss['name'],
                                 "display-name": ss['name'],
                                 "version": ss['version'],
                                 "id": '',
                                 "repository": d.download_url,
                                 "description": ss['summary'],
                                 "author": '',
                                 "homepage": '',
                                 }])
    return plugins


def get_plugin_sourcefile_id(filename):
    h = sha256()
    b = bytearray(128*1024)
    mv = memoryview(b)
    with open(filename, 'rb', buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()

def get_plugins():
    return validate_json_plugin_list()

