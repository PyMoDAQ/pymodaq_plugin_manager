import chardet
import logging
import ast
import sys
from pathlib import Path
import subprocess
import importlib
import argparse
import pkgutil

from pymodaq_data import Q_, Unit

from pymodaq_plugin_manager.validate import  get_pypi_plugins


def _detect_encoding(filename):
    '''
       Detect encoding of a file 

    Parameters
    ----------
    filename: str
        the file for which the encoding is to be detected
    Returns
    -------
    str:
        The encoding
    '''
    with open(filename, "rb") as f:
        raw = f.read()
        return chardet.detect(raw)['encoding']


class PyMoDAQPlugin:
    '''
        A simple class to represent a PyMoDAQ plugin, from a `pip install`
        point of view
    '''
    def __init__(self, name, version):
        self._name = name
        self._version = version
        self._install_result = None
        self.failed_imports = []
        self.failed_units = []
        self.failed_other = []

    @property
    def name(self):
        return self._name
    
    @property
    def version(self):
        return self._version
    
    def _get_location(self):
        return importlib.util.find_spec(self._name).submodule_search_locations[0]

    def install(self) -> bool:
        '''
           Try to install this plugin using pip

        Returns
        -------
        bool:
            True if the plugin could be installed or is already installed, False otherwise    
        '''
        package = f'{self._name}=={self._version}' if self._version else f'{self._name}'
        command = [sys.executable, '-m', 'pip', 'install', package]
        if args.pymodaq:
            command.append(args.pymodaq)
            
        self._install_result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return self._install_result.returncode == 0

    def _save_report(self, name, stream, path = None):
        if not path:
            path = args.reports_path
        else:
            path = Path(path) 
        with open(path / name, 'w') as f:
            f.write(stream)

    def save_install_report(self, path = None):
        self._save_report(f'install_report_{self._name}_{self._version}.txt', self._install_result.stdout, path=path)

    def save_import_report(self, path = None):
        self._save_report(f'import_report_{self._name}_{self._version}.txt', '\n'.join(self._failed_imports + ['']), path=path) 

    def save_import_report(self):
        self._save_report(f'import_report_{self._name}_{self._version}.txt', '\n'.join(self.failed_imports + ['']))

    def save_units_report(self):
        self._save_report(f'unit_report_{self._name}_{self._version}.txt', '\n'.join(self.failed_units + ['']))

    def save_other_report(self):
        self._save_report(f'other_report_{self._name}_{self._version}.txt', '\n'.join(self.failed_other + ['']))

    def get_move_plugins(self):
        pkg_name = self._name
        try:
            move_mod = importlib.import_module(f'{pkg_name}.daq_move_plugins')
            plugin_list = []
            try:

                for mod in pkgutil.iter_modules([str(move_mod.path.parent)]):
                    if 'daq_move_' in mod:
                        plugin_list.append(mod[1])
            except Exception as e:
                self.failed_other.append(f'Unknown: {e} in {mod}')
        except Exception as e:
            plugin_list = []
            move_mod = None
            self.failed_other.append(f'Unknown: {e} in {move_mod}')


        return plugin_list, move_mod

    def units_valid(self):
        plugin_list, move_mod = self.get_move_plugins()
        for plug in plugin_list:
            try:
                name = plug.split('daq_move_')[1]
                print(name)
                klass = getattr(getattr(move_mod, plug), f'DAQ_Move_{name}')
                if not isinstance(klass._controller_units, list):
                    units = [klass._controller_units]
                else:
                    units = klass._controller_units
                for unit in units:
                    Unit(unit)  # check if the unit is known from pint
            except Exception as e:
                self.failed_units.append(f'Unit error in {move_mod}/{plug}: {str(e)}')

    def all_imports_valid(self) -> bool:
        '''
            Check if this plugin imports are all valid

        Returns
        -------
        bool:
            True if all imports are valid (no import failed), False otherwise    
        '''

        install_path = self._get_location()

        for filename in Path(install_path).glob('**/*.py'):
            with open(filename, 'r', encoding=_detect_encoding(filename)) as f:
                tree = ast.parse(f.read(), filename=filename)
                for node in tree.body:
                    try:
                        if (isinstance(node, ast.ImportFrom) and 'pymodaq' in node.module) \
                        or (isinstance(node, ast.Import) and any('pymodaq' in name.name for name in node.names)):
                            for name in node.names:
                                try:
                                    if isinstance(node, ast.ImportFrom):
                                        import_code = f'from {node.module} import {name.name}'
                                        getattr(importlib.import_module(node.module), name.name)                            
                                    elif isinstance(node, ast.Import):
                                        import_code = f'import {name.name}'
                                        if name.asname:
                                            import_code += f' as {name.asname}'
                                        importlib.import_module(node.module)
                                
                                except (ImportError, ModuleNotFoundError):
                                    self.failed_imports.append(f'"{import_code}" in {filename} ({node.lineno})')
                                except Exception as e:
                                    self.failed_other.append(f'Unknown: {e} in {filename}')
                    except TypeError as te:
                        pass


def parse_args():
    parser = argparse.ArgumentParser(description="Detect incompatibilities between a PyMoDAQ version and the released plugins")
    parser.add_argument("-r", type=Path, default=Path("reports/"), dest="reports_path", help="Path to the reports folder (default: reports/)")
    parser.add_argument("-p", type=str, default=None, dest="plugin", help="plugin to check (instead of the complete list)")
    parser.add_argument(nargs="?", type=str, default="", dest="pymodaq", help="Installation source of the PyMoDAQ package (default: empty string)")

    return parser.parse_args()


def main():
    '''
        The script use `get_pypi_plugins` function to get a list of all PyMoDAQ plugins.
        Then it tries to install each plugin. If it fails it write a report (in `args.reports_path`)
        Otherwise, it tries to execute all its import clauses containing "pymodaq". If at least 
        one import fail, a report is made (with relevant information).

        Finally, if something failed, the script signal it by returning with an exit code of 1.
    '''
    global args

    args = parse_args()
    
    code = 0
    args.reports_path.mkdir(parents=True, exist_ok=True)

    if args.plugin:
        plugin_list = [{"plugin-name" : args.plugin, "version" : None}]
    else:
        plugin_list = get_pypi_plugins()


    for p in plugin_list:
        plugin = PyMoDAQPlugin(p['plugin-name'], p['version'])
        if plugin.install():
            plugin.all_imports_valid()
            if len(plugin.failed_imports) > 0:
                plugin.save_import_report()
                code = 1
            plugin.units_valid()
            if len(plugin.failed_units) > 0:
                plugin.save_units_report()
                code = 1
            if len(plugin.failed_other) > 0:
                plugin.save_other_report()
                code = 1
        else:
            plugin.save_install_report()
            code = 1
    sys.exit(code)


if __name__ == '__main__':
    main()
