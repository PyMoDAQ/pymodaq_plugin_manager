import logging
from typing import List, Union
import platform
from hashlib import sha256
from packaging import version
from packaging.version import Version, parse

from distlib.index import PackageIndex
from pathlib import Path
#using pip directly https://pip.pypa.io/en/latest/reference/pip_install/#git
from pytablewriter import MarkdownTableWriter
from yawrap import Doc
from copy import deepcopy
import os
from concurrent.futures import ThreadPoolExecutor

from pymodaq_utils.packages import get_pypi_package_list, get_pypi_pymodaq, get_entrypoints, \
    extract_authors_from_description
from pymodaq_utils.plugin_tools.readme import parse_readme
from pymodaq_plugin_manager import index as plugin_index

if parse(platform.python_version()) >= parse('3.8'):  # from version 3.8 this feature is included in the
    # standard lib
    from importlib import metadata
else:
    import importlib_metadata as metadata

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel('INFO')

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


EXCLUDE_PLUGINS = ['pymodaq_plugins',
                   'pymodaq_plugins_orsay',
                   'pymodaq_plugins_template',
                   'pymodaq_plugins_KDC101',  # should not exists on its own but should be incorporated into thorlabs
                   'pymodaq_plugins_AvaSpec',
                   'pymodaq_plugins_MozzaSpectro',
                   ]


def get_pypi_plugins(browse_pypi=True, pymodaq_version: Union[Version, str] = None,
                     print_method=logger.info, max_workers: int = 8) -> List[dict]:
    """Fetch the list of plugins (for a given version) of pymodaq from PyPI

    The metadata of the packages are requested in parallel.

    Parameters
    ----------
    browse_pypi: bool
        If True get the list from pypi server, if False from the builtin json (deprecated, should be True)
    pymodaq_version: Union[str, Version]
        a given pymodaq version (or the latest if None)
    print_method: Callable
        a callable accepting str argument
    max_workers: int
        number of packages requested at the same time

    Returns
    -------
    list of dictionaries giving info on plugins
    """
    packages = get_pypi_package_list(['pymodaq', 'plugins'], print_method=print_method)
    pymodaq_latest = Version(get_pypi_pymodaq('pymodaq')['version'])
    packages = sorted({package.replace('-', '_') for package in packages if package.replace('-', '_')
                       not in EXCLUDE_PLUGINS})

    def fetch(package):
        print_method(f'Fetching metadata for package {package}')
        try:
            metadata = get_pypi_pymodaq(package, pymodaq_version, pymodaq_latest)
        except Exception:
            logger.exception(f'Could not get the metadata of {package}')
            return None
        if metadata is None:
            return None
        display_name = ' '.join(package.split('_')[2:]).capitalize()
        readme = parse_readme(metadata['description'])
        return {'plugin-name': package, 'display-name': display_name,
                'version': metadata['version'],
                'id': '', 'repository': '', 'description': metadata['description'],
                'instruments': readme.instruments_as_dict(),
                'authors': readme.authors or [metadata['author']],
                'contributors': readme.contributors,
                'homepage': metadata['project_url']}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return [plugin for plugin in pool.map(fetch, packages) if plugin is not None]


def get_available_plugins(pymodaq_version: Union[Version, str] = None, print_method=logger.info,
                          use_index: bool = True) -> List[dict]:
    """The plugins compatible with a version of PyMoDAQ

    They are read from the static index (``doc/instruments.json`` of the repository, cached on disk), a single and fast
    request. PyPI is browsed if the index is not available, or if ``use_index`` is False or the environment variable
    ``PYMODAQ_PLUGIN_MANAGER_LIVE`` is ``1`` (to see a plugin released since the last build of the index).
    """
    if use_index and os.environ.get(plugin_index.ENV_LIVE, '') != '1':
        print_method('Reading the plugin index')
        index = plugin_index.fetch_index()
        if index is not None:
            plugins = plugin_index.plugins_from_index(index, pymodaq_version)
            if plugins:
                print_method(f"Plugin index of {index.get('generated', '')}: {len(plugins)} plugins")
                return plugins
        print_method('Plugin index not available, browsing PyPI (slower)')
    return get_pypi_plugins(pymodaq_version=pymodaq_version, print_method=print_method)


def get_plugin_sourcefile_id(filename):
    """Get the SHA identifier of a vien file"""
    h = sha256()
    b = bytearray(128*1024)
    mv = memoryview(b)
    with open(filename, 'rb', buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()


def get_plugins(from_json=False, browse_pypi=True, pymodaq_version: Version = None, print_method=logger.info):
    """get PyMoDAQ plugins

    Parameters
    ----------
    from_json: bool
        if True get the plugins list and source files from the json data file (deprecated) else from the pypi server
    browse_pypi: bool
        if from_json is False:
            if True get the list of plugins name from the https://pypi.org/simple/ website, then get the sources from
            the pypiserver
            if False, get the list of plugins name from the json data, then fetch the source from the pypi server
    pymodaq_version: Version
        the current version of PyMoDAQ
    print_method: Callable
        a callable accepting string
    Returns
    -------
    plugins_available: list of available plugins for installation
    plugins_installed: list of already installed plugins
    plugins_update: list of plugins with existing update
    """
    print_method('Fetching plugin list')
    plugins_available = get_available_plugins(pymodaq_version=pymodaq_version, print_method=print_method)

    plugins = deepcopy(plugins_available)
    discovered_plugins = get_entrypoints('pymodaq.plugins')
    plugins_installed_init = [{'plugin-name': entry.value,
                          'version': metadata.version(entry.value)} for entry in discovered_plugins]
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


def capitalize(string, Nfirst=1):
    """
    Returns same string but with first Nfirst letters upper
    Parameters
    ----------
    string: (str)
    Nfirst: (int)
    Returns
    -------
    str
    """
    return string[:Nfirst].upper() + string[Nfirst:]

def write_plugin_doc():
    """Update the README, the table of plugins and the static index of instruments from info of all available plugins

    The three files are built from the same list of plugins, in a single run (weekly job of the repository):
    ``README.md``, ``doc/PluginList.md`` and ``doc/instruments.json`` (see :mod:`pymodaq_plugin_manager.index`)
    """


    plugins = get_pypi_plugins(browse_pypi=True)
    base_path = Path(__file__).parent

    header_keys = ['display-name', 'version', 'description']
    header = ['Repo Name', 'Version plugin', 'Instruments']
    plugins_tmp = []

    plugins.sort(key=lambda plugin: plugin['plugin-name'].lower())

    for ind, plug in enumerate(plugins):
        tmp = []

        for k in header_keys:
            if k == 'display-name':
                tmp.append(f'<a href="{plug["homepage"].rstrip()}"'
                           f' target="_top">'
                           f'{capitalize(plug["plugin-name"].rstrip()[16:])}'
                           f'</a> ')
            elif k == 'authors':
                authors = extract_authors_from_description(plug['description'])
                if len(authors) == 0:
                    authors == plug[k]
                doc, tag, text = Doc().tagtext()
                with tag('ul'):
                    for auth in authors:
                        with tag('li'):
                            text(auth.rstrip())
                tmp.append(doc.getvalue())
            elif k == 'version':
                tmp.append(f'<a href="{plug["homepage"]}" target="_top">{plug["version"]}</a> ')
            elif k == 'description':
                doc, tag, text = Doc().tagtext()
                #text(plug[k]+'\r\n')
                if plug['instruments']:

                    for inst in plug['instruments']:
                        text(f'{inst}:')
                        with tag('ul'):
                            for instt in plug['instruments'][inst]:
                                with tag('li'):
                                    text(instt.rstrip())
                    tmp.append(doc.getvalue())
                else:
                    lines = plug['description'].split('\n')
                    header_inst = ['Actuators', 'Viewer0D', 'Viewer1D', 'Viewer2D', 'ViewerND']
                    for header_ind, head in enumerate(header_inst):
                        instrument_text = []
                        for ind_line, line in enumerate(lines):
                            if head in line:
                                instrument_text.append(line.rstrip())
                                for subline in lines[ind_line+1:]:
                                    if subline[0:4] == '* **':
                                        instrument_text.append(subline[2:].rstrip())
                                    elif any([hd in subline for hd in header_inst[header_ind+1:]]):
                                        break
                        if len(instrument_text) > 1:
                            text(instrument_text[0])
                            for inst_txt in instrument_text[1:]:
                                with tag('ul'):
                                    with tag('li'):
                                        text(inst_txt)


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

    index = plugin_index.build_index(plugins)
    plugin_index.save_index(index, base_path.parent.parent.joinpath('doc/instruments.json'))


    with open(base_path.parent.parent.joinpath('README_base.md'), 'r') as f:
        content = f.read()
        content += '\r\n'

    with open(base_path.parent.parent.joinpath('README.md'), 'w') as f:
        content += writer.dumps()
        f.write(content)


if __name__ == '__main__':
    write_plugin_doc()  # do not modify this as it is run by github actions
    #get_plugins()
