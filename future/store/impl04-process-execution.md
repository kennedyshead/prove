# impl04: Process Execution (Already Available)

## Overview

Subprocess execution and result inspection are already provided by the `InputOutput`
stdlib. No new implementation is required — impl06 uses these directly.

## Available Verbs

```prove
import InputOutput

/// Execute a system command
inputs system(command String, arguments List<String>) ProcessResult

/// Exit the process with a given code
outputs system(code Integer)

/// Validate a command exists in PATH
validates system(command String)
```

## ProcessResult Fields

```
exit_code        Integer   — process exit code (0 = success)
standard_output  String    — captured stdout
standard_error   String    — captured stderr
```

## Usage in impl06

```prove
result as ProcessResult = system("prove", ["build",
    "--output", "bin/lookup_v" + get_next_version(),
    "console_lookup.prv"
])

match result.exit_code != 0
    True  => fail("Compile failed: " + result.standard_error)
    False => ok()
```

## Note on impl06 Example

The impl06 example uses `exec` and `.code`/`.stdout`/`.stderr` — these are aliases
that do not exist. Use `system` and `.exit_code`/`.standard_output`/`.standard_error`.

## Exit Criteria

- [x] `system` verb implemented (InputOutput)
- [x] `ProcessResult` type available with `exit_code`, `standard_output`, `standard_error`
- [x] `outputs file()` available for writing `.prv` source (InputOutput)
- [x] impl06 example updated to use correct names
