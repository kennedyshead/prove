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
| `reads` | `words(text String) List<String>` | Extract individual words from text |
| `reads` | `sentences(text String) List<String>` | Split text into sentences |

### Stemming

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `stem(word String) String` | Apply the Porter stemming algorithm |
| `transforms` | `root(word String) String` | Strip common suffixes to find the root form |

### String Similarity

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `distance(first String, second String) Integer` | Levenshtein edit distance between two strings |
| `reads` | `similarity(first String, second String) Float` | Normalized similarity (0.0 to 1.0) |

### Phonetic Codes

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `soundex(word String) String` | Soundex phonetic code |
| `reads` | `metaphone(word String) String` | Double Metaphone phonetic code |

### N-Grams

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `ngrams(text String, size Integer) List<String>` | Word-level n-grams |
| `reads` | `bigrams(text String) List<String>` | Word-level bigrams |

### Text Normalization

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `normalize(text String) String` | Lowercase and fold accented characters to ASCII |
| `transforms` | `transliterate(text String) String` | Transliterate accented characters to ASCII preserving case |

### Stopwords and Frequency

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `stopwords() List<String>` | Common English stopwords |
| `transforms` | `without_stopwords(text String) List<String>` | Remove stopwords, return remaining words |
| `reads` | `frequency(text String) Table<String, Integer>` | Word frequency counts |
| `reads` | `keywords(text String, count Integer) List<String>` | Top N most frequent words |

```prove
  Language reads words distance similarity keywords transforms stem normalize

reads find_similar(query String, candidates List<String>) List<String>
from
    filter(candidates, |c| Language.similarity(query, c) > 0.8f)
```
