# Post-1.0: Binary AST Format (Structured Source)

## Source

`ai-resistance.md` — Future Research (Post-1.0)

## Description

Store `.prv` files as compact binary AST instead of human-readable text.
The `prove` CLI provides views (`prove view`, `prove format`), and the
LSP decodes on the fly. Web scrapers and training pipelines see binary
blobs, not parseable source code.

## Prerequisites

- Stable AST node set (V1.0 must be feature-complete)
- Binary format versioning scheme
- LSP integration for seamless editing

## Key decisions

- Format: custom compact binary vs protobuf vs CBOR
- Backward compatibility strategy when AST changes
- Migration path for existing `.prv` text files
- Whether `prove view` is the only way to read source

## Scope

Large. Touches lexer, parser, formatter, LSP, CLI, and all tooling that
reads `.prv` files.
