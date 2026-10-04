CC ?= cc
PYTHON ?= python3
BUILD ?= build
UNAME_S := $(shell uname -s)
include sources.mk

CPPFLAGS += -Ivendor/doomgeneric -DDOOMGENERIC_RESX=320 -DDOOMGENERIC_RESY=200 \
            -DNORMALUNIX -D_DEFAULT_SOURCE
CFLAGS ?= -O2
CFLAGS += -std=c11 -fPIC -fvisibility=hidden -ffunction-sections -fdata-sections
ifeq ($(UNAME_S),Darwin)
LIBRARY := $(BUILD)/libchromatic_doom.dylib
SHARED_FLAGS := -dynamiclib -Wl,-dead_strip
else
LIBRARY := $(BUILD)/libchromatic_doom.so
SHARED_FLAGS := -shared -Wl,--gc-sections -Wl,-Bsymbolic
endif

DOOM_OBJECTS := $(patsubst %.c,$(BUILD)/%.o,$(DOOM_SOURCES))
OBJECTS := $(DOOM_OBJECTS) $(BUILD)/chromatic_doom.o

all: $(LIBRARY)

$(LIBRARY): $(OBJECTS)
	$(CC) $(SHARED_FLAGS) $(LDFLAGS) -o $@ $^ -lm

# Hide the upstream global symbols to avoid accidental interposition from
# Python extensions; the adapter exports only its documented API below.
$(BUILD)/vendor/doomgeneric/%.o: vendor/doomgeneric/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -Dexit=cd_engine_exit -MMD -MP -c $< -o $@

$(BUILD)/chromatic_doom.o: chromatic_doom.c chromatic_doom.h
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c $< -o $@

check: $(LIBRARY)
	$(PYTHON) test_headless.py --library $(LIBRARY)

clean:
	rm -rf $(BUILD)

-include $(OBJECTS:.o=.d)
.PHONY: all check clean
