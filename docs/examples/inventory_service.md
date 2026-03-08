# Inventory Service Example

This example demonstrates a RESTful inventory service, showcasing various features of the Prove programming language.

```prove
module InventoryService
  narrative: """
    Products are added to inventory with validated stock levels.
    Orders consume stock. The system ensures stock never goes negative
    and all monetary calculations use exact decimal arithmetic.
    """

  type Port is Integer:[16 Unsigned] where 1 .. 65535

  type Price is Decimal:[128 Scale:2] where self >= 0

  type Sku is String where r"^[A-Z]{2,4}-[0-9]{4,8}$"

  type Product is
    sku Sku
    name String
    price Price
    stock Quantity

/// Checks whether every item in an order can be fulfilled.
validates fulfillable(order Order)
from
    all(order.items, |item| in_stock(item.product, item.quantity))

/// Places an order: validates stock, calculates total, deducts inventory.
outputs place_order(db Database, order Order, tax TaxRule) Order!
  ensures result.status == Confirmed
  requires fulfillable(order)
from
    total as Price = calculate_total(order.items, None, tax)
    confirmed as Order = Order(order.id, order.items, Confirmed, total)
    insert(db, "orders", confirmed)!
    deduct_stock(all_products(db)!, order.items) |> update_all(db, "products")!
    confirmed

/// Routes incoming HTTP requests.
inputs request(route Route, body String, db Database) Response!
from
    Get("/health") => ok("healthy")
    Get("/products") => all_products(db)! |> encode |> ok
    Post("/orders") => parse_order(body)! |> place_order(db, tax)! |> encode |> created
    _ => not_found()

main()!
from
    cfg as Config = load_config("inventory.yaml")!
    db as Database = connect(cfg.db_url)!
    server as Server = new_server()
    route(server, "/", request)
    listen(server, cfg.port)!
```