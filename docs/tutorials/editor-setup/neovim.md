---
title: Neovim Setup
description: Configure Neovim for Prove development with tree-sitter and LSP
keywords: Neovim, Prove, tree-sitter, LSP, nvim
---

# Neovim Setup

This guide covers setting up Prove in Neovim with syntax highlighting (tree-sitter) and language server (LSP).

## Prerequisites

- Neovim 0.10+
- Python 3.11+
- gcc/clang for building tree-sitter parser

## Install Prove

```bash
pip install -e ".[dev]"
prove setup
```

The `prove setup` command downloads NLP models and builds data stores for the LSP.

---

## Tree-Sitter Setup

### Option 1: Using nvim-treesitter (Recommended)

[NvChad](https://nvchad.com/) users and those with nvim-treesitter already configured:

1. Add to your `nvim-treesitter` config:

```lua
require("nvim-treesitter.install").compilers = { "clang", "gcc" }

require("nvim-treesitter.configs").setup({
  ensure_installed = {
    -- other parsers
    "prove",
  },
  highlight = {
    enable = true,
  },
})
```

2. Add filetype detection:

```lua
vim.filetype.add({
  extension = {
    prv = "prove",
    intent = "prove",
  },
})
```

3. Force-load the parser (if not auto-detected):

```lua
pcall(vim.treesitter.language.add, "prove", {
  path = vim.fn.stdpath("data") .. "/lazy/nvim-treesitter/parser/prove.so",
})
```

### Option 2: Manual Installation

Build and install the parser manually:

```bash
cd tree-sitter-prove
npm install
npm run build
```

Then symlink the parser:

```bash
mkdir -p ~/.local/share/nvim/site/pack/vendor/start/nvim-treesitter/parser
ln -s ~/Projects/prove/tree-sitter-prove/parser/prove.so \
  ~/.local/share/nvim/site/pack/vendor/start/nvim-treesitter/parser/prove.so
```

---

## LSP Setup (prove-lsp)

Prove includes an LSP server for diagnostics, code completion, and go-to-definition.

### Option 1: NvChad / nvim-lspconfig

Add this to your LSP config (`lua/configs/lspconfig.lua`):

```lua
vim.api.nvim_create_autocmd("FileType", {
  pattern = "prove",
  callback = function()
    vim.lsp.start({
      name = "prove-lsp",
      cmd = { "prove-lsp" },
      root_dir = vim.fs.root(0, { "prove.toml", ".git" }),
    })
  end,
})
```

The LSP will start automatically when opening `.prv` files.

### Option 2: Manual LSP Config

```lua
local lspconfig = require("lspconfig")

lspconfig.prove_lsp = {
  cmd = { "prove-lsp" },
  filetypes = { "prove" },
  root_dir = function(fname)
    return vim.fs.root(fname, { "prove.toml", ".git" })
  end,
}

lspconfig.prove_lsp.setup({})
```

### Verify LSP is Running

Open a `.prv` file and run:

```vim
:LspInfo
```

You should see `prove-lsp` listed as an active client.

---

## Formatting

Use the Prove CLI for formatting:

```vim
:!prove format %
```

Or configure conform.nvim / null-ls:

```lua
require("conform.nvim").setup({
  formatters_by_ft = {
    prove = { "prove" },
  },
})
```

With `prove` formatter defined as:

```lua
formatters = {
  prove = {
    command = "prove",
    args = { "--stdin-filename", "$FILENAME", "format", "-" },
    stdin = true,
  },
}
```

---

## Syntax Highlighting Queries

Prove's tree-sitter queries are in `tree-sitter-prove/queries/prove/`:

- `highlights.scm` — syntax highlighting
- `locals.scm` — scopelocal variables
- `tags.scm` — ctags support

These are automatically loaded when using nvim-treesitter.

---

## Verify Your Setup

1. Open a `.prv` file:

```bash
nvim hello.prv
```

2. Check tree-sitter is active:

```vim
:TSInspect
```

3. Check LSP diagnostics:

```vim
:Trouble
```

---

## Troubleshooting

### Parser not loading

Ensure the parser file exists:

```bash
ls ~/.local/share/nvim/lazy/nvim-treesitter/parser/prove.so
```

If missing, rebuild:

```bash
cd tree-sitter-prove
npm run build
```

### LSP not starting

Check prove-lsp is installed:

```bash
which prove-lsp
prove-lsp --version
```

If not found, run:

```bash
prove setup
```

### No syntax highlighting

Force reload:

```vim
:edit!
:TSUpdateSync prove
```
