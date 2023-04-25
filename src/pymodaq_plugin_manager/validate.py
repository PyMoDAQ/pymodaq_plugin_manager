import logging
from typing import List, Union

from hashlib import sha256
from packaging import version
from packaging.version import Version
from packaging.requirements import Requirement, SpecifierSet, Specifier
import pkg_resources
from jsonschema import validate
import json
from distlib.index import PackageIndex
from pathlib import Path
#using pip directly https://pip.pypa.io/en/latest/reference/pip_install/#git
from pytablewriter import MarkdownTableWriter
from yawrap import Doc
import requests
from lxml import html
from copy import deepcopy
import re

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

pypi_index = PackageIndex()


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


def get_pypi_package_list(match_name=None):
    status = 'Connecting to the pypi repository, may take some time to retrieve the list'
    if logging:
        logger.info(status)
    else:
        print(status)
    simple_package = requests.get('https://pypi.org/simple/')
    if simple_package.status_code == 503:
        info = 'The service from pypi is currently unavailable, please retry later or install your plugins manually'
        if logging:
            logger.info(info)
        else:
            print(info)
    tree = html.fromstring(simple_package.text)
    packages = []
    for child in tree.body:
        if match_name is None or match_name in child.text:
            packages.append(child.text)
    return packages


def get_pymodaq_specifier(requirements: List[str]) -> SpecifierSet:
    """Get specifiers for pymodaq version from a list of requirements"""
    specifier = SpecifierSet('>3.0,<4.0')
    if requirements is not None:
        for package in requirements:
            req = Requirement(package)
            if req.name == 'pymodaq':
                specifier = req.specifier
                break
    return specifier


def get_package_metadata(name: str, version: Union[str, Version] = None):
    if version is None:
        url = f'https://pypi.python.org/pypi/{name}/json'
    else:
        url = f'https://pypi.python.org/pypi/{name}/{str(version)}/json'
    rep = requests.get(url)
    if rep.status_code != 404:
        return rep.json()


def get_metadata_from_json(json_as_dict: dict) -> dict:
    try:
        if json_as_dict is not None:
            metadata = dict([])
            metadata['author'] = json_as_dict['info']['author']
            metadata['description'] = json_as_dict['info']['description']
            metadata['project_url'] = json_as_dict['info']['project_url']
            metadata['version'] = json_as_dict['info']['version']
            metadata['requirements'] = json_as_dict['info']['requires_dist']
            return metadata
    except:
        pass


def get_pypi_pymodaq(package_name='pymodaq-plugins', pymodaq_version: Version = None):
    """ Get the latest plugin info compatible with a given version of pymodaq

    Parameters
    ----------
    package_name: str
    pymodaq_version: Version

    Returns
    -------
    dict containing metadata of the latest compatible plugin
    """
    if package_name == 'pymodaq-plugins':  # has been renamed pymodaq-plugins-mock
        return
    if isinstance(pymodaq_version, str):
        pymodaq_version = Version(pymodaq_version)
    latest = get_package_metadata(package_name)
    if latest is not None:
        if pymodaq_version is not None:
            versions = list(latest['releases'].keys())[::-1]
            for _version in versions:
                versioned = get_package_metadata(package_name, _version)
                if versioned is not None:
                    specifier = get_pymodaq_specifier(versioned['info']['requires_dist'])
                    if str(specifier) == '>=2.0':  # very old stuff
                        return
                    if pymodaq_version in specifier:
                        return get_metadata_from_json(versioned)
        else:
            return get_metadata_from_json(latest)


def get_pypi_plugins(browse_pypi=False, pymodaq_version: Version = None):
    plugins = []
    if browse_pypi:
        packages = get_pypi_package_list('pymodaq-plugins')
    else:
        packages = [plug['plugin-name'] for plug in get_plugins_from_json()]
    for package in packages:
        metadata = get_pypi_pymodaq(package, pymodaq_version)
        if metadata is not None:
            title = metadata['description'].split('\n')[0]
            if '(' in title and ')' in title:
                display_name = re.search(r'\((.*?)\)', title).group(1)
            else:
                display_name = title
            plugin = {'plugin-name': package.replace('-', '_'), 'display-name': display_name,
                      'version': metadata['version'],
                      'id': '', 'repository': '', 'description': metadata['description'],
                      'instruments': '', 'authors': [metadata['author']], 'contributors': [],
                      'homepage': metadata['project_url']}
            plugins.append(plugin)
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
        if logging:
            logger.exception(str(e))
            return str(e)

    if response.status_code != 200:
        rep = f'{plugin_dict["display-name"]}: failed to download plugin. Returned code {response.status_code}'
        if logging:
            logger.error(rep)
        return rep

    # Hash it and make sure its what is expected
    hash = sha256(response.content).hexdigest()
    if plugin_dict["id"].lower() != hash.lower():
        rep = f'{plugin_dict["display-name"]}: Invalid hash. Got {hash.lower()} but expected {plugin_dict["id"]}'
        if logging:
            logger.error(rep)
        return rep
    else:
        if logging:
            logger.info(f'SHA256 is Ok')


def get_plugins(from_json=False, browse_pypi=True, pymodaq_version: Version = None):
    """get PyMoDAQ plugins

    Parameters
    ----------
    from_json: (bool) if True get the plugins list and source files from the json data file (deprecated) else from the pypi
    server
    browse_pypi: (bool) if from_json is False:
        if True get the list of plugins name from the https://pypi.org/simple/ website, then get the sources from the pypi
            server
        if False, get the list of plugins name from the json data, then fetch the source from the pypi server

    Returns
    -------
    plugins_available: list of available plugins for installation
    plugins_installed: list of already installed plugins
    plugins_update: list of plugins with existing update
    """
    logger.info('Fetching plugin list')
    if from_json:
        plugins_available = get_plugins_from_json()
    else:
        plugins_available = get_pypi_plugins(browse_pypi=browse_pypi, pymodaq_version=pymodaq_version)

    plugins = deepcopy(plugins_available)
    plugins_installed_init = [{'plugin-name': entry.module_name,
                          'version': entry.dist.version} for entry in pkg_resources.iter_entry_points('pymodaq.plugins')]
    plugins_installed = []
    for plug in plugins_installed_init:
        d = find_dict_in_list_from_key_val(plugins_available, 'plugin-name', plug['plugin-name'])
        if d is not None:
            d.update(plug)
            plugins_installed.append(d)
            plugins_available.pop(plugins_available.index(d))

    plugins_update = []
    for plug in plugins_installed:
        d = find_dict_in_list_from_key_val(plugins, 'plugin-name', plug['plugin-name'])
        if version.parse(d['version']) > version.parse(plug['version']):
            plugins_update.append(d)

    return plugins_available, plugins_installed, plugins_update


def validate_json_plugin_list():
    base_path = Path(__file__).parent.joinpath('data')
    with open(str(base_path.joinpath('plugin_list.schema'))) as f:
        schema = json.load(f)
    with open(str(base_path.joinpath('PluginList.json'))) as f:
        plugins = json.load(f)
    validate(instance=plugins, schema=schema)
    return plugins


def post_error(message):
    if logging:
        logger.error(message)


def check_plugin_entries():
    displaynames = []
    repositories = []
    for plugin in get_plugins_from_json():
        if logging:
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
            if logging:
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


def extract_authors_from_description(description):
    """returns the authors as a list from the plugin package description (it should follow the template structure)

    Parameters
    ----------
    description: (str)

    Returns
    -------
    list of string
    """

    posa = description.find('Authors')
    posc = description.find('\n\nContributors')
    posi = description.find('\n\nInstruments')
    authors_raw = description[posa:posc if posc != -1 else posi]
    return authors_raw.split('\n* ')[1:]


def write_plugin_doc():
    plugins = get_pypi_plugins(browse_pypi=True)
    base_path = Path(__file__).parent

    header_keys = ['display-name', 'authors', 'version', 'description']
    header = ['Repo Name', 'Authors', 'Version plugin', 'Instruments']
    plugins_tmp = []

    plugins.sort(key=lambda plugin: plugin['display-name'])

    for ind, plug in enumerate(plugins):
        tmp = []
        for k in header_keys:
            if k == 'display-name':
                tmp.append(f'<a href="{plug["homepage"]}" target="_top">{plug["display-name"]}</a> ')
            elif k == 'authors':
                authors = extract_authors_from_description(plug['description'])
                if len(authors) == 0:
                    authors == plug[k]
                doc, tag, text = Doc().tagtext()
                with tag('ul'):
                    for auth in authors:
                        with tag('li'):
                            text(auth)
                tmp.append(doc.getvalue())
            elif k == 'version':
                tmp.append(f'<a href="{plug["repository"]}" target="_top">{plug["version"]}</a> ')
            elif k == 'description':
                doc, tag, text = Doc().tagtext()
                #text(plug[k]+'\r\n')
                if plug['instruments'] != '':

                    for inst in plug['instruments']:
                        text(f'{inst}:')
                        with tag('ul'):
                            for instt in plug['instruments'][inst]:
                                with tag('li'):
                                    text(instt)
                    tmp.append(doc.getvalue())
                else:
                    lines = plug['description'].split('\n')
                    header_inst = ['Actuators', 'Viewer0D', 'Viewer1D', 'Viewer2D', 'ViewerND']
                    for header_ind, head in enumerate(header_inst):
                        for ind_line, line in enumerate(lines):
                            if head in line:
                                text(line)
                                with tag('ul'):
                                    for subline in lines[ind_line+1:]:
                                        if subline[0:4] == '* **':
                                            with tag('li'):
                                                text(subline[2:])
                                        elif any([hd in subline for hd in header_inst[header_ind+1:]]):
                                            break


                    tmp.append(doc.getvalue())
                    # else:
                    #     tmp.append('')
            else:
                tmp.append(plug[k])
        plugins_tmp.append(tmp)

    writer = MarkdownTableWriter(
        table_name="PyMoDAQ Plugins",
        headers=header,
        value_matrix=plugins_tmp,
        margin=1
    )
    writer.dump(base_path.parent.parent.joinpath('doc/PluginList.md'))


    with open(base_path.parent.parent.joinpath('README_base.md'), 'r') as f:
        content = f.read()
        content += '\r\n'

    with open(base_path.parent.parent.joinpath('README.md'), 'w') as f:
        content += writer.dumps()
        f.write(content)

if __name__ == '__main__':
    #check_plugin_entries()
    write_plugin_doc()
    # versions = get_pypi_pymodaq()
    # from pymodaq_plugin_manager import __version__ as version
    # print(version)
    #print(get_pypi_package_list('pymodaq-plugins'))