# impl06: Dynamic Self-Modifying Binary Lookup

## Overview

Building a Prove program that can modify its own lookup tables at runtime by:
1. Loading and updating tables via the Database stdlib
2. Handling stale versions (or merging with a custom resolver)
3. Recompiling to a new binary
4. Calling the new binary for lookups

## Prerequisites

- impl01: Async verbs
- impl02: Kind:[Lookup] modifier
- impl03: Database stdlib (storage, versioning, diffs, merges)
- impl04: Process execution (already available via `InputOutput.system`)

## Phase 1: AST File Output

`outputs file(path String, content String) Result<Unit, Error>!` is already available
in the `InputOutput` stdlib — no new implementation needed.

## Phase 2: Database-Backed Updates

Use the Database stdlib to load, modify, and save lookup tables. The Database
handles versioning — stale writes are rejected, and the caller decides how to
recover (retry, merge, or fail).

```prove
inputs update_table(db Database, name String, new_entries List<Entry>)!
from
    table as DatabaseTable = loads(db, name)!
    updated as DatabaseTable = add_entries(table, new_entries)

    match saves(db, updated)
        Ok(_) => ok()
        Err(StaleVersion(_, _)) =>
            // Reload and retry with fresh version
            fresh as DatabaseTable = loads(db, name)!
            retried as DatabaseTable = add_entries(fresh, new_entries)
            saves(db, retried)!
```

For cases needing merge instead of simple retry, provide a resolver:

```prove
inputs update_table_with_merge(db Database, name String, new_entries List<Entry>, resolver (Conflict) Resolution)!
from
    table as DatabaseTable = loads(db, name)!
    updated as DatabaseTable = add_entries(table, new_entries)
    diff as TableDiff = diffs(table, updated)!

    match saves(db, updated)
        Ok(_) => ok()
        Err(StaleVersion(_, _)) =>
            fresh as DatabaseTable = loads(db, name)!
            remote_diff as TableDiff = diffs(table, fresh)!
            merged as MergeResult = merges(table, remote_diff, diff, resolver)!
            match merged
                Ok(merged_table) => saves(db, merged_table)!
                Err(msg) => fail("Merge failed: " + msg)
```

See `future/database-merge-conflicts.md` for conflict types and resolution framework.

## Phase 3: Subprocess Compilation

Spawn `prove build` from running program using `system` from `InputOutput`:

```prove
inputs compile_new_binary()!
from
    result as ProcessResult = system("prove", ["build",
        "--output", "bin/lookup_v" + get_next_version(),
        "console_lookup.prv"
    ])

    match result.exit_code != 0
        True  => fail("Compile failed: " + result.standard_error)
        False => ok()
```

## Phase 4: Subprocess Lookup

Call sibling binary for lookups:

```prove
transforms lookup_word(word String) String
from
    result as ProcessResult = system("bin/lookup_v" + current_version, [word])
    trim(result.standard_output)
```

## Full Example

```prove
module ConsoleLookup
    inputs console() String
    outputs console(Value)

    type Token:[Lookup] is String Integer Decimal where
        First  | "first"  | 1     | 1.0
        Second | "second" | 2     | 2.0

    transforms run(input String) String
    from
        match process_input(input)
            Ok(result) => result
            Err(msg) => msg

    inputs process_input(input String) Result<String, String>
    from
        words as List<String> = split(trim(input), " ")

        if eq(get(words, 0), "Insert")
            return insert_token(words)!

        results as List<String> = []
        for word in words
            result as String = String Token:word
            results = push(results, result)

        join(results, " ")

    inputs insert_token(words List<String>) Result<String, String>
    from
        key as String = trim(get(words, 1))
        val1 as String = trim(get(words, 2))
        val2 as String = trim(get(words, 3))

        db as Database = database("./data")!
        table as DatabaseTable = loads(db, "tokens")!
        updated as DatabaseTable = add_entry(table, key, val1, val2)

        match saves(db, updated)
            Ok(_) => ok()
            Err(StaleVersion(_, _)) =>
                // Simple retry — reload and re-apply
                fresh as DatabaseTable = loads(db, "tokens")!
                retried as DatabaseTable = add_entry(fresh, key, val1, val2)
                saves(db, retried)!

        // Compile new binary
        compile_new_binary()!

        ok("Compiled new lookup table")

    inputs compile_new_binary()!
    from
        result as ProcessResult = system("prove", ["build",
            "--output", "bin/lookup_v" + get_next_version(),
            "console_lookup.prv"
        ])

        match result.exit_code != 0
            True  => fail("Compile failed: " + result.standard_error)
            False => ok()
```

## Key Challenges

1. **Stale version handling**: Database rejects stale writes — caller must retry or merge
2. **Custom merge**: When retry isn't enough, caller provides a resolver function (see `future/database-merge-conflicts.md`)
3. **Version management**: Track which binary version to call
4. **State persistence**: Runtime state lost on binary swap (by design)
5. **Error handling**: What if save fails? What if new binary doesn't compile?
6. **Atomicity**: Save + compile should be atomic or recoverable

## Exit Criteria

- [x] `outputs file()` writes .prv files (already in InputOutput)
- [ ] Database stdlib used for all table modifications
- [ ] Stale version rejection works
- [ ] Custom resolver merge works
- [ ] Subprocess compilation spawns new binary
- [ ] Subprocess lookup works
- [ ] Full self-modifying demo works
- [ ] Tests pass
- [ ] Docs updated: `compiler.md` (runtime modification), `stdlib.md` (Database usage patterns)
