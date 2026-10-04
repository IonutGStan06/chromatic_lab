GBDK_HOME ?= /workspace/.chromatic-tools/gbdk-4.5.0/
LCC := $(patsubst %/,%,$(GBDK_HOME))/bin/lcc
PYTHON ?= python3
SOURCES := src/main.c src/stack.c src/runner.c src/vault.c src/orbit.c src/crates.c src/assets.c
ROM := build/chromatic-arcade.gbc

.PHONY: all test release clean
all: $(ROM)

src/assets.c: tools/art.py
	$(PYTHON) tools/art.py

$(ROM): $(SOURCES) src/arcade.h
	@mkdir -p build
	$(LCC) -Isrc -Wm-yc -Wm-yn"CHROMATIC LAB" -Wl-m -Wl-j -o $@ $(SOURCES)

test: $(ROM)
	$(PYTHON) tools/playtest.py $(ROM)

release: test
	$(PYTHON) tools/package.py

clean:
	rm -rf build
