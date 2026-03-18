# Post-1.0: Identity-Bound Compilation

## Source

`ai-resistance.md` — Future Research (Post-1.0)

## Description

Source files carry a cryptographic signature chain. The compiler verifies
authorship. Scraped code with stripped signatures won't compile.

## Prerequisites

- Binary AST format (01-binary-ast-format.md) — signatures embed in binary
- Key management story (where do keys live? how are they distributed?)
- Trust model (who signs? individual devs? org keys? CI?)

## Key decisions

- Signature algorithm (Ed25519? GPG integration?)
- Key storage (`.prove/keys/`? system keyring? hardware tokens?)
- What happens when a key is revoked or lost?
- Open-source friction: how do contributors sign patches?
- CI/CD: how do build servers sign?
- Signature scope: per-file? per-function? per-commit?

## Scope

Large. Requires cryptographic infrastructure, key management UX, and
changes to the build pipeline. The trust model design is the hard part.
