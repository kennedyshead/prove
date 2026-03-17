#ifndef PROVE_LANGUAGE_H
#define PROVE_LANGUAGE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_table.h"

/* ── Token kind constants ──────────────────────────────────────── */

#define PROVE_TOKEN_WORD         0
#define PROVE_TOKEN_PUNCTUATION  1
#define PROVE_TOKEN_WHITESPACE   2
#define PROVE_TOKEN_NUMBER       3

/* ── Token type ────────────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *text;
    int64_t       start;
    int64_t       end;
    int64_t       kind;
} Prove_Language_Token;

/* ── Tokenization ──────────────────────────────────────────────── */

Prove_List   *prove_language_words(Prove_String *text);
Prove_List   *prove_language_sentences(Prove_String *text);
Prove_List   *prove_language_tokens(Prove_String *text);

/* ── Stemming / root ───────────────────────────────────────────── */

Prove_String *prove_language_stem(Prove_String *word);
Prove_String *prove_language_root(Prove_String *word);

/* ── Distance / similarity ─────────────────────────────────────── */

int64_t       prove_language_distance(Prove_String *a, Prove_String *b);
double        prove_language_similarity(Prove_String *a, Prove_String *b);

/* ── Phonetic ──────────────────────────────────────────────────── */

Prove_String *prove_language_soundex(Prove_String *word);
Prove_String *prove_language_metaphone(Prove_String *word);

/* ── N-grams ───────────────────────────────────────────────────── */

Prove_List   *prove_language_ngrams(Prove_String *text, int64_t n);
Prove_List   *prove_language_bigrams(Prove_String *text);

/* ── Normalization ─────────────────────────────────────────────── */

Prove_String *prove_language_normalize(Prove_String *text);
Prove_String *prove_language_transliterate(Prove_String *text);

/* ── Stopwords ─────────────────────────────────────────────────── */

Prove_List   *prove_language_stopwords(void);
Prove_List   *prove_language_without_stopwords(Prove_String *text);

/* ── Frequency / keywords ──────────────────────────────────────── */

Prove_Table  *prove_language_frequency(Prove_String *text);
Prove_List   *prove_language_keywords(Prove_String *text, int64_t count);

/* ── Token accessors ───────────────────────────────────────────── */

Prove_String *prove_language_token_text(Prove_Language_Token *t);
int64_t       prove_language_token_start(Prove_Language_Token *t);
int64_t       prove_language_token_end(Prove_Language_Token *t);
int64_t       prove_language_token_kind(Prove_Language_Token *t);

#endif /* PROVE_LANGUAGE_H */
