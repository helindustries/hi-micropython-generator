#  Copyright 2023 Hel Industries, all rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt file in this repository going up the directory tree.
#

#MICROPYTHON_SOURCE_PATH := ../MicroPython
MICROPYTHON_DIR ?= MicroPython
MICROPYTHON_BUILD_DIR ?= build-embed
MICROPYTHON_BUILD_REFERENCE_PATH = $(MICROPYTHON_BUILD_DIR)/genhdr/qstrdefs.generated.h
INCLUDE_PATHS += $(MICROPYTHON_DIR)
INCLUDE_PATHS += $(MICROPYTHON_DIR)/port

ifeq ($(strip $(VERBOSE)),1)
    ECHO ?= @echo
else
    # This silences the generation target output from the MicroPython build system, that breaks our immersion.
    ECHO ?= @/usr/bin/true
endif

# We still care about all the C and C++ files in the module path, even though the python integration
# has to live in a sub-directory as the micropython.mk files are only recognized there.
$(foreach module_path,$(MICROPYTHON_MODULES),$(eval PYTHON_MODULE_HEADERS += $(wildcard $(module_path)/*.h $(module_path)/*/*.h $(module_path)/*/*/*.h $(module_path)/*/*/*.h)))
$(foreach module_path,$(MICROPYTHON_MODULES),$(eval PYTHON_MODULE_C_FILES += $(wildcard $(module_path)/*.c $(module_path)/*/*.c $(module_path)/*/*/*.c $(module_path)/*/*/*.c)))
$(foreach module_path,$(MICROPYTHON_MODULES),$(eval PYTHON_MODULE_CPP_FILES += $(wildcard $(module_path)/*.cpp $(module_path)/*/*.cpp $(module_path)/*/*/*.cpp $(module_path)/*/*/*.cpp)))

HEADERS += $(wildcard $(MICROPYTHON_DIR)/*/*.h $(MICROPYTHON_DIR)/*/*/*.h $(MICROPYTHON_DIR)/*/*/*/*.h)
C_FILES += $(wildcard $(MICROPYTHON_DIR)/*/*.c $(MICROPYTHON_DIR)/*/*/*.c $(MICROPYTHON_DIR)/*/*/*/*.c)
CPP_FILES += $(wildcard $(MICROPYTHON_DIR)/*/*.cpp $(MICROPYTHON_DIR)/*/*/*.cpp $(MICROPYTHON_DIR)/*/*/*/*.cpp)
HEADERS += $(wildcard $(MICROPYTHON_BUILD_DIR)/*/*.h $(MICROPYTHON_BUILD_DIR)/*/*/*.h $(MICROPYTHON_BUILD_DIR)/*/*/*/*.h)
C_FILES += $(wildcard $(MICROPYTHON_BUILD_DIR)/*/*.c $(MICROPYTHON_BUILD_DIR)/*/*/*.c $(MICROPYTHON_BUILD_DIR)/*/*/*/*.c)
CPP_FILES += $(wildcard $(MICROPYTHON_BUILD_DIR)/*/*.cpp $(MICROPYTHON_BUILD_DIR)/*/*/*.cpp $(MICROPYTHON_BUILD_DIR)/*/*/*/*.cpp)

CPPFLAGS += $(MICROPYTHON_OPTIONS:%=-D%)
MICROPYTHON_CPPFLAGS := $(CPPFLAGS) $(INCLUDE_PATHS:%-I%)

$(MICROPYTHON_BUILD_REFERENCE_PATH): $(PYTHON_MODULE_C_FILES) $(PYTHON_MODULE_CPP_FILES) $(PYTHON_MODULE_HEADERS)
	@$(MSG) "[GEN]" "$(MCU_TARGET)" "Modules"
	$(V)$(MAKE) --file=$(MICROPYTHON_SOURCE_PATH)/ports/embed/embed.mk V=$(VERBOSE) "ECHO=@$(ECHO)" "MICROPYTHON_TOP=$(MICROPYTHON_SOURCE_PATH)" "PACKAGE_DIR=$(MICROPYTHON_DIR)" "USER_C_MODULES=$(MICROPYTHON_MODULES)" "CFLAGS_USERMOD=$(CFLAGS) $(MICROPYTHON_CPPFLAGS)" "CXXFLAGS_USERMOD=$(CXXFLAGS) $(MICROPYTHON_CPPFLAGS)" "LDFLAGS_USERMOD=$(LDFLAGS)" "CC=$(CC)" "CXX=$(CXX)" all
	$(V)rm -f ./*.d
	$(V)touch "$@"

python-modules: $(MICROPYTHON_BUILD_REFERENCE_PATH) $(PYTHON_MODULE_C_FILES) $(PYTHON_MODULE_CPP_FILES) $(PYTHON_MODULE_HEADERS)
	@if ls ./*.d > /dev/null 2>&1; then rm -f ./*.d; fi

clean-python-modules:
	@$(MSG) "[CLEAN]" "$(MCU_TARGET)" "MicroPython"
	$(V)rm -fr "$(MICROPYTHON_DIR)"
	$(V)rm -fr "$(MICROPYTHON_BUILD_DIR)"
	@if ls ./*.d > /dev/null 2>&1; then rm -f ./*.d; fi

cfg-python-modules:
	@$(MSG) "[CFG]" "$(MCU_TARGET)" "MicroPython"
	@$(CFGMSG) "MICROPYTHON_MODULES:" "$(MICROPYTHON_MODULES)"
	@$(CFGMSG) "MICROPYTHON_OPTIONS:" "$(MICROPYTHON_OPTIONS)"
	@$(CFGMSG) "MICROPYTHON_TOP:" "$(MICROPYTHON_SOURCE_ABSPATH)"
	@$(CFGMSG) "PACKAGE_DIR:" "$(MICROPYTHON_DIR)"
	@$(CFGMSG) "BUILD:" "$(BUILD_DIR)"
	@$(CFGMSG) "CFLAGS:" "$(PYTHON_MODULE_CFLAGS)"
	@$(CFGMSG) "CXXFLAGS:" "$(PYTHON_MODULE_CXXFLAGS)"
	@$(CFGMSG) "LDFLAGS:" "$(PYTHON_MODULE_LDFLAGS)"

.PHONY: python-modules clean-python-modules cfg-python-modules
