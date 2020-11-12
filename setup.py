
import importlib
import sys
try:
    import setuptools
    from setuptools import setup, find_packages
    from setuptools.command import install
except ImportError:
    sys.stderr.write("Warning: could not import setuptools; falling back to distutils.\n")
    from distutils.core import setup
    from distutils.command import install

version = importlib.import_module('.version', 'pymodaq_plugin_manager')

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
        "License :: CeCILL-B Free Software License Agreement (CECILL-B)",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: User Interfaces",
    ], )


setup(
    version=version.get_version(),
    packages=find_packages(),
    include_package_data=True,
    entry_points={'console_scripts': ['plugin_manager=pymodaq_plugin_manager.manager:main',]},
    install_requires=[
        'distlib',
        'jsonschema',
        'pytablewriter',
        'requests',
        'yawrap',
        ],
    **setupOpts
)

