# Gitea Integration Guide

This document describes how to integrate the Prove Chroma lexer into Gitea for syntax highlighting.

## Option 1: Fork Gitea and Add Lexer Directly

### Step 1: Fork Gitea

Fork the Gitea repository at https://github.com/go-gitea/gitea

### Step 2: Clone Your Fork

```bash
git clone https://github.com/YOUR_USERNAME/gitea.git
cd gitea
```

### Step 3: Add the Prove Lexer

Create a new file `modules/highlight/prove.go`:

```go
package highlight

import (
	"github.com/alecthomas/chroma"
)

func init() {
	Register(proveLexer)
}

var proveLexer = chroma.MustNewLexer(
	&chroma.Config{
		Name:      "Prove",
		Aliases:   []string{"prove"},
		Filenames: []string{"*.prv", "*.prove"},
		MimeTypes: []string{"text/x-prove"},
	},
	chroma.Rules{
		"root": {
			{`\s+`, chroma.Text, nil},
			{`///.*$`, chroma.Comment, nil},
			{`//[^\n][^\n]*`, chroma.Comment, nil},
			{`"""[\s\S]*?"""`, chroma.String, nil},
			{`"(?:[^"\\]|\\.)*"`, chroma.String, nil},
			{`0x[0-9a-fA-F][0-9a-fA-F_]*`, chroma.NumberHex, nil},
			{`0b[01][01_]*`, chroma.NumberBin, nil},
			{`0o[0-7][0-7_]*`, chroma.NumberOct, nil},
			{`[0-9][0-9_]*\.[0-9][0-9_]*`, chroma.NumberFloat, nil},
			{`[0-9][0-9_]*`, chroma.Number, nil},
			{`\b(module|type|with|use|transforms|inputs|outputs|validates|main|from|if|else|match|proof|ensures|requires|where|comptime)\b`, chroma.Keyword, nil},
			{`\b(true|false)\b`, chroma.KeywordConstant, nil},
			{`\b(Integer|String|Decimal|Boolean|List|Option|Result|Any|Never)\b`, chroma.KeywordType, nil},
			{`[A-Z][A-Za-z0-9_]*`, chroma.KeywordType, nil},
			{`\|>`, chroma.Operator, nil},
			{`=>`, chroma.Operator, nil},
			{`==|!=|<=|>=|&&|\|\||\.\.`, chroma.Operator, nil},
			{`[+\-*/%=<>!&|^~!]+`, chroma.Operator, nil},
			{`\.`, chroma.Operator, nil},
			{`[a-z_][a-z0-9_]*`, chroma.Name, nil},
			{`[(),;\[\]{}]`, chroma.Punctuation, nil},
			{`:`, chroma.Punctuation, nil},
		},
	},
)
```

### Step 4: Add File Extension Mapping

In your Gitea `app.ini`, add:

```ini
[highlight.mapping]
.prv = prove
.prove = prove
```

### Step 5: Build Gitea

```bash
make build
```

## Option 2: Submit a PR to Gitea

### Step 1: Check Existing Lexers

Look at how other lexers are added in Gitea:

```bash
ls modules/highlight/*.go
```

### Step 2: Add Your Lexer

Follow the pattern in Option 1, but add it to the main Gitea repository.

### Step 3: Create a Pull Request

```bash
git checkout -b add-prove-lexer
git add modules/highlight/prove.go
git commit -m "Add Prove language lexer for syntax highlighting"
git push origin add-prove-lexer
```

Then create a PR at https://github.com/go-gitea/gitea/pulls

## Option 3: Use External Configuration (No Code Changes)

### For Existing Similar Languages

If you just want to highlight `.prv` files using a similar existing lexer, add to `app.ini`:

```ini
[highlight.mapping]
.prv = go
.prove = go
```

Or use any other existing Chroma lexer like `python`, `javascript`, etc.

## Testing Your Integration

1. Build your custom Gitea
2. Start the server
3. Create a file with `.prv` extension
4. View the file in Gitea - it should be syntax highlighted

## Troubleshooting

- **No highlighting**: Check that the file extension is correctly mapped in `[highlight.mapping]`
- **Wrong highlighting**: The lexer might need adjustment - modify the regex patterns in the lexer
- **Cache issues**: Restart Gitea and clear any cache
