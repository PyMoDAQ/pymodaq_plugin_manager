"""get_pypi_plugins reads the instruments of the plugin from its README (the PyPI description)"""
import pytest

pytest.importorskip('pymodaq_utils.plugin_tools.readme')  # needs pymodaq_utils >= 5.3.8
pytest.importorskip('distlib')
pytest.importorskip('pytablewriter')
pytest.importorskip('yawrap')

from pymodaq_plugin_manager import validate

README = """
pymodaq_plugins_demo
####################

Authors
=======

* First Author (first@lab.org)

Instruments
===========

Actuators
+++++++++

* **MyStage**: a stage (tested on model X)

Viewer2D
++++++++

* **MyCamera**: a camera
"""


def test_get_pypi_plugins_fills_instruments(monkeypatch):
    monkeypatch.setattr(validate, 'get_pypi_package_list', lambda *a, **k: ['pymodaq-plugins-demo'])
    monkeypatch.setattr(validate, 'get_pypi_pymodaq',
                        lambda name, *a, **k: {'version': '5.3.1'} if name == 'pymodaq' else
                        {'version': '1.0.0', 'description': README, 'author': 'Someone', 'project_url': 'http://x'})
    plugins = validate.get_pypi_plugins(print_method=lambda *a: None)
    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin['plugin-name'] == 'pymodaq_plugins_demo'
    assert plugin['instruments'] == {'Actuators': ['MyStage: a stage (tested on model X)'],
                                     'Viewer2D': ['MyCamera: a camera']}
    assert plugin['authors'] == ['First Author (first@lab.org)']
