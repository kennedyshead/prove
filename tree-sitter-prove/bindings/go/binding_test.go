package tree_sitter_prove_test

import (
	"testing"

	tree_sitter "github.com/smacker/go-tree-sitter"
	"github.com/tree-sitter/tree-sitter-prove"
)

func TestCanLoadGrammar(t *testing.T) {
	language := tree_sitter.NewLanguage(tree_sitter_prove.Language())
	if language == nil {
		t.Errorf("Error loading Prove grammar")
	}
}
