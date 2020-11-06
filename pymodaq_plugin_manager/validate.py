from hashlib import sha256
import pkg_resources
from jsonschema import validate
import json
from distlib.index import PackageIndex
from distlib.locators import SimpleScrapingLocator
from pathlib import Path
#using pip directly https://pip.pypa.io/en/latest/reference/pip_install/#git
from pytablewriter import MarkdownTableWriter


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

def get_plugins_from_json():
    return validate_json_plugin_list()['pymodaq-plugins']

def get_plugins_installed():
    plugins = get_plugins_from_json()
    plugins_installed = [entry.load().__name__ for entry in pkg_resources.iter_entry_points('pymodaq.plugins')]


def validate_json_plugin_list():
    base_path = Path(__file__).parent.joinpath('src')
    with open(str(base_path.joinpath('plugin_list.schema'))) as f:
        schema = json.load(f)
    with open(str(base_path.joinpath('PluginList.json'))) as f:
        plugins = json.load(f)
    validate(instance=plugins, schema=schema)
    return plugins

def write_plugin_doc():
    plugins = get_plugins_from_json()
    base_path = Path(__file__).parent

    header_keys = ['display-name', 'author', 'homepage', 'version', 'description']
    header = ['Plugin Name', 'Author', 'Homepage', 'Version', 'Description']
    plugins_tmp = []

    for ind, plug in enumerate(plugins):
        tmp = []
        for k in header_keys:
            if k == 'version':
                tmp.append(f'<a href="{plug["repository"]}" target="_top">{plug["version"]}</a> ')
            else:
                tmp.append(plug[k])
        plugins_tmp.append(tmp)

    writer = MarkdownTableWriter(
        table_name="PyMoDAQ Plugins",
        headers=header,
        value_matrix=plugins_tmp,
        margin=1
    )
    writer.dump(base_path.joinpath('doc/PluginList.md'))


if __name__ == '__main__':
    write_plugin_doc()
