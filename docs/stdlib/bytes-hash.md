---
title: Bytes & Hash - Prove Standard Library
description: Bytes sequence manipulation and Hash cryptographic hashing in the Prove standard library.
keywords: Prove Bytes, Prove Hash, byte array, SHA-256, SHA-512, BLAKE3, HMAC
---

# Bytes & Hash

## Bytes

**Module:** `Bytes` — byte sequence manipulation.

Defines a binary type: `ByteArray` (a sequence of bytes).

### Construction & Slicing

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `bytearray(values List<Integer>) ByteArray` | Create byte array from list of integers |
| `validates` | `bytearray(data ByteArray)` | True if byte array is empty |
| `derives` | `bytearray(data ByteArray, start Integer, length Integer) ByteArray` | Extract a sub-range of bytes |
| `derives` | `bytearray(first ByteArray, second ByteArray) ByteArray` | Concatenate two byte arrays |

### Access

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `at(data ByteArray, index Integer) Integer` | Read byte at index |
| `validates` | `exist(data ByteArray, index Integer)` | True if index is within bounds |

### Hex Encoding

Hex encoding/decoding functions are in the **Parse** module, not Bytes:

| Verb | Signature | Module | Description |
|------|-----------|--------|-------------|
| `creates` | `hexadecimal(data ByteArray) String` | Parse | Encode byte array as hex string |
| `creates` | `hexadecimal(string String) ByteArray` | Parse | Decode hex string to byte array |
| `validates` | `hexadecimal(string String)` | Parse | True if string is valid hex |

```prove
  Bytes creates bytearray at validates exist
  Parse creates hexadecimal validates hexadecimal

creates first_byte_hex(data ByteArray) String
from
    single as ByteArray = Bytes.bytearray(data, 0, 1)
    Parse.hexadecimal(single)
```

---

## Hash

**Module:** `Hash` — cryptographic hashing and verification.

Defines a binary type: `Algorithm` (hash algorithm selector).

No external crypto dependency — all algorithms are implemented in the runtime.

### SHA-256

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `sha256(data ByteArray) ByteArray` | Hash bytes to SHA-256 digest |
| `creates` | `sha256(data String) String` | Hash string to SHA-256 hex string |
| `validates` | `sha256(data ByteArray, expected ByteArray)` | Verify data matches expected SHA-256 hash |

### SHA-512

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `sha512(data ByteArray) ByteArray` | Hash bytes to SHA-512 digest |
| `creates` | `sha512(data String) String` | Hash string to SHA-512 hex string |
| `validates` | `sha512(data ByteArray, expected ByteArray)` | Verify data matches expected SHA-512 hash |

### BLAKE3

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `blake3(data ByteArray) ByteArray` | Hash bytes to BLAKE3 digest |
| `creates` | `blake3(data String) String` | Hash string to BLAKE3 hex string |
| `validates` | `blake3(data ByteArray, expected ByteArray)` | Verify data matches expected BLAKE3 hash |

### HMAC

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `hmac(data ByteArray, key ByteArray) ByteArray` | Create HMAC-SHA256 signature |
| `validates` | `hmac(data ByteArray, key ByteArray, signature ByteArray)` | Verify HMAC-SHA256 signature |

```prove
  Hash creates sha256 hmac validates hmac
  Bytes creates bytearray types ByteArray

creates checksum(content String) String
from
    Hash.sha256(content)
```
