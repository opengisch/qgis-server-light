import os
import re
from glob import glob

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.md')) as f:
    CHANGES = f.read()

with open(os.path.join(here, 'requirements.txt')) as f:
    re_ = a = re.compile(r'(.+)==')
    recommend = f.read().splitlines()
requires = [re_.match(r).group(1) for r in recommend]

tests_require = [
    'WebTest >= 1.3.1',  # py3 compat
    'pytest',  # includes virtualenv
    'pytest-cov'
    ]

setup(
    name='qgis_server_light',
    version='v1.0.0',
    description='qgis server in a light weight manner.',
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
    keywords=['web wsgi bfg pylons pyramid qgis qgis-server'],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(path))[0] for path in glob('src/*.py')],
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
        'paste.app_factory': [
            'main = qgis_server_light:main'
        ]
    }
)
