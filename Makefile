
VENV_PATH ?= .venv
VENV_REQUIREMENTS = $(VENV_PATH)/.timestamp
PIP_REQUIREMENTS = $(VENV_PATH)/.requirements-timestamp
VENV_BIN = $(VENV_PATH)/bin
PIP_COMMAND = pip3
PYTHON_PATH = $(shell which python3)
PYTHON_VERSION = $(shell printf '%b' "import sys\nprint(f'{sys.version_info.major}.{sys.version_info.minor}')" | $$(which python3))
QGIS_VENV_PATH = $(VENV_PATH)/lib/python$(PYTHON_VERSION)/site-packages/qgis_paths.pth


QGIS_PY_PATH ?= /usr/share/qgis/python

# ********************
# Variable definitions
# ********************

# Package name
PACKAGE = qgis_server_light
LOCATION ?= ./src

# Python source files
SRC_PY = $(shell find $(LOCATION)/$(PACKAGE) -name '*.py')

# Environment variables used for build
BUILD_ENV += \
	DEVELOPMENT=${DEVELOPMENT}

# *******************
# Set up environments
# *******************

$(VENV_REQUIREMENTS):
	$(PYTHON_PATH) -m venv $(VENV_PATH) --system-site-packages
	touch $@

$(QGIS_VENV_PATH):
	echo "/usr/share/qgis/python" > $@

$(PIP_REQUIREMENTS): $(VENV_REQUIREMENTS) requirements.interface.txt requirements.worker.txt requirements.exporter.txt $(QGIS_VENV_PATH)
	$(VENV_BIN)/$(PIP_COMMAND) install --upgrade pip
	$(VENV_BIN)/$(PIP_COMMAND) install -r requirements.interface.txt -r requirements.worker.txt -r requirements.exporter.txt
	touch $@

# **************
# Common targets
# **************

# Build dependencies
BUILD_DEPS += $(PIP_REQUIREMENTS)


.PHONY: install
install: $(PIP_REQUIREMENTS)

.PHONY: build
build: $(BUILD_DEPS)

.PHONY: clean
clean:

.PHONY: clean-all
clean-all: clean
	rm -rf $(VENV_PATH)
	rm -rf src/$(PACKAGE).egg-info

.PHONY: git-attributes
git-attributes:
	git --no-pager diff --check `git log --oneline | tail -1 | cut --fields=1 --delimiter=' '`

.PHONY: lint
lint: $(PIP_REQUIREMENTS)
	$(VENV_BIN)/flake8

.PHONY: test
test: $(PIP_REQUIREMENTS) $(VARS_FILES)
	$(VENV_BIN)/py.test -vv --cov-config .coveragerc --cov $(PACKAGE) --cov-report term-missing:skip-covered tests

.PHONY: check
check: git-attributes lint test

.PHONY: doc-latex
doc-latex: $(PIP_REQUIREMENTS)
	rm -rf doc/build/latex
	$(VENV_BIN)/sphinx-build -b latex doc/source doc/build/latex

.PHONY: doc-html
doc-html: $(PIP_REQUIREMENTS)
	rm -rf doc/build/html
	$(VENV_BIN)/sphinx-build -b html doc/source doc/build/html

.PHONY: updates
updates: $(PIP_REQUIREMENTS)
	$(VENV_BIN)/pip list --outdated

.PHONY: dev
dev: setup.py build
	$(VENV_BIN)/python $< develop

.PHONY: serve
serve: build
	$(VENV_BIN)/pserve application.ini
