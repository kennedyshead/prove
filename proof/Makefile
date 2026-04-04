PREFIX ?= ~/.local/bin

clean: 
	rm -rf build dist .prove

build:
	@test -f ../.envrc && . ../.envrc; python -m prove build && ./dist/proof build --compiler

install: build
	cp dist/proof $(PREFIX)/

.PHONY: clean build install
