---
title: Lambdas & Iteration - Prove Programming Language
description: Lambda expressions and functional iteration in Prove — map, filter, reduce, and parallel variants.
keywords: Prove lambdas, iteration, map, filter, reduce, par_map, par_filter
---

# Lambdas & Iteration

Prove has no loops. All iteration is expressed through higher-order functions.

## Lambdas

Lambdas are single-expression anonymous functions, used exclusively as arguments to higher-order functions like `map`, `filter`, and `reduce`. They cannot capture mutable state and must be pure.

**Syntax:** `|params| expression`

```prove
// Filtering with a lambda
active_users as List<User> = filter(users, |u| u.active)

// Mapping with a lambda
names as List<String> = map(users, |u| u.name)

// Reducing with a lambda
total as Decimal = reduce(prices, 0, |acc, p| acc + p.price)

// Using `valid` to pass a validates function as predicate (no lambda needed)
verified_emails as List<String> = filter(emails, valid email)
```

**Constraints:**
- **Single expression only** — no multi-line bodies, no statements. If you need more, write a named function.
- **Must be pure** — no IO effects inside a lambda. Side effects require a named function.
- **Closure capture** — lambdas can capture immutable variables from the enclosing scope. Captured values are passed via a compiler-generated context struct. Mutable captures in parallel lambdas are rejected (E409).
- **Only as arguments** — lambdas cannot be assigned to variables or returned from functions. They exist only at the call site of a higher-order function or a [`Verb`](types.md#function-types-verb) parameter.

Lambdas work with any function parameter typed as `Verb<P1, ..., R>`:

```prove
// Store merge with a lambda resolver
result as MergeResult = Store.merge(base, local, remote, |c| KeepRemote)
```

## Builtin Higher-Order Functions

The following functions are **builtins** — always available, no import needed. They work on any iterable type (`List`, `Array`, and future iterable types like cursors).

| Function | Signature | Description |
|----------|-----------|-------------|
| `map` | `map(items, \|x\| expr) List<T>` | Transform each element, return new list |
| `filter` | `filter(items, \|x\| predicate) List<T>` | Keep elements matching predicate |
| `reduce` | `reduce(items, init, \|acc, x\| expr) T` | Fold elements into accumulator |
| `each` | `each(items, \|x\| expr)` | Run function for each element (side effects) |
| `len` | `len(items) Integer` | Number of elements |
| `clamp` | `clamp(value, min, max) Integer` | Clamp value to range |
| `par_map` | `par_map(items, fn) List<T>` | Parallel map (pure functions only) |
| `par_filter` | `par_filter(items, fn) List<T>` | Parallel filter (pure functions only) |
| `par_reduce` | `par_reduce(items, init, fn) T` | Parallel reduce (pure functions only) |
| `par_each` | `par_each(items, fn)` | Parallel each (pure functions only) |

These are **not** part of any stdlib module — they are compiler builtins with generic type inference. The compiler dispatches to the appropriate C runtime function based on the collection type.

## Iteration — No Loops

Prove has no `for`, `while`, or loop constructs. Iteration is expressed through the builtin HOFs (`map`, `filter`, `reduce`) and recursion. This keeps all data transformations as expressions (they produce values) rather than statements.

```prove
// Instead of: for each user, get their name
names as List<String> = map(users, |u| u.name)

// Instead of: for each item, keep valid ones
valid_items as List<Item> = filter(items, |i| i.quantity > 0)

// Instead of: accumulate a total with a loop
total as Decimal = reduce(order.items, 0, |acc, item| acc + item.price * item.quantity)

// Chaining with pipe operator
result as List<String> = users
    |> filter(|u| u.active)
    |> map(|u| u.email)
    |> filter(valid email)
```

For complex iteration that doesn't fit map/filter/reduce, use recursion with a `transforms` function and a [`terminates`](contracts.md#terminates) annotation.

## Parallel Iteration

`par_map`, `par_filter`, and `par_reduce` are parallel variants of the standard higher-order functions. They use a pthreads thread pool with automatic core detection — no worker count needed.

```prove
// Parallel map — transform each element concurrently
scores as List<Integer> = par_map(documents, compute_score)

// Parallel filter — keep matching elements concurrently
valid as List<Order> = par_filter(orders, validates order)

// Parallel reduce — combine elements concurrently
total as Integer = par_reduce(values, 0, add)
```

**Purity requirement:** the callback must be a named pure function (`transforms`, `validates`, `reads`, `creates`, or `matches`). IO verbs (`inputs`, `outputs`) and async verbs are rejected at compile time.

**Closures:** lambdas with captured variables are supported. The compiler generates a context struct for captured values and passes it through the parallel runtime.

**Ordering:** result ordering is not guaranteed — elements may be placed in any order depending on thread scheduling. Use `map` if ordering must be preserved.

## Why No Loops?

1. **Expressions, not statements** — `map`, `filter`, `reduce` return values; loops are statements that require mutable state
2. **Composable** — chain operations: `users |> filter(...) |> map(...)`
3. **Parallelizable** — the compiler can parallelize `par_map` automatically
4. **Total functions** — no chance of infinite loops when combined with `terminates`

---

## Complete Example: RESTful Server

```prove
module Rest
  type Port is Integer:[16 Unsigned] where 1 .. 65535
  type Route is Get(path String) | Post(path String) | Delete(path String)

  type User is
    id Integer
    name String
    email String

/// Checks whether a string is a valid email address.
validates email(address String)
from
    contains(address, "@") && contains(address, ".")

/// Retrieves all users from the store.
inputs users(db Store) List<User>!
from
    query(db, "SELECT * FROM users")!

/// Creates a new user from a request body.
outputs create(db Store, body String) User!
  ensures email(result.email)
from
    user as User = decode(body)!
    insert(db, "users", user)!
    user

/// Routes incoming HTTP requests.
inputs request(route Route, body String, db Store) Response!
from
    Get("/health") => ok("healthy")
    Get("/users")  => users(db)! |> encode |> ok
    Post("/users") => create(db, body)! |> encode |> created
    _              => not_found()

/// Application entry point — no verb, main is special.
main()!
from
    port as Port = 8080
    db as Store = connect()!
    server as Server = new_server()
    route(server, "/", request)
    listen(server, port)!
```
