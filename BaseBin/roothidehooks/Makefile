TARGET := iphone:clang:latest:15.0
INSTALL_TARGET_PROCESSES = lsd cfprefsd
FINALPACKAGE = 1
THEOS_PACKAGE_SCHEME = roothide
ARCHS = arm64 arm64e

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = cleanerhooks

cleanerhooks_FILES = $(wildcard *.x) $(wildcard *.c) $(wildcard *.m)
cleanerhooks_CFLAGS = -Werror -fobjc-arc -I../.include
cleanerhooks_LDFLAGS = -rpath @loader_path/.jbroot/Library/Frameworks -rpath @loader_path/fallback -L../libjailbreak -ljailbreak
cleanerhooks_INSTALL_PATH = /basebin

include $(THEOS_MAKE_PATH)/tweak.mk

after-cleanerhooks-all::
	install_name_tool -change @loader_path/.jbroot/usr/lib/libsubstrate.dylib @rpath/CydiaSubstrate.framework/CydiaSubstrate $(THEOS_OBJ_DIR)/cleanerhooks.dylib
	ldid -S $(THEOS_OBJ_DIR)/cleanerhooks.dylib
