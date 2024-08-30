import os
import re

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__name__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.md')) as f:
    CHANGES = f.read()

with open(os.path.join(here, 'requirements.interface.txt')) as f:
    re_ = re.compile(r'(.+)==')
    recommend = f.read().splitlines()
requires = [re_.match(r).group(1) for r in recommend]

tests_require = [
    'pytest',  # includes virtualenv
    'pytest-cov'
]

setup(
    name='qgis_server_light',
    version='v0.0.1',
    description='qgis renderer as a python process',
    long_description=README + '\n\n' + CHANGES,
    classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
    ],
    author='Clemens Rudert (OPENGIS.ch)',
    author_email='clemens@opengis.ch',
    url='https://github.com/opengisch/qgis-server-light',
    keywords=['web worker qgis qgis-server processing'],
    packages=['qgis_server_light.interface'],
    package_dir={'': 'src'},
    package_data={
        "qgis_server_light.interface": ["*.py"]
    },
    py_modules=[
        'qgis_server_light/interface/job',
        'qgis_server_light/interface/dispatcher',
        'qgis_server_light/interface/qgis'

    ],
    include_package_data=True,
    zip_safe=False,
    project_urls={
        'Documentation': 'https://github.com/opengisch/qgis-server-light',
        'Changelog': 'https://github.com/opengisch/qgis-server-light/blob/master/CHANGES.md',
        'Issue Tracker': 'https://github.com/opengisch/qgis-server-light/issues',
    },
    extras_require={
        'recommend': recommend,
        'no-version': requires,
        'testing': tests_require,
    },
    entry_points={
    }
)
