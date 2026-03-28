PREFIX ?= ~/.local/bin

build:
	@test -f ../.envrc && . ../.envrc; python -m prove build && ./dist/proof build

install: build
	cp dist/proof $(PREFIX)/

.PHONY: build install
