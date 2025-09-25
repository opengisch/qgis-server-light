import os

from setuptools import setup

here = os.path.abspath(os.path.dirname(__name__))
# with open(os.path.join(here, "README.md")) as f:
#     README = f.read()
README = "Interface library to communicate with QGIS-Server light"
with open(os.path.join(here, "CHANGES.md")) as f:
    CHANGES = f.read()

with open(os.path.join(here, "requirements.interface.txt")) as f:
    install_requires = f.read().splitlines()

tests_require = ["pytest", "pytest-cov"]  # includes virtualenv
worker_files = {}
worker_modules = []
worker_packages = []
worker_scripts = []
if os.environ.get("WITH_WORKER", False):
    with open(os.path.join(here, "requirements.worker.txt")) as f:
        install_requires = install_requires + f.read().splitlines()

    worker_files = {"qgis_server_light.worker": ["*.py"]}
    worker_modules = [
        "qgis_server_light/worker/engine",
        "qgis_server_light/worker/image_utils",
        "qgis_server_light/worker/qgis",
        "qgis_server_light/worker/redis",
        "qgis_server_light/worker/runner",
    ]
    worker_packages = ["qgis_server_light.worker"]
    worker_scripts = ["redis_worker=qgis_server_light.worker.redis:main"]

package_data = {"qgis_server_light.interface": ["*.py"]}
package_data.update(worker_files)

setup(
    name="qgis_server_light",
    version="v0.0.2",
    description="qgis renderer as a python process",
    long_description=README + "\n\n" + CHANGES,
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Topic :: Internet :: WWW/HTTP",
        "Typing :: Typed",
    ],
    author="Clemens Rudert (OPENGIS.ch)",
    author_email="clemens@opengis.ch",
    url="https://github.com/opengisch/qgis-server-light",
    keywords=["web worker qgis qgis-server processing"],
    packages=["qgis_server_light.interface"] + worker_packages,
    package_dir={"": "src"},
    package_data=package_data,
    py_modules=[
        "qgis_server_light/interface/job",
        "qgis_server_light/interface/dispatcher",
        "qgis_server_light/interface/qgis",
        "qgis_server_light/interface/exporter",
    ]
    + worker_modules,
    include_package_data=True,
    zip_safe=False,
    project_urls={
        "Documentation": "https://github.com/opengisch/qgis-server-light",
        "Changelog": "https://github.com/opengisch/qgis-server-light/blob/master/CHANGES.md",
        "Issue Tracker": "https://github.com/opengisch/qgis-server-light/issues",
    },
    install_requires=install_requires,
    entry_points={"console_scripts": [] + worker_scripts},
)
