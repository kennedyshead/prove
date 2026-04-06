---
title: Language - Prove Standard Library
description: Natural language processing primitives in the Prove standard library.
keywords: Prove Language, NLP, stemming, edit distance, phonetic codes
---

# Language

**Module:** `Language` — natural language processing primitives.

### Word and Sentence Extraction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `words(text String) List<String>` | Extract individual words from text |
| `creates` | `sentences(text String) List<String>` | Split text into sentences |

### Stemming

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `stem(word String) String` | Apply the Porter stemming algorithm |
| `derives` | `root(word String) String` | Strip common suffixes to find the root form |

### String Similarity

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `distance(first String, second String) Integer` | Levenshtein edit distance between two strings |
| `creates` | `similarity(first String, second String) Float` | Normalized similarity (0.0 to 1.0) |

### Phonetic Codes

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `soundex(word String) String` | Soundex phonetic code |
| `derives` | `metaphone(word String) String` | Double Metaphone phonetic code |

### N-Grams

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `ngrams(text String, size Integer) List<String>` | Word-level n-grams |
| `creates` | `bigrams(text String) List<String>` | Word-level bigrams |

### Text Normalization

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `normalize(text String) String` | Lowercase and fold accented characters to ASCII |
| `derives` | `transliterate(text String) String` | Transliterate accented characters to ASCII preserving case |

### Stopwords and Frequency

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `stopwords() List<String>` | Common English stopwords |
| `creates` | `without_stopwords(text String) List<String>` | Remove stopwords, return remaining words |
| `creates` | `frequency(text String) Table<Value>` | Word frequency counts (keys are words, values are counts) |
| `creates` | `keywords(text String, count Integer) List<String>` | Top N most frequent words |

### Token Accessors

Access properties of `Token` values produced by `Parse.tokens()`. Extract token text via `Types.string(token)`.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `start(token Token) Integer` | Start position in source |
| `creates` | `end(token Token) Integer` | End position in source |
| `creates` | `kind(token Token) Integer` | Kind tag (from the matched rule) |

```prove
  Language creates words distance similarity keywords start end kind derives stem normalize
  Parse types Token

derives find_similar(query String, candidates List<String>) List<String>
from
    filter(candidates, |c| Language.similarity(query, c) > 0.8f)
```
