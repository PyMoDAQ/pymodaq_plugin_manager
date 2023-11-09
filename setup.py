from setuptools import setup, find_packages
import json
from pathlib import Path

with open(str(Path(__file__).parent.joinpath(f'src/pymodaq_plugin_manager/VERSION')), 'r') as fvers:
    version = fvers.read().strip()

with open('README_base.md') as fd:
    long_description = fd.read()

setupOpts = dict(
    name='pymodaq_plugin_manager',
    description="Manager and interface to list, install or remove PyMoDAQ's plugins",
    long_description=long_description,
    license='CECILL B',
    url='',
    author="Sébastien Weber",
    author_email='sebastien.weber@cemes.fr',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 5 - Production/Stable",
        "Environment :: Other Environment",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Human Machine Interfaces",
        "Topic :: Scientific/Engineering :: Visualization",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: User Interfaces",
    ], )


setup(
    version=version,
    packages=find_packages(where='./src'),
    package_dir={'': 'src'},
    include_package_data=True,
    entry_points={'console_scripts': ['plugin_manager=pymodaq_plugin_manager.manager:main',
                                      'write_plugins_doc=pymodaq_plugin_manager.validate:write_plugin_doc']},
    install_requires=[
        'distlib',
        'jsonschema',
        'pytablewriter',
        'requests',
        'yawrap',
        'lxml',
        'readme_renderer',
        ],
    **setupOpts
)

