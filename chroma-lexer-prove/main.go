// Package main demonstrates the Prove lexer
package main

import (
	"fmt"
	"os"

	"github.com/alecthomas/chroma"
	"github.com/alecthomas/chroma/lexers"
	_ "github.com/alecthomas/chroma/lexers"

	"github.com/magnusknutas/prove/chroma-lexer/prove"
)

func main() {
	lexer := lexers.Get("prove")
	if lexer == nil {
		fmt.Println("Prove lexer not found in registry, using prove package")
		lexer = prove.Lexer
	}

	code := `type Port is Integer where 1..65535

validates email(address String)
    from
        contains(address, "@")

transforms area(s Shape) Decimal
    ensures result >= 0
    proof
        area_positive: the area formula always produces positive values
    from
        pi * s.radius * s.radius

inputs create_user(db Database, body String) User!
    requires valid_email(body)
    ensures email(result.email)
    from
        user = decode(body)!
        insert(db, "users", user)!
        user

main() Result!
    know: this function starts the server
    from
        db = connect("postgres://localhost")!
        server = new_server()
        listen(server, 8080)!`

	iterator, err := lexer.Tokenise(nil, code)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("=== Tokens ===")
	for {
		token := iterator()
		if token == chroma.EOF {
			break
		}
		fmt.Printf("%-25s %q\n", token.Type, token.Value)
	}
}
