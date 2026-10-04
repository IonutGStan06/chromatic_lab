GBDK_HOME ?= /workspace/.chromatic-tools/gbdk-4.5.0/
LCC := $(patsubst %/,%,$(GBDK_HOME))/bin/lcc
ROM := build/doom-receiver.gbc
PYTHON ?= python3
.PHONY: all test clean
all: $(ROM)
test: $(ROM)
	$(PYTHON) validate.py $(ROM)
$(ROM): main.c Makefile
	mkdir -p build
	$(LCC) -Wm-yC -Wm-yt0x1B -Wm-ya16 -Wm-yn"DOOM RECEIVER" -Wl-m -Wl-j -o $@ $<
clean:
	rm -rf build
