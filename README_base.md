# PyMoDAQ Plugin Manager

[<img src="https://img.shields.io/pypi/v/pymodaq_plugin_manager.svg">](https://pypi.org/project/pymodaq_plugin_manager/)
[<img src="https://readthedocs.org/projects/pymodaq/badge/?version=latest">](https://pymodaq.readthedocs.io/en/stable/?badge=latest)
[<img src="https://github.com/PyMoDAQ/pymodaq_plugin_manager/workflows/Upload%20Python%20Package/badge.svg">](https://github.com/PyMoDAQ/pymodaq_plugin_manager)


A plugin manager for PyMoDAQ, Modular Data Acquisition with Python.

Give a list of available, installable or updatable plugins compatible with pymodaq


## Is my instrument supported?

Search the table below, or the **Instruments** column of the manager (search box: `Kinesis`, `iXon`, `thorlabs kpz`...).

The list is compiled every week from the README of each plugin published on PyPI, in a single run which writes:

* this README and `doc/PluginList.md`: the table of plugins,
* [`doc/instruments.json`](doc/instruments.json): the same information for programs (plugin, version, PyMoDAQ versions
  it works with, authors, instruments by type with their description).

The manager reads `doc/instruments.json` (cached on disk for 24 hours) instead of browsing PyPI, which is much faster.
Set `PYMODAQ_PLUGIN_MANAGER_LIVE=1` to browse PyPI and see a plugin released since the last compilation, and
`PYMODAQ_PLUGIN_INDEX_URL` to read another index (an url or a file). The index is at
https://raw.githubusercontent.com/PyMoDAQ/pymodaq_plugin_manager/main/doc/instruments.json
