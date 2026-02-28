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

	code := `module InventoryService
  narrative: """
  Products are added to inventory with validated stock levels.
  """

  type Port is Integer where 1..65535

  type Sku is String where matches(r"^[A-Z]{2,4}-[0-9]{4,8}$")

  type Discount is FlatOff(amount Price)
    | PercentOff(rate Percentage)

  MAX_CONNECTIONS as Integer = comptime
      if cfg.target == "embedded"
          16
      else
          1024

validates email(address String)
from
    contains(address, "@")

transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  requires len(items) > 0
  proof
    subtotal: sums the items Price
    apply_discount: deduct discount if > 0
    apply_tax: adds tax if tax > 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)

inputs product_by_sku(db Database, code Sku) Product!
from
    query_one(db, f"SELECT * FROM products WHERE sku = {code}")!

outputs place_order(db Database, order Order, tax TaxRule) Order!
  ensures result.status == Confirmed
  requires fulfillable(order)
  proof
    fulfillment: requires clause guarantees stock sufficiency
from
    total as Price = calculate_total(order.items, FlatOff(0), tax)
    confirmed as Order = Order(order.id, order.items, Confirmed, total)
    insert(db, "orders", confirmed)!
    confirmed

main() Result<Unit, Error>!
from
    cfg as Config = load_config("inventory.yaml")!
    db as Database = connect(cfg.db_url)!
    if !valid sku(product.sku)
        bad_request("invalid SKU format")
    listen(server, port)!`

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
