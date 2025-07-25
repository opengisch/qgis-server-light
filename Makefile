# ********************
# Variable definitions
# ********************

# QSL runtime variables (which can be overwritten when calling make with the corresponding ENV variables e.g.:
# QSL_REDIS_URL=redis://my.redis.domain:9999 make run
QSL_REDIS_URL ?= redis://localhost:1234
QSL_SVG_PATH ?= /io/svg
QSL_DATA_ROOT ?= /io/data
QSL_LOG_LEVEL ?= info

ifneq (,$(wildcard .env))
  include .env
  export
endif


# Package name
PACKAGE = qgis_server_light
LOCATION ?= ./src


VENV_PATH ?= .venv
VENV_REQUIREMENTS = $(VENV_PATH)/.timestamp
PIP_REQUIREMENTS = $(VENV_PATH)/.requirements-timestamp
DOC_REQUIREMENTS = $(VENV_PATH)/.doc-requirements-timestamp
DOCS_CONFIGURATION = docs/mkdocs.yml
PROJECT_REQUIREMENTS = $(VENV_PATH)/.$(PACKAGE)-requirements-timestamp
DEV_REQUIREMENTS = $(VENV_PATH)/.dev-requirements-timestamp
TEST_REQUIREMENTS = $(VENV_PATH)/.test-requirements-timestamp
VENV_BIN = $(VENV_PATH)/bin
PIP_COMMAND = pip3
PYTHON_PATH = $(shell which python3)
PYTHON_VERSION = $(shell printf '%b' "import sys\nprint(f'{sys.version_info.major}.{sys.version_info.minor}')" | $$(which python3))
PYCACHE = $(shell find ./src -name "*.pyc")

# Path where the pyqgis system path will be written to
QGIS_VENV_PATH = $(VENV_PATH)/lib/python$(PYTHON_VERSION)/site-packages/qgis_paths.pth

# Python source files
SRC_PY = $(shell find $(LOCATION)/$(PACKAGE) -name '*.py')

# *******************
# Set up environments
# *******************

$(VENV_REQUIREMENTS):
	$(PYTHON_PATH) -m venv $(VENV_PATH)
	touch $@

$(QGIS_VENV_PATH): $(VENV_REQUIREMENTS)
	# we dont use the python path of the venv but the system python here on purpose, because this
	# is the only one shipping the pyqgis if QGIS is installed. This step is meant to fail if QGIS is not
	# installed.
	echo $(shell which pyhton3)
	echo $(shell python3 -c 'import os; import qgis; from pathlib import Path; print(Path(os.path.dirname(qgis.__file__)).parent)') > $@

$(PIP_REQUIREMENTS): $(VENV_REQUIREMENTS)
	$(VENV_BIN)/$(PIP_COMMAND) install --upgrade pip wheel
	touch $@

$(PROJECT_REQUIREMENTS): $(PIP_REQUIREMENTS) requirements.interface.txt requirements.worker.txt requirements.exporter.txt $(QGIS_VENV_PATH)
	$(VENV_BIN)/$(PIP_COMMAND) install -r requirements.interface.txt -r requirements.worker.txt -r requirements.exporter.txt
	touch $@

$(DEV_REQUIREMENTS): $(PROJECT_REQUIREMENTS) requirements.dev.txt
	WITH_WORKER=True $(VENV_BIN)/$(PIP_COMMAND) install -e . -r requirements.dev.txt --config-settings editable_mode=compat
	touch $@

$(DOC_REQUIREMENTS): $(DEV_REQUIREMENTS) requirements.docs.txt
	WITH_WORKER=True $(VENV_BIN)/$(PIP_COMMAND) install -r requirements.docs.txt
	touch $@

$(TEST_REQUIREMENTS): $(DEV_REQUIREMENTS) requirements.test.txt
	WITH_WORKER=True $(VENV_BIN)/$(PIP_COMMAND) install -r requirements.test.txt
	touch $@


# **************
# Common targets
# **************

# Build dependencies
BUILD_DEPS += $(PROJECT_REQUIREMENTS)

.PHONY: install
install: $(PROJECT_REQUIREMENTS)

.PHONY: install-docs
install-docs: $(DOC_REQUIREMENTS)

.PHONY: install-dev
install-dev: $(DEV_REQUIREMENTS)

.PHONY: install-test
install-test: $(TEST_REQUIREMENTS)

.PHONY: clean
clean:
	rm -rf $(PYCACHE)

.PHONY: clean-doc
clean-doc:
	rm -rf docs/site

.PHONY: clean-all
clean-all: clean
	rm -rf build
	rm -rf dist
	rm -rf $(VENV_PATH)
	rm -rf src/$(PACKAGE).egg-info

.PHONY: git-attributes
git-attributes:
	git --no-pager diff --check `git log --oneline | tail -1 | cut --fields=1 --delimiter=' '`

.PHONY: test
test: $(TEST_REQUIREMENTS)
	$(VENV_BIN)/pytest -vv tests

.PHONY: doc-html
doc-html: $(DOC_REQUIREMENTS) $(DOCS_CONFIGURATION)

	$(VENV_BIN)/mkdocs build -f $(DOCS_CONFIGURATION) -d site

.PHONY: doc-serve
doc-serve: $(DOC_REQUIREMENTS) $(DOCS_CONFIGURATION)
	$(VENV_BIN)/mkdocs serve -f $(DOCS_CONFIGURATION)

.PHONY: updates
updates: $(PROJECT_REQUIREMENTS) $(DOC_REQUIREMENTS) $(DEV_REQUIREMENTS) $(TEST_REQUIREMENTS)
	$(VENV_BIN)/pip list --outdated

.PHONY: run
run: $(DEV_REQUIREMENTS)
	$(VENV_BIN)/python -m qgis_server_light.worker.redis --redis-url $(QSL_REDIS_URL) --svg-path $(QSL_SVG_PATH) --data-root $(QSL_DATA_ROOT) --log-level $(QSL_LOG_LEVEL)

.PHONY: run-reload
run-reload: $(DEV_REQUIREMENTS)
	$(VENV_BIN)/hupper -m qgis_server_light.worker.redis --redis-url $(QSL_REDIS_URL) --svg-path $(QSL_SVG_PATH) --data-root $(QSL_DATA_ROOT) --log-level $(QSL_LOG_LEVEL)
