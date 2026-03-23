PREFIX ?= ~/.local/bin

build:
	python -m prove build && ./dist/proof build

install: build
	cp dist/proof $(PREFIX)/

.PHONY: build install
