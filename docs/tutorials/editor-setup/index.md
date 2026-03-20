---
title: Editor Setup
description: Configure your favorite editor to work with Prove
keywords: Prove editor setup, IDE, syntax highlighting, LSP
---

# Editor Setup

Prove has support for multiple editors through tree-sitter parsers and LSP. This section contains guides for setting up your favorite editor.

## Supported Editors

| Editor | Syntax Highlighting | LSP | Formatter |
|--------|-------------------|-----|-----------|
| Neovim | tree-sitter | prove-lsp | prove CLI |
| VS Code | tree-sitter | prove-lsp | prove CLI |
| Other | tree-sitter | — | prove CLI |

## Quick Start

All editors require:

1. **Install Prove**:
   ```bash
   pip install -e ".[dev]"
   ```

2. **Install tree-sitter parser** (see editor-specific guide)

3. **Start the LSP** — `prove lsp` starts automatically when you open a `.prv` file. ML completion stores are downloaded to `~/.prove/` on first use.

## Requirements

- Python 3.11+
- tree-sitter CLI (for building parsers)
- A compiler (gcc/clang) for building native components
