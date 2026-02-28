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
				// Annotation keywords (ensures, requires, proof, etc.)
				{`\b(ensures|requires|proof)\b`, chroma.KeywordNamespace, nil},
				{`\b(module|type|with|use|transforms|inputs|outputs|validates|types|main|from|if|else|match|where|comptime)\b`, chroma.Keyword, nil},
				// More annotation keywords
				{`\b(invariant_network|know|assume|believe|intent|narrative|temporal|why_not|chosen|near_miss|satisfies)\b`, chroma.KeywordNamespace, nil},
				{`\b(true|false)\b`, chroma.KeywordConstant, nil},
				{`\b(Integer|String|Decimal|Boolean|List|Option|Result|Any|Never)\b`, chroma.KeywordType, nil},
				{`[A-Z][A-Za-z0-9_]*`, chroma.KeywordType, nil},
				{`\|>`, chroma.Operator, nil},
				{`=>`, chroma.Operator, nil},
				{`==|!=|<=|>=|&&|\|\||\.\.`, chroma.Operator, nil},
				{`[+\-*/%=<>!&|^~!]+`, chroma.Operator, nil},
				{`\.`, chroma.Operator, nil},
				// Proof obligation names (e.g., "email_valid:" in proof blocks)
				{`[a-z_][a-z0-9_]+(?=\s*:)`, chroma.NameAttribute, nil},
				{`[a-z_][a-z0-9_]*`, chroma.Name, nil},
				{`[(),;\[\]{}]`, chroma.Punctuation, nil},
				{`:`, chroma.Punctuation, nil},
			},
		},
	)
)
