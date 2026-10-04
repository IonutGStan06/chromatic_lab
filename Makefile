GBDK_HOME ?= /workspace/.chromatic-tools/gbdk-4.5.0/
LCC := $(patsubst %/,%,$(GBDK_HOME))/bin/lcc
PYTHON ?= python3
SOURCES := src/main.c src/stack.c src/runner.c src/vault.c src/orbit.c src/crates.c src/assets.c
ROM := build/chromatic-arcade.gbc

.PHONY: all test release clean doom doom-test doom-play doom-release
all: $(ROM)

src/assets.c: tools/art.py
	"$(PYTHON)" tools/art.py

$(ROM): $(SOURCES) src/arcade.h
	@mkdir -p build
	"$(LCC)" -Isrc -Wm-yc -Wm-yn"CHROMATIC LAB" -Wl-m -Wl-j -o $@ $(SOURCES)

test: $(ROM)
	"$(PYTHON)" tools/playtest.py $(ROM)

release: test
	"$(PYTHON)" tools/package.py

doom:
	$(MAKE) -C doom/engine
	$(MAKE) -C doom/receiver GBDK_HOME="$(GBDK_HOME)"

doom-test: doom
	$(MAKE) -C doom/engine check PYTHON="$(PYTHON)"
	$(MAKE) -C doom/receiver test PYTHON="$(PYTHON)" GBDK_HOME="$(GBDK_HOME)"
	"$(PYTHON)" -m unittest discover -s doom/tests -v
	SDL_VIDEODRIVER=dummy "$(PYTHON)" doom/play.py --frames 75 --state-dir "$(CURDIR)/doom/build/sdl-state" --screenshot "$(CURDIR)/doom/build/desktop-preview.png"

doom-play: doom
	"$(PYTHON)" doom/play.py

doom-release: doom-test
	"$(PYTHON)" doom/package.py

clean:
	rm -rf build
