#  Copyright 2023 Hel Industries, all rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt in this repository file going up the directory tree.
#

MICROPYTHON_API_GENERATOR_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ifneq ($(strip $(PLATFORM_UTILS_PRESENT)),yes)
    # If PLATFORM_UTILS_PRESENT is set, we are building against the makefile-based hybrid build system,
    # otherwise we need to solve a few dependencies here so it is stand-alone.
	include $(BUFFER_PREPROCESSOR_DIR)/PlatformUtils/PlatformUtils.mk
    ifneq ($(strip $(PYTHON_ADDITIONAL_PATHS)),)
        PYTHON_ENV ?= PYTHONPATH="$(PYTHON_ADDITIONAL_PATHS)"
    endif
    PYTHON := $(PYTHON_ENV) python
    CFGMSG := printf "    %-30s %s\n"
    MSG := /usr/bin/true
else
	include $(MAKE_INC_PATH)/BuildSystem.mk
    ifeq ($(strip $(filter $(MAKE_INC_PATH)/Python.mk,$(MAKEFILE_LIST))),)
        include $(MAKE_INC_PATH)/Python.mk
    endif
endif

MICROPYTHON_API_GENERATOR := $(MICROPYTHON_API_GENERATOR_DIR)/bin/micropython_api_generator
ifeq ($(strip $(shell ls --color=never $(MICROPYTHON_API_GENERATOR) 2>/dev/null)),)
    MICROPYTHON_API_GENERATOR_PATH := $(MICROPYTHON_API_GENERATOR_DIR)/micropython_api_generator.py
    MICROPYTHON_API_GENERATOR := $(PYTHON) $(MICROPYTHON_API_GENERATOR_PATH)
    MICROPYTHON_API_GENERATOR_MODULES = $(wildcard $(MICROPYTHON_API_GENERATOR_DIR)/micropython_generator/*.py)
endif
MICROPYTHON_API_GENERATOR_FLAGS := $(filter-out --jobserver-fds%,$(MAKEFLAGS))
ifneq ($(strip $(MICROPYTHON_PARSER_CONFIG_PATH)),)
    MICROPYTHON_PARSER_CONFIG_OPTS = --parser-config="$(MICROPYTHON_PARSER_CONFIG_PATH)"
endif

MICROPYTHON_MODULE_TARGET_PATH := $(shell $(MICROPYTHON_API_GENERATOR) --targetpath -s "$(MICROPYTHON_MODULE_TARGET)" $(MAKEFLAGS) -- $(CPPFLAGS) $(CXXFLAGS))
MICROPYTHON_SOURCE_FILES := $(shell $(MICROPYTHON_API_GENERATOR) --sources -s "$(MICROPYTHON_MODULE_TARGET)" $(MAKEFLAGS) -- $(CPPFLAGS) $(CXXFLAGS))

$(MICROPYTHON_MODULE_TARGET_PATH).cpp: $(MICROPYTHON_MODULE_TARGET) $(MICROPYTHON_SOURCE_FILES) $(MICROPYTHON_API_GENERATOR_PATH) $(MICROPYTHON_API_GENERATOR_MODULES)
	@$(MSG) "[GEN]" "Python Module" "$(MICROPYTHON_MODULE_TARGET_PATH)";
	$(V)$(MICROPYTHON_API_GENERATOR) $(MICROPYTHON_PARSER_CONFIG_OPTS) --log -s "$<" $(MICROPYTHON_API_GENERATOR_FLAGS) -- $(CPPFLAGS) $(CXXFLAGS) > /dev/null

python-module: $(MICROPYTHON_MODULE_TARGET_PATH).cpp $(MICROPYTHON_MODULE_TARGET) $(MICROPYTHON_SOURCE_FILES) $(MICROPYTHON_API_GENERATOR_PATH) $(MICROPYTHON_API_GENERATOR_MODULES)
	@:

cfg-python-module:
	@$(CFGMSG) "MICROPYTHON_MODULE_TARGET:" "$(MICROPYTHON_MODULE_TARGET)"
	@$(CFGMSG) "MICROPYTHON_API_GENERATOR_PATH:" "$(MICROPYTHON_API_GENERATOR_PATH)"
	@$(CFGMSG) "MICROPYTHON_MODULE_INCLUDE_PATHS:" "$(MICROPYTHON_MODULE_INCLUDE_PATHS)"
	@$(CFGMSG) "MICROPYTHON_MODULE_TARGET:" "$(MICROPYTHON_MODULE_TARGET).h $(MICROPYTHON_MODULE_TARGET).cpp"

wnk: cfg-python-module