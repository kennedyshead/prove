# hx — Explorative Hex Editor

A terminal hex editor written in [Prove](https://code.botwork.se/Botwork/prove) with wildcard byte-pattern search.

Inspired by [this Hacker News request](https://news.ycombinator.com/item?id=46345827) for an "explorative hex editor where you can do fuzzy searches, e.g., searching for a header with specific values for certain fields."

## Usage

```
./dist/hx <filename>
```

## Key Bindings

| Key | Action |
|-----|--------|
| Arrow keys | Move cursor (left/right = 1 byte, up/down = 1 row) |
| Page Up/Down | Scroll by one screenful |
| Home / End | Jump to start / end of file |
| `/` | Enter search mode |
| Enter | Execute search |
| Backspace | Delete last search character |
| Escape | Cancel search / quit |
| `n` | Jump to next match |
| `N` | Jump to previous match |
| `q` | Quit |

## Search

Press `/` to enter search mode. Type a pattern using space-separated hex bytes:

- `89 50 4E 47` — find PNG file magic bytes
- `FF D8 FF` — find JPEG magic bytes
- `FF ?? ?? 89` — find `FF`, skip any two bytes, then `89`

`??` matches any single byte (wildcard).

Press Enter to execute. Matches are highlighted in yellow, the current match in green. Use `n`/`N` to jump between matches.

## Layout

```
 hx: photo.png  (1234 bytes)  Matches: 2 [1/2]
 Offset   00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F  ASCII
 00000000 89 50 4E 47 0D 0A 1A 0A  00 00 00 0D 49 48 44 52  .PNG........IHDR
 00000010 00 00 01 00 00 00 01 00  08 06 00 00 00 5C 72 A8  .............r.
 Cursor: 0x00000000
 /89 50 4E 47
```

## Building

```
prove build examples/hx
```

## Architecture

Single-file TUI app (`src/main.prv`) using Prove's event-driven terminal framework:

- **Event types**: `HxEvent` extends `TerminalAppEvent` with `Search`, `NextMatch`, `PrevMatch`, `SearchChar`
- **Rendering**: Recursive functions (`render_rows` -> `render_row` -> `render_cols` -> `render_byte`) since Prove lambdas are single-expression
- **Pattern matching**: Recursive `check_at` with `terminates` clause for the search algorithm
- **File loading**: Lazy-loaded on first `Draw` event (since `state_init` is compile-time)
