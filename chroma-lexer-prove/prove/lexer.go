// Package prove provides a Chroma lexer for the Prove programming language.
package prove

import (
	"github.com/alecthomas/chroma"
)

var (
	// Lexer is the Chroma lexer for the Prove programming language.
	Lexer = chroma.MustNewLexer(
		&chroma.Config{
			Name:      "Prove",
			Aliases:   []string{"prove"},
			Filenames: []string{"*.prv", "*.prove"},
			MimeTypes: []string{"text/x-prove"},
		},
		chroma.Rules{
			"root": {
				// Whitespace
				{`\s+`, chroma.Text, nil},

				// Comments
				{`///.*$`, chroma.CommentSpecial, nil},
				{`//[^\n]*`, chroma.Comment, nil},

				// Triple-quoted strings
				{`"""[\s\S]*?"""`, chroma.String, nil},

				// F-strings with interpolation
				{`f"`, chroma.StringAffix, chroma.Push("fstring")},

				// Raw strings (no escapes)
				{`r"[^"]*"`, chroma.StringRegex, nil},

				// Regular strings
				{`"`, chroma.String, chroma.Push("string")},

				// Regex literals (deprecated /pattern/ form)
				{`/[^\s/]([^/\n\\]|\\.)*?/`, chroma.StringRegex, nil},

				// Numbers
				{`0x[0-9a-fA-F][0-9a-fA-F_]*`, chroma.NumberHex, nil},
				{`0b[01][01_]*`, chroma.NumberBin, nil},
				{`0o[0-7][0-7_]*`, chroma.NumberOct, nil},
				{`[0-9][0-9_]*\.[0-9][0-9_]*`, chroma.NumberFloat, nil},
				{`[0-9][0-9_]*`, chroma.Number, nil},

				// Fail marker (before operators so ! is not consumed)
				{`!`, chroma.KeywordPseudo, nil},

				// Intent verbs
				{`\b(transforms|inputs|outputs|validates)\b`, chroma.KeywordDeclaration, nil},

				// Contract keywords
				{`\b(ensures|requires|proof)\b`, chroma.KeywordNamespace, nil},

				// Core keywords
				{`\b(module|type|is|as|from|match|where|comptime|valid|main)\b`, chroma.Keyword, nil},

				// AI-resistance and annotation keywords
				{`\b(invariant_network|know|assume|believe|intent|narrative|temporal|why_not|chosen|near_miss|satisfies)\b`, chroma.KeywordNamespace, nil},

				// Boolean literals
				{`\b(true|false)\b`, chroma.KeywordConstant, nil},

				// Built-in types (synced with tree-sitter highlights.scm)
				{`\b(Integer|Decimal|Float|Boolean|String|Byte|Character|List|Option|Result|Unit|NonEmpty|Map|Any|Never)\b`, chroma.KeywordType, nil},

				// Operators (order matters — multi-char before single-char)
				{`\|>`, chroma.Operator, nil},
				{`=>`, chroma.Punctuation, nil},
				{`==|!=|<=|>=|&&|\|\||\.\.`, chroma.Operator, nil},
				{`[+\-*/%<>]+`, chroma.Operator, nil},
				{`=`, chroma.Operator, nil},
				{`\.`, chroma.Operator, nil},

				// Constant identifiers (ALL_CAPS)
				{`[A-Z][A-Z0-9_]+\b`, chroma.NameConstant, nil},

				// Type identifiers (PascalCase)
				{`[A-Z][a-zA-Z0-9]*`, chroma.KeywordType, nil},

				// Proof obligation names (identifier followed by colon)
				{`[a-z_][a-z0-9_]+(?=\s*:)`, chroma.NameAttribute, nil},

				// Regular identifiers
				{`[a-z_][a-z0-9_]*`, chroma.Name, nil},

				// Punctuation
				{`[(),;\[\]{}:|]`, chroma.Punctuation, nil},
			},

			// String state — handles escape sequences
			"string": {
				{`\\[nrt\\"{}0]`, chroma.StringEscape, nil},
				{`[^"\\]+`, chroma.String, nil},
				{`"`, chroma.String, chroma.Pop(1)},
			},

			// F-string state — handles escape sequences and interpolation
			"fstring": {
				{`\\[nrt\\"{}0]`, chroma.StringEscape, nil},
				{`\{`, chroma.StringInterpol, chroma.Push("fstring_interp")},
				{`[^"\\{]+`, chroma.StringAffix, nil},
				{`"`, chroma.StringAffix, chroma.Pop(1)},
			},

			// F-string interpolation — lex the expression inside {…}
			"fstring_interp": {
				{`\}`, chroma.StringInterpol, chroma.Pop(1)},
				{`[^}]+`, chroma.Name, nil},
			},
		},
	)
)
