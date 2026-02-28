# Compiler-Driven Development

## Conversational Compiler Errors

Errors are suggestions, not walls:

```
error[E042]: `port` may exceed type bound
  --> server.prv:12:5
   |
12 |   port as Port = get_integer(config, "port")
   |                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   = note: `get_integer` returns Integer, but Port requires 1..65535

   try: port as Port = clamp(get_integer(config, "port"), 1, 65535)
    or: port as Port = check(get_integer(config, "port"))!
```

## Comptime (Compile-Time Computation)

Inspired by Zig. Arbitrary computation at compile time, including IO. Files read during comptime become build dependencies.

```prove
MAX_CONNECTIONS as Integer = comptime
  match cfg.target
    "embedded" => 16
    _ => 1024

LOOKUP_TABLE as List<Integer:[32 Unsigned]> = comptime
  collect(map(0..256, crc32_step))

ROUTES as List<Route> = comptime
  decode(read("routes.json"))                   // IO allowed — routes.json becomes a build dep
```
