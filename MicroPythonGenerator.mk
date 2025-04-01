#  Copyright 2023 Hel Industries, all rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt in this repository file going up the directory tree.
#
# This file is meant to be included in the main Makefile only and any modules required to be included and built need
# to be specified beforehand to allow a module-level control of the API build process. Individual libraries and modules
# will then define their project files, so defining the actual generation is as simple as possible
#

MICROPYTHON_API_GENERATOR_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ifeq ($(strip $(shell ls --color=never $(MAKE_INC_PATH) 2>/dev/null)),)
    # Lets add these, so the makefile can be used standalone
    CFGMSG := printf "    %-30s %s\n"
    VCFGMSG = printf "  %-9s %s\n"
    MSG := /usr/bin/true
    ifneq ($(strip $(PYTHON_ADDITIONAL_PATHS)),)
        PYTHON_ENV ?= PYTHONPATH="$(PYTHON_ADDITIONAL_PATHS)"
    endif
    PYTHON = $(PYTHON_ENV) python
endif

# Tools
MICROPYTHON_API_GENERATOR := $(MICROPYTHON_API_GENERATOR_DIR)/bin/micropython_api_generator
ifeq ($(strip $(shell ls --color=never $(MICROPYTHON_API_GENERATOR) 2>/dev/null)),)
    MICROPYTHON_API_GENERATOR_PATH := $(MICROPYTHON_API_GENERATOR_DIR)/micropython_api_generator.py
    PYTHON_ADDITIONAL_PATHS := $(MICROPYTHON_API_GENERATOR_DIR):$(FRAMEWORK_PATH)/Tools/PytonUtilities:$(FRAMEWORK_PATH)
    ifneq ($(strip $(shell ls --color=never $(MAKE_INC_PATH) 2>/dev/null)),)
        ifeq ($(strip $(filter $(MAKE_INC_PATH)/Python.mk,$(MAKEFILE_LIST))),)
            include $(MAKE_INC_PATH)/Python.mk
        endif
    endif

	MICROPYTHON_API_GENERATOR := $(PYTHON) $(MICROPYTHON_API_GENERATOR_PATH)
    MICROPYTHON_API_GENERATOR_MODULES = $(wildcard $(MICROPYTHON_API_GENERATOR_DIR)/micropython_generator/*.py)
endif

# Proxy the variables, so they don't conflict with ones passed in somehow. Pass in or declare in the including Makefile
# PYTHON_MODULES or PYTHON_OPTIONS
MICROPYTHON_MODULES += $(PYTHON_MODULES)
MICROPYTHON_OPTIONS += $(PYTHON_OPTIONS)

# Resolve some requried variables to make sure we compile with consistent configurations
CPPFLAGS += $(MICROPYTHON_OPTIONS:%=-D%)
INCLUDE_PATHS += $(MICROPYTHON_API_GENERATOR_DIR)/include
INCLUDE_PATHS += $(MICROPYTHON_PATH)
INCLUDE_PATHS += $(MICROPYTHON_PATH)/MicroPython
INCLUDE_PATHS += $(MICROPYTHON_PATH)/MicroPython/ports
INCLUDE_PATHS += $(MICROPYTHON_SOURCE_PATH)
INCLUDE_PATHS += $(MICROPYTHON_SOURCE_PATH)/ports/embed

MICROPYTHON_TARGETS := $(foreach path,$(MICROPYTHON_API_MODULES),$(notdir $(path:%.$(MICROPYTHON_MODULE_FILTER)=%)))
$(foreach path,$(MICROPYTHON_API_MODULES),$(eval MICROPYTHON_TARGET_$(notdir $(path:%.$(MICROPYTHON_MODULE_FILTER)=%)) := $(path)))
$(foreach name,$(MICROPYTHON_TARGETS),$(eval MICROPYTHON_TARGET_PATH_$(name) := $(shell $(MICROPYTHON_API_GENERATOR) --targetpath -s "$(MICROPYTHON_TARGET_$(name))" $(MAKEFLAGS) -- $(CPPFLAGS) $(CXXFLAGS))))
$(foreach name,$(MICROPYTHON_TARGETS),$(eval MICROPYTHON_SOURCE_FILES += $(shell $(MICROPYTHON_API_GENERATOR) --sources -s "$(MICROPYTHON_TARGET_$(name))" $(MAKEFLAGS) -- $(CPPFLAGS) $(CXXFLAGS))))
$(foreach name,$(MICROPYTHON_TARGETS),$(eval MICROPYTHON_MODULES += $(abspath $(dir $(MICROPYTHON_TARGET_PATH_$(name))))))
$(foreach name,$(MICROPYTHON_TARGETS),$(eval MICROPYTHON_INCLUDE_PATHS += $(dir $(MICROPYTHON_TARGET_PATH_$(name)))))
$(foreach name,$(MICROPYTHON_TARGETS),$(eval MICROPYTHON_CPP_FILES += $(MICROPYTHON_TARGET_PATH_$(name)).cpp))
$(foreach name,$(MICROPYTHON_TARGETS),$(eval MICROPYTHON_HEADERS += $(MICROPYTHON_TARGET_PATH_$(name)).h))

INCLUDE_PATHS += $(MICROPYTHON_INCLUDE_PATHS)
CPP_FILES += $(MICROPYTHON_CPP_FILES)
HEADERS += $(MICROPYTHON_HEADERS)

%.py.target: | silent
ifeq ($(strip $(VERBOSE)),1)
	@$(VMSG) "Building Python API"
	@$(VCFGMSG) 'SUBTARGET_NAME:' '$*'
	@$(VCFGMSG) 'MICROPYTHON_TARGET:' '$(MICROPYTHON_TARGET_$*)'
	@$(VCFGMSG) 'MICROPYTHON_API_GENERATOR_PATH:' '$(MICROPYTHON_API_GENERATOR_PATH)'
	@$(VCFGMSG) 'MICROPYTHON_PARSER_CONFIG_PATH:' '$(MICROPYTHON_PARSER_CONFIG_PATH)'
	@$(VCFGMSG) 'CXXFLAGS:' '$(CXXFLAGS)'
	@$(VCFGMSG) 'CPPFLAGS:' '$(CPPFLAGS)'
	@$(VCFGMSG) 'MAKEFLAGS:' '$(MAKEFLAGS)'
	@$(VCFGMSG) 'MAKE_INC_PATH:' '$(MAKE_INC_PATH)'
endif
	@$(MAKE) --file=$(MICROPYTHON_API_GENERATOR_DIR)/MicroPythonModule.mk $(MAKEFLAGS) "MAKE_INC_PATH=$(MAKE_INC_PATH)" "PYTHON_ADDITIONAL_PATHS=$(PYTHON_ADDITIONAL_PATHS)" "MICROPYTHON_MODULE_TARGET=$(MICROPYTHON_TARGET_$*)" "MICROPYTHON_PARSER_CONFIG_PATH=$(MICROPYTHON_PARSER_CONFIG_PATH)" "CPPFLAGS=$(CPPFLAGS)" "CXXFLAGS=$(CXXFLAGS)" python-module

python-api: $(MICROPYTHON_TARGETS:%=%.py.target) $(MICROPYTHON_API_GENERATOR_PATH) $(MICROPYTHON_API_GENERATOR_MODULES)

cfg-python-api: --cfg-python-api $(MICROPYTHON_TARGETS:%=%.py.cfg) | silent
--cfg-python-api:
	@$(CFGMSG) "MICROPYTHON_MODULES:" "$(MICROPYTHON_MODULES)"
	@$(CFGMSG) "MICROPYTHON_OPTIONS:" "$(MICROPYTHON_OPTIONS)"
	@$(CFGMSG) "MICROPYTHON_API_GENERATOR_PATH:" "$(MICROPYTHON_API_GENERATOR_PATH)"
	@$(CFGMSG) "MICROPYTHON_CPP_FILES:" "$(MICROPYTHON_CPP_FILES)"
	@$(CFGMSG) "MICROPYTHON_HEADERS:" "$(MICROPYTHON_HEADERS)"

%.py.cfg: | silent
	@$(MAKE) --file=$(MICROPYTHON_API_GENERATOR_DIR)/MicroPythonModule.mk $(MAKEFLAGS) "MAKE_INC_PATH=$(MAKE_INC_PATH)" "PYTHON_ADDITIONAL_PATHS=$(PYTHON_ADDITIONAL_PATHS)" "MICROPYTHON_TARGET=$(MICROPYTHON_TARGET_$*)" "MICROPYTHON_API_GENERATOR_PATH=$(MICROPYTHON_API_GENERATOR_PATH)" "MICROPYTHON_PARSER_CONFIG_PATH=$(MICROPYTHON_PARSER_CONFIG_PATH)" "CPPFLAGS=$(CPPFLAGS)" "CPPFLAGS=$(CPPFLAGS)" "CXXFLAGS=$(CXXFLAGS)" cfg-python-module

clean-python-api: | silent
	@rm -f $(MICROPYTHON_CPP_FILES) $(MICROPYTHON_HEADERS)

.PHONY: python-api --python-api cfg-python-api --cfg-python-api clean-python-api
