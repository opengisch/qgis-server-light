
PIP_REQUIREMENTS=.venv/.requirements-timestamp
VENV_BIN=.venv/bin/
PIP_COMMAND=pip3

# ********************
# Variable definitions
# ********************

# Package name
PACKAGE = qgis_server_light
LOCATION = src

# Python source files
SRC_PY = $(shell find $(LOCATION)/$(PACKAGE) -name '*.py')

# Environment variables used for build
BUILD_ENV += \
	DEVELOPMENT=${DEVELOPMENT}

# *******************
# Set up environments
# *******************

.venv/timestamp:
	python3 -m venv .venv --system-site-packages
	touch $@

.venv/requirements-timestamp: .venv/timestamp setup.py requirements.txt
	$(VENV_BIN)/$(PIP_COMMAND) install -r requirements.txt
	touch $@

# **************
# Common targets
# **************

# Build dependencies
BUILD_DEPS += .venv/requirements-timestamp


.PHONY: install
install: .venv/requirements-timestamp

.PHONY: build
build: $(BUILD_DEPS)

.PHONY: clean
clean:

.PHONY: clean-all
clean-all: clean
	rm -rf .venv
	rm -rf $(PACKAGE).egg-info

.PHONY: git-attributes
git-attributes:
	git --no-pager diff --check `git log --oneline | tail -1 | cut --fields=1 --delimiter=' '`

.PHONY: lint
lint: .venv/requirements-timestamp
	$(VENV_BIN)/flake8

.PHONY: test
test: .venv/requirements-timestamp $(VARS_FILES)
	$(VENV_BIN)/py.test -vv --cov-config .coveragerc --cov $(PACKAGE) --cov-report term-missing:skip-covered tests

.PHONY: check
check: git-attributes lint test

.PHONY: doc-latex
doc-latex: .venv/requirements-timestamp
	rm -rf doc/build/latex
	$(VENV_BIN)/sphinx-build -b latex doc/source doc/build/latex

.PHONY: doc-html
doc-html: .venv/requirements-timestamp
	rm -rf doc/build/html
	$(VENV_BIN)/sphinx-build -b html doc/source doc/build/html

.PHONY: updates
updates: $(PIP_REQUIREMENTS)
	$(VENV_BIN)/pip list --outdated

.PHONY: serve-dev
serve-dev: setup.py build
	$(VENV_BIN)/python $< develop
	$(VENV_BIN)/pserve dev_application.ini --reload --verbose

.PHONY: serve
serve: build
	$(VENV_BIN)/pserve application.ini
