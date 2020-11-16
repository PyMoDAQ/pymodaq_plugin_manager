import os
import requests
import tempfile
from hashlib import sha256
from packaging import version
import pkg_resources
from jsonschema import validate
import json
from distlib.index import PackageIndex
from distlib.locators import SimpleScrapingLocator
from pathlib import Path
#using pip directly https://pip.pypa.io/en/latest/reference/pip_install/#git
from pytablewriter import MarkdownTableWriter, RstSimpleTableWriter
from yawrap import Doc
from pymodaq.daq_utils import daq_utils as utils

pypi_index = PackageIndex()
s = SimpleScrapingLocator(pypi_index.url)
logger = utils.set_logger('plugin_manager', add_handler=False, base_logger=False, add_to_console=True)

def find_dict_in_list_from_key_val(dicts, key, value):
    """ lookup within a list of dicts. Look for the dict within the list which has the correct key, value pair

    Parameters
    ----------
    dicts: (list) list of dictionnaries
    key: (str) specific key to look for in each dict
    value: value to match

    Returns
    -------
    dict: if found otherwose returns None
    """

    for dict in dicts:
        if key in dict:
            if dict[key] == value:
                return dict
    return None


def get_pypi_pymodaq(search_string='pymodaq'):
    versions = []
    for ss in pypi_index.search(search_string):
        if search_string == ss['name']:
            d = s.locate(ss['name'])
            if d is not None:
                versions.append({"name": ss['name'],
                                 "version": ss['version'],
                                 })
    return versions

def get_pypi_plugins():
    plugins = []
    for ss in pypi_index.search('pymodaq'):
        if 'pymodaq-plugin' in ss['name']:
            d = s.locate(ss['name'])
            if d is not None:
                plugins.append({"plugin-name": ss['name'],
                                 "display-name": ss['name'],
                                 "version": ss['version'],
                                 "id": '',
                                 "repository": d.download_url,
                                 "description": ss['summary'],
                                 "author": '',
                                 "homepage": '',
                                 })
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


def get_plugin(name, entry='display-name'):
    plugins = get_plugins_from_json()
    d = find_dict_in_list_from_key_val(plugins, entry, name)
    return d

def get_check_repo(plugin_dict):
    try:
        response = requests.get(plugin_dict["repository"])
    except requests.exceptions.RequestException as e:
        logger.exception(str(e))
        return str(e)

    if response.status_code != 200:
        rep = f'{plugin_dict["display-name"]}: failed to download plugin. Returned code {response.status_code}'
        logger.error(rep)
        return rep

    # Hash it and make sure its what is expected
    hash = sha256(response.content).hexdigest()
    if plugin_dict["id"].lower() != hash.lower():
        rep = f'{plugin_dict["display-name"]}: Invalid hash. Got {hash.lower()} but expected {plugin_dict["id"]}'
        logger.error(rep)
        return rep
    else:
        logger.info(f'SHA256 is Ok')



def get_plugins():
    plugins_available = get_plugins_from_json()
    plugins_installed_init = [{'plugin-name': entry.module_name,
                          'version': entry.dist.version} for entry in pkg_resources.iter_entry_points('pymodaq.plugins')]
    plugins_installed = []
    for plug in plugins_installed_init:
        d = find_dict_in_list_from_key_val(plugins_available, 'plugin-name', plug['plugin-name'])
        d.update(plug)
        plugins_installed.append(d)
        plugins_available.pop(plugins_available.index(d))

    plugins = get_plugins_from_json()
    plugins_update = []
    for plug in plugins_installed:
        d = find_dict_in_list_from_key_val(plugins, 'plugin-name', plug['plugin-name'])
        if version.parse(d['version']) > version.parse(plug['version']):
            plugins_update.append(d)


    return plugins_available, plugins_installed, plugins_update


def validate_json_plugin_list():
    base_path = Path(__file__).parent.joinpath('src')
    with open(str(base_path.joinpath('plugin_list.schema'))) as f:
        schema = json.load(f)
    with open(str(base_path.joinpath('PluginList.json'))) as f:
        plugins = json.load(f)
    validate(instance=plugins, schema=schema)
    return plugins


def post_error(message):
    logger.error(message)


def check_plugin_entries():
    displaynames = []
    repositories = []
    for plugin in get_plugins_from_json():
        logger.info(f'Checking info on plugin: {plugin["display-name"]}')

        try:
            response = requests.get(plugin["repository"])
        except requests.exceptions.RequestException as e:
            post_error(str(e))
            continue

        if response.status_code != 200:
            post_error(f'{plugin["display-name"]}: failed to download plugin. Returned code {response.status_code}')
            continue

        # Hash it and make sure its what is expected
        hash = sha256(response.content).hexdigest()
        if plugin["id"].lower() != hash.lower():
            post_error(f'{plugin["display-name"]}: Invalid hash. Got {hash.lower()} but expected {plugin["id"]}')
        else:
            logger.info(f'SHA256 is Ok')

        # check uniqueness of json display-name and repository
        found = False
        for name in displaynames:
            if plugin["display-name"] == name:
                post_error(f'{plugin["display-name"]}: non unique display-name entry')
                found = True
        if not found:
            displaynames.append(plugin["display-name"])

        found = False
        for repo in repositories:
            if plugin["repository"] == repo:
                post_error(f'{plugin["repository"]}: non unique repository entry')
                found = True
        if not found:
            repositories.append(plugin["repository"])


def write_plugin_doc():
    plugins = get_plugins_from_json()
    base_path = Path(__file__).parent

    header_keys = ['display-name', 'authors', 'version', 'description']
    header = ['Repo Name', 'Authors', 'Versiopluginn', 'Description']
    plugins_tmp = []

    plugins.sort(key=lambda plugin: plugin['display-name'])

    for ind, plug in enumerate(plugins):
        tmp = []
        for k in header_keys:
            if k == 'display-name':
                tmp.append(f'<a href="{plug["homepage"]}" target="_top">{plug["display-name"]}</a> ')
            elif k == 'authors':
                doc, tag, text = Doc().tagtext()
                with tag('ul'):
                    for auth in plug[k]:
                        with tag('li'):
                            text(auth)
                tmp.append(doc.getvalue())
            elif k == 'version':
                tmp.append(f'<a href="{plug["repository"]}" target="_top">{plug["version"]}</a> ')
            elif k == 'description':
                doc, tag, text = Doc().tagtext()
                text(plug[k]+'\r\n')
                if plug['instruments']:
                    for inst in plug['instruments']:
                        text(f'{inst}:')
                        with tag('ul'):
                            for instt in plug['instruments'][inst]:
                                with tag('li'):
                                    text(instt)
                    tmp.append(doc.getvalue())
                else:
                    tmp.append('')
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


    with open(base_path.parent.joinpath('README_base.md'), 'r') as f:
        content = f.read()
        content += '\r\n'

    with open(base_path.parent.joinpath('README.md'), 'w') as f:
        content += writer.dumps()
        f.write(content)

if __name__ == '__main__':
    #check_plugin_entries()
    write_plugin_doc()
    versions = get_pypi_pymodaq()
    import pymodaq_plugin_manager.version
