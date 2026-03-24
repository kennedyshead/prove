#include "prove_language.h"
#include "prove_text.h"
#include "prove_option.h"
#include <ctype.h>
#include <math.h>
#include <string.h>

/* ═══════════════════════════════════════════════════════════════════
   Internal tokenizer — UTF-8 aware character classification
   ═══════════════════════════════════════════════════════════════════ */

typedef enum {
    CHARCLASS_ALPHA,
    CHARCLASS_DIGIT,
    CHARCLASS_PUNCT,
    CHARCLASS_SPACE,
    CHARCLASS_OTHER
} CharClass;

static CharClass _classify_byte(unsigned char c) {
    if (isalpha(c) || (c & 0x80))  return CHARCLASS_ALPHA;  /* ASCII alpha or UTF-8 continuation */
    if (isdigit(c))                 return CHARCLASS_DIGIT;
    if (isspace(c))                 return CHARCLASS_SPACE;
    if (ispunct(c))                 return CHARCLASS_PUNCT;
    return CHARCLASS_OTHER;
}

static int _token_kind_from_class(CharClass cc) {
    switch (cc) {
        case CHARCLASS_ALPHA: return PROVE_LANGUAGE_TOKEN_WORD;
        case CHARCLASS_DIGIT: return PROVE_LANGUAGE_TOKEN_NUMBER;
        case CHARCLASS_PUNCT: return PROVE_LANGUAGE_TOKEN_PUNCTUATION;
        case CHARCLASS_SPACE: return PROVE_LANGUAGE_TOKEN_WHITESPACE;
        default:              return PROVE_LANGUAGE_TOKEN_WORD;
    }
}

/* Tokenize into a list of Prove_Token* (generic parse tokens).
   Consecutive characters of the same class form one token. */
static Prove_List *_tokenize(const char *src, int64_t len) {
    Prove_List *result = prove_list_new(16);
    int64_t i = 0;

    while (i < len) {
        CharClass cc = _classify_byte((unsigned char)src[i]);
        int64_t start = i;
        i++;
        while (i < len && _classify_byte((unsigned char)src[i]) == cc) {
            i++;
        }

        Prove_Token *tok =
            (Prove_Token *)prove_alloc(sizeof(Prove_Token));
        tok->text  = prove_string_new(src + start, i - start);
        tok->start = start;
        tok->end   = i;
        tok->kind  = _token_kind_from_class(cc);
        prove_list_push(result, tok);
    }

    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   words() — extract word and number tokens
   ═══════════════════════════════════════════════════════════════════ */

Prove_List *prove_language_words(Prove_String *text) {
    Prove_List *tokens = _tokenize(text->data, text->length);
    Prove_List *result = prove_list_new(tokens->length / 2 + 1);

    for (int64_t i = 0; i < tokens->length; i++) {
        Prove_Token *t = (Prove_Token *)prove_list_get(tokens, i);
        if (t->kind == PROVE_LANGUAGE_TOKEN_WORD || t->kind == PROVE_LANGUAGE_TOKEN_NUMBER) {
            prove_list_push(result, t->text);
        }
    }

    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   sentences() — heuristic sentence splitting
   ═══════════════════════════════════════════════════════════════════ */

static const char *_ABBREVIATIONS[] = {
    "Mr", "Mrs", "Ms", "Dr", "Prof", "Sr", "Jr", "St",
    "Ave", "Blvd", "Dept", "Est", "Fig", "Gen", "Gov",
    "Inc", "Ltd", "Corp", "Rev", "Sgt", "Lt", "Col",
    "Capt", "Cmdr", "Adm", "vs", "etc", "al", "approx",
    NULL
};

static bool _is_abbreviation(const char *src, int64_t dot_pos) {
    /* Walk backwards from dot to find the word start. */
    int64_t ws = dot_pos;
    while (ws > 0 && isalpha((unsigned char)src[ws - 1])) ws--;
    int64_t wlen = dot_pos - ws;
    if (wlen == 0 || wlen > 10) return false;

    for (int k = 0; _ABBREVIATIONS[k]; k++) {
        const char *ab = _ABBREVIATIONS[k];
        int64_t alen = (int64_t)strlen(ab);
        if (alen == wlen && strncmp(src + ws, ab, (size_t)wlen) == 0) {
            return true;
        }
    }

    /* Single uppercase letter (initials like "U.S.") */
    if (wlen == 1 && isupper((unsigned char)src[ws])) return true;

    return false;
}

Prove_List *prove_language_sentences(Prove_String *text) {
    const char *src = text->data;
    int64_t len = text->length;
    Prove_List *result = prove_list_new(4);
    int64_t start = 0;

    /* Skip leading whitespace */
    while (start < len && isspace((unsigned char)src[start])) start++;

    for (int64_t i = start; i < len; i++) {
        char c = src[i];
        if (c != '.' && c != '!' && c != '?') continue;

        /* Check abbreviation for '.' */
        if (c == '.' && _is_abbreviation(src, i)) continue;

        /* Consume trailing sentence-ending punctuation (e.g. "..." or "?!") */
        int64_t end = i + 1;
        while (end < len && (src[end] == '.' || src[end] == '!' || src[end] == '?')) end++;

        /* The sentence boundary is at 'end'. Require that what follows is
           whitespace+uppercase, or end-of-string. */
        int64_t next = end;
        while (next < len && isspace((unsigned char)src[next])) next++;

        if (next >= len || isupper((unsigned char)src[next])) {
            /* Emit sentence from start..end, trimmed */
            int64_t se = end;
            while (se > start && isspace((unsigned char)src[se - 1])) se--;
            if (se > start) {
                prove_list_push(result, prove_string_new(src + start, se - start));
            }
            start = next;
            i = next - 1; /* will be incremented by loop */
        }
    }

    /* Remainder as last sentence */
    if (start < len) {
        int64_t se = len;
        while (se > start && isspace((unsigned char)src[se - 1])) se--;
        if (se > start) {
            prove_list_push(result, prove_string_new(src + start, se - start));
        }
    }

    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   stem() — Porter stemmer (simplified)
   ═══════════════════════════════════════════════════════════════════ */

/* Measure: count VC sequences in a word (Porter's "m" value).
   Consonant = not aeiou (y is consonant at start, else depends on context). */

static bool _is_vowel(const char *w, int64_t i) {
    switch (w[i]) {
        case 'a': case 'e': case 'i': case 'o': case 'u':
            return true;
        case 'y':
            return i > 0;
        default:
            return false;
    }
}

static int _measure(const char *w, int64_t len) {
    int m = 0;
    int64_t i = 0;
    /* Skip initial consonants */
    while (i < len && !_is_vowel(w, i)) i++;
    while (i < len) {
        /* Skip vowels */
        while (i < len && _is_vowel(w, i)) i++;
        if (i >= len) break;
        m++;
        /* Skip consonants */
        while (i < len && !_is_vowel(w, i)) i++;
    }
    return m;
}

static bool _has_vowel(const char *w, int64_t len) {
    for (int64_t i = 0; i < len; i++) {
        if (_is_vowel(w, i)) return true;
    }
    return false;
}

static bool _ends_double_consonant(const char *w, int64_t len) {
    if (len < 2) return false;
    return w[len - 1] == w[len - 2] && !_is_vowel(w, len - 1);
}

static bool _ends_cvc(const char *w, int64_t len) {
    if (len < 3) return false;
    if (_is_vowel(w, len - 1) || !_is_vowel(w, len - 2) || _is_vowel(w, len - 3))
        return false;
    char c = w[len - 1];
    return c != 'w' && c != 'x' && c != 'y';
}

/* Try to replace suffix `old` with `rep` if measure of stem >= min_m.
   Returns true if replacement was done. buf must be large enough. */
static bool _replace_suffix(char *buf, int64_t *len,
                            const char *old, int64_t olen,
                            const char *rep, int64_t rlen,
                            int min_m) {
    if (*len < olen) return false;
    if (memcmp(buf + *len - olen, old, (size_t)olen) != 0) return false;
    int64_t stem_len = *len - olen;
    if (min_m >= 0 && _measure(buf, stem_len) < min_m) return false;
    memcpy(buf + stem_len, rep, (size_t)rlen);
    *len = stem_len + rlen;
    buf[*len] = '\0';
    return true;
}

Prove_String *prove_language_stem(Prove_String *word) {
    if (word->length <= 2) {
        return prove_string_new(word->data, word->length);
    }

    /* Work in a mutable lowercase copy */
    int64_t len = word->length;
    if (len > 256) len = 256; /* cap for safety */
    char buf[260];
    for (int64_t i = 0; i < len; i++) {
        buf[i] = (char)tolower((unsigned char)word->data[i]);
    }
    buf[len] = '\0';

    /* Step 1a */
    if (!_replace_suffix(buf, &len, "sses", 4, "ss", 2, -1)) {
        if (!_replace_suffix(buf, &len, "ies", 3, "i", 1, -1)) {
            if (len >= 2 && buf[len - 1] == 's' && buf[len - 2] != 's') {
                len--;
                buf[len] = '\0';
            }
        }
    }

    /* Step 1b */
    bool step1b_extra = false;
    if (_replace_suffix(buf, &len, "eed", 3, "ee", 2, 0)) {
        /* done */
    } else {
        int64_t old_len = len;
        bool did_ed = _replace_suffix(buf, &len, "ed", 2, "", 0, -1);
        if (did_ed && !_has_vowel(buf, len)) {
            /* restore */
            len = old_len;
            memcpy(buf, word->data, (size_t)len);
            for (int64_t i = 0; i < len; i++) buf[i] = (char)tolower((unsigned char)buf[i]);
            buf[len] = '\0';
            did_ed = false;
        }
        bool did_ing = false;
        if (!did_ed) {
            old_len = len;
            did_ing = _replace_suffix(buf, &len, "ing", 3, "", 0, -1);
            if (did_ing && !_has_vowel(buf, len)) {
                len = old_len;
                for (int64_t i = 0; i < len; i++) buf[i] = (char)tolower((unsigned char)word->data[i]);
                buf[len] = '\0';
                did_ing = false;
            }
        }
        if (did_ed || did_ing) step1b_extra = true;
    }

    if (step1b_extra) {
        if (_ends_double_consonant(buf, len) && buf[len - 1] != 'l'
                && buf[len - 1] != 's' && buf[len - 1] != 'z') {
            len--;
            buf[len] = '\0';
        } else if (_measure(buf, len) == 1 && _ends_cvc(buf, len)) {
            buf[len] = 'e';
            len++;
            buf[len] = '\0';
        }
    }

    /* Step 1c */
    if (len > 1 && buf[len - 1] == 'y' && _has_vowel(buf, len - 1)) {
        buf[len - 1] = 'i';
    }

    /* Step 2 */
    if (len > 7 && _measure(buf, len - 7) > 0) {
        _replace_suffix(buf, &len, "ational", 7, "ate", 3, 0) ||
        _replace_suffix(buf, &len, "tional", 6, "tion", 4, 0) ||
        _replace_suffix(buf, &len, "ization", 7, "ize", 3, 0);
    }
    if (len > 5) {
        _replace_suffix(buf, &len, "enci", 4, "ence", 4, 0) ||
        _replace_suffix(buf, &len, "anci", 4, "ance", 4, 0) ||
        _replace_suffix(buf, &len, "izer", 4, "ize", 3, 0) ||
        _replace_suffix(buf, &len, "abli", 4, "able", 4, 0) ||
        _replace_suffix(buf, &len, "alli", 4, "al", 2, 0) ||
        _replace_suffix(buf, &len, "entli", 5, "ent", 3, 0) ||
        _replace_suffix(buf, &len, "eli", 3, "e", 1, 0) ||
        _replace_suffix(buf, &len, "ousli", 5, "ous", 3, 0) ||
        _replace_suffix(buf, &len, "ation", 5, "ate", 3, 0) ||
        _replace_suffix(buf, &len, "ator", 4, "ate", 3, 0) ||
        _replace_suffix(buf, &len, "alism", 5, "al", 2, 0) ||
        _replace_suffix(buf, &len, "iveness", 7, "ive", 3, 0) ||
        _replace_suffix(buf, &len, "fulness", 7, "ful", 3, 0) ||
        _replace_suffix(buf, &len, "ousnes", 6, "ous", 3, 0) ||
        _replace_suffix(buf, &len, "aliti", 5, "al", 2, 0) ||
        _replace_suffix(buf, &len, "iviti", 5, "ive", 3, 0) ||
        _replace_suffix(buf, &len, "biliti", 6, "ble", 3, 0);
    }

    /* Step 3 */
    _replace_suffix(buf, &len, "icate", 5, "ic", 2, 0) ||
    _replace_suffix(buf, &len, "ative", 5, "", 0, 0) ||
    _replace_suffix(buf, &len, "alize", 5, "al", 2, 0) ||
    _replace_suffix(buf, &len, "iciti", 5, "ic", 2, 0) ||
    _replace_suffix(buf, &len, "ical", 4, "ic", 2, 0) ||
    _replace_suffix(buf, &len, "ful", 3, "", 0, 0) ||
    _replace_suffix(buf, &len, "ness", 4, "", 0, 0);

    /* Step 4 */
    _replace_suffix(buf, &len, "al", 2, "", 0, 1) ||
    _replace_suffix(buf, &len, "ance", 4, "", 0, 1) ||
    _replace_suffix(buf, &len, "ence", 4, "", 0, 1) ||
    _replace_suffix(buf, &len, "er", 2, "", 0, 1) ||
    _replace_suffix(buf, &len, "ic", 2, "", 0, 1) ||
    _replace_suffix(buf, &len, "able", 4, "", 0, 1) ||
    _replace_suffix(buf, &len, "ible", 4, "", 0, 1) ||
    _replace_suffix(buf, &len, "ant", 3, "", 0, 1) ||
    _replace_suffix(buf, &len, "ement", 5, "", 0, 1) ||
    _replace_suffix(buf, &len, "ment", 4, "", 0, 1) ||
    _replace_suffix(buf, &len, "ent", 3, "", 0, 1) ||
    (len >= 3 && (buf[len - 1] == 's' || buf[len - 1] == 't') &&
        _replace_suffix(buf, &len, "ion", 3, "", 0, 1)) ||
    _replace_suffix(buf, &len, "ou", 2, "", 0, 1) ||
    _replace_suffix(buf, &len, "ism", 3, "", 0, 1) ||
    _replace_suffix(buf, &len, "ate", 3, "", 0, 1) ||
    _replace_suffix(buf, &len, "iti", 3, "", 0, 1) ||
    _replace_suffix(buf, &len, "ous", 3, "", 0, 1) ||
    _replace_suffix(buf, &len, "ive", 3, "", 0, 1) ||
    _replace_suffix(buf, &len, "ize", 3, "", 0, 1);

    /* Step 5a */
    if (buf[len - 1] == 'e') {
        int m = _measure(buf, len - 1);
        if (m > 1 || (m == 1 && !_ends_cvc(buf, len - 1))) {
            len--;
            buf[len] = '\0';
        }
    }

    /* Step 5b */
    if (_measure(buf, len) > 1 && _ends_double_consonant(buf, len) && buf[len - 1] == 'l') {
        len--;
        buf[len] = '\0';
    }

    return prove_string_new(buf, len);
}

/* ═══════════════════════════════════════════════════════════════════
   root() — simple suffix stripping
   ═══════════════════════════════════════════════════════════════════ */

Prove_String *prove_language_root(Prove_String *word) {
    int64_t len = word->length;
    if (len > 256) len = 256;
    char buf[260];
    memcpy(buf, word->data, (size_t)len);
    buf[len] = '\0';

    /* Try suffixes longest first */
    _replace_suffix(buf, &len, "ation", 5, "", 0, -1) ||
    _replace_suffix(buf, &len, "tion", 4, "", 0, -1) ||
    _replace_suffix(buf, &len, "ments", 5, "", 0, -1) ||
    _replace_suffix(buf, &len, "ment", 4, "", 0, -1) ||
    _replace_suffix(buf, &len, "ness", 4, "", 0, -1) ||
    _replace_suffix(buf, &len, "ing", 3, "", 0, -1) ||
    _replace_suffix(buf, &len, "ies", 3, "y", 1, -1) ||
    _replace_suffix(buf, &len, "es", 2, "", 0, -1) ||
    _replace_suffix(buf, &len, "ed", 2, "", 0, -1) ||
    (len > 1 && buf[len - 1] == 's' && buf[len - 2] != 's' &&
        (_replace_suffix(buf, &len, "s", 1, "", 0, -1)));

    return prove_string_new(buf, len);
}

/* ═══════════════════════════════════════════════════════════════════
   distance() — Levenshtein edit distance
   ═══════════════════════════════════════════════════════════════════ */

int64_t prove_language_distance(Prove_String *a, Prove_String *b) {
    int64_t m = a->length;
    int64_t n = b->length;

    if (m == 0) return n;
    if (n == 0) return m;

    /* Ensure n <= m for single-row optimization */
    const char *sa = a->data;
    const char *sb = b->data;
    if (n > m) {
        int64_t tmp = m; m = n; n = tmp;
        const char *ts = sa; sa = sb; sb = ts;
    }

    /* Allocate single row */
    int64_t *row = (int64_t *)calloc((size_t)(n + 1), sizeof(int64_t));
    if (!row) prove_panic("out of memory");
    for (int64_t j = 0; j <= n; j++) row[j] = j;

    for (int64_t i = 1; i <= m; i++) {
        int64_t prev = row[0];
        row[0] = i;
        for (int64_t j = 1; j <= n; j++) {
            int64_t cost = (sa[i - 1] == sb[j - 1]) ? 0 : 1;
            int64_t del = row[j] + 1;
            int64_t ins = row[j - 1] + 1;
            int64_t sub = prev + cost;
            prev = row[j];
            int64_t mn = del < ins ? del : ins;
            row[j] = mn < sub ? mn : sub;
        }
    }

    int64_t result = row[n];
    free(row);
    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   similarity() — normalized edit similarity
   ═══════════════════════════════════════════════════════════════════ */

double prove_language_similarity(Prove_String *a, Prove_String *b) {
    if (a->length == 0 && b->length == 0) return 1.0;
    int64_t dist = prove_language_distance(a, b);
    int64_t maxlen = a->length > b->length ? a->length : b->length;
    return 1.0 - ((double)dist / (double)maxlen);
}

/* ═══════════════════════════════════════════════════════════════════
   soundex() — classic 4-character American Soundex
   ═══════════════════════════════════════════════════════════════════ */

static const char _SOUNDEX_TABLE[26] = {
    /* A  B  C  D  E  F  G  H  I  J  K  L  M */
       0,'1','2','3', 0,'1','2', 0, 0,'2','2','4','5',
    /* N  O  P  Q  R  S  T  U  V  W  X  Y  Z */
      '5', 0,'1','2','6','2','3', 0,'1', 0,'2', 0,'2'
};

Prove_String *prove_language_soundex(Prove_String *word) {
    if (word->length == 0) {
        return prove_string_new("0000", 4);
    }

    char result[5] = "0000";
    const char *src = word->data;
    int64_t len = word->length;

    /* First character uppercase */
    result[0] = (char)toupper((unsigned char)src[0]);

    char last_code = 0;
    int idx = toupper((unsigned char)src[0]) - 'A';
    if (idx >= 0 && idx < 26) last_code = _SOUNDEX_TABLE[idx];

    int ri = 1;
    for (int64_t i = 1; i < len && ri < 4; i++) {
        char c = (char)toupper((unsigned char)src[i]);
        if (c < 'A' || c > 'Z') continue;
        char code = _SOUNDEX_TABLE[c - 'A'];
        if (code != 0 && code != last_code) {
            result[ri++] = code;
        }
        /* Only update last_code for letters with a real code.
           H and W (code 0) must not break adjacent-code merging. */
        if (code != 0) last_code = code;
    }

    return prove_string_new(result, 4);
}

/* ═══════════════════════════════════════════════════════════════════
   metaphone() — Double Metaphone (primary code only)
   ═══════════════════════════════════════════════════════════════════ */

/* Helper: check if position is at a given substring */
static bool _at(const char *s, int64_t len, int64_t pos, const char *sub) {
    int64_t slen = (int64_t)strlen(sub);
    if (pos < 0 || pos + slen > len) return false;
    return memcmp(s + pos, sub, (size_t)slen) == 0;
}

static bool _is_vowel_ch(char c) {
    switch (c) {
        case 'A': case 'E': case 'I': case 'O': case 'U': case 'Y':
            return true;
        default:
            return false;
    }
}

/* Slavo-Germanic check */
static bool _slavo_germanic(const char *s, int64_t len) {
    if (memchr(s, 'W', (size_t)len) || memchr(s, 'K', (size_t)len)) return true;
    /* Check for CZ or WITZ */
    for (int64_t i = 0; i + 1 < len; i++) {
        if (s[i] == 'C' && s[i + 1] == 'Z') return true;
    }
    return false;
}

Prove_String *prove_language_metaphone(Prove_String *word) {
    if (word->length == 0) {
        return prove_string_new("", 0);
    }

    /* Uppercase working copy */
    int64_t len = word->length;
    if (len > 256) len = 256;
    char w[260];
    for (int64_t i = 0; i < len; i++) {
        w[i] = (char)toupper((unsigned char)word->data[i]);
    }
    w[len] = '\0';

    char primary[8];
    int pi = 0;
    int64_t pos = 0;
    bool is_slavo = _slavo_germanic(w, len);

    #define EMIT(c) do { if (pi < 6) primary[pi++] = (c); } while(0)

    /* Skip initial silent letters */
    if (_at(w, len, 0, "GN") || _at(w, len, 0, "KN") ||
        _at(w, len, 0, "PN") || _at(w, len, 0, "AE") ||
        _at(w, len, 0, "WR")) {
        pos = 1;
    }

    /* Special: initial X -> S */
    if (w[0] == 'X') {
        EMIT('S');
        pos = 1;
    }

    while (pos < len && pi < 6) {
        char c = w[pos];

        /* Skip vowels unless at start */
        if (_is_vowel_ch(c)) {
            if (pos == 0) EMIT('A');
            pos++;
            continue;
        }

        switch (c) {
        case 'B':
            EMIT('P');
            pos += (pos + 1 < len && w[pos + 1] == 'B') ? 2 : 1;
            break;

        case 'C':
            if (pos > 1 && !_is_vowel_ch(w[pos - 2]) &&
                _at(w, len, pos - 1, "ACH") &&
                (pos + 2 >= len || w[pos + 2] != 'I')) {
                EMIT('K'); pos += 2;
            } else if (pos == 0 && _at(w, len, pos, "CAESAR")) {
                EMIT('S'); pos += 2;
            } else if (_at(w, len, pos, "CH")) {
                EMIT('X'); pos += 2;
            } else if (_at(w, len, pos, "CI") || _at(w, len, pos, "CE") || _at(w, len, pos, "CY")) {
                EMIT('S'); pos += 2;
            } else {
                EMIT('K');
                pos += (pos + 1 < len && (w[pos + 1] == 'C' || w[pos + 1] == 'K' || w[pos + 1] == 'Q')) ? 2 : 1;
            }
            break;

        case 'D':
            if (_at(w, len, pos, "DG") && pos + 2 < len &&
                (w[pos + 2] == 'I' || w[pos + 2] == 'E' || w[pos + 2] == 'Y')) {
                EMIT('J'); pos += 3;
            } else {
                EMIT('T');
                pos += (pos + 1 < len && w[pos + 1] == 'D') ? 2 : 1;
            }
            break;

        case 'F':
            EMIT('F');
            pos += (pos + 1 < len && w[pos + 1] == 'F') ? 2 : 1;
            break;

        case 'G':
            if (pos + 1 < len && w[pos + 1] == 'H') {
                if (pos > 0 && !_is_vowel_ch(w[pos - 1])) {
                    EMIT('K'); pos += 2;
                } else if (pos == 0) {
                    EMIT('K'); pos += 2;
                } else {
                    pos += 2;
                }
            } else if (pos + 1 < len && w[pos + 1] == 'N') {
                pos += (pos + 2 < len && w[pos + 2] == 'N') ? 3 : 2;
            } else if (_at(w, len, pos, "GI") || _at(w, len, pos, "GE") || _at(w, len, pos, "GY")) {
                EMIT('K'); pos += 2;
            } else {
                EMIT('K');
                pos += (pos + 1 < len && w[pos + 1] == 'G') ? 2 : 1;
            }
            break;

        case 'H':
            if (pos + 1 < len && _is_vowel_ch(w[pos + 1]) &&
                (pos == 0 || _is_vowel_ch(w[pos - 1]))) {
                EMIT('H');
            }
            pos++;
            break;

        case 'J':
            if (_at(w, len, pos, "JOSE") || _at(w, len, 0, "SAN ")) {
                EMIT('H');
            } else {
                EMIT('J');
            }
            pos += (pos + 1 < len && w[pos + 1] == 'J') ? 2 : 1;
            break;

        case 'K':
            EMIT('K');
            pos += (pos > 0 && w[pos - 1] == 'C') ? 1 :
                   (pos + 1 < len && w[pos + 1] == 'K') ? 2 : 1;
            break;

        case 'L':
            EMIT('L');
            pos += (pos + 1 < len && w[pos + 1] == 'L') ? 2 : 1;
            break;

        case 'M':
            EMIT('M');
            pos += (pos + 1 < len && w[pos + 1] == 'M') ? 2 : 1;
            break;

        case 'N':
            EMIT('N');
            pos += (pos + 1 < len && w[pos + 1] == 'N') ? 2 : 1;
            break;

        case 'P':
            if (pos + 1 < len && w[pos + 1] == 'H') {
                EMIT('F'); pos += 2;
            } else {
                EMIT('P');
                pos += (pos + 1 < len && (w[pos + 1] == 'P' || w[pos + 1] == 'B')) ? 2 : 1;
            }
            break;

        case 'Q':
            EMIT('K');
            pos += (pos + 1 < len && w[pos + 1] == 'Q') ? 2 : 1;
            break;

        case 'R':
            EMIT('R');
            pos += (pos + 1 < len && w[pos + 1] == 'R') ? 2 : 1;
            break;

        case 'S':
            if (_at(w, len, pos, "SH")) {
                EMIT('X'); pos += 2;
            } else if (_at(w, len, pos, "SI") && pos + 2 < len &&
                       (w[pos + 2] == 'O' || w[pos + 2] == 'A')) {
                EMIT('X'); pos += 3;
            } else if (_at(w, len, pos, "SC") && pos + 2 < len &&
                       (w[pos + 2] == 'E' || w[pos + 2] == 'I' || w[pos + 2] == 'Y')) {
                EMIT('S'); pos += 3;
            } else if (_at(w, len, pos, "SCH")) {
                EMIT('S'); EMIT('K'); pos += 3;
            } else {
                EMIT('S');
                pos += (pos + 1 < len && (w[pos + 1] == 'S' || w[pos + 1] == 'Z')) ? 2 : 1;
            }
            break;

        case 'T':
            if (_at(w, len, pos, "TH") || _at(w, len, pos, "TTH")) {
                EMIT('0'); /* theta */
                pos += _at(w, len, pos, "TTH") ? 3 : 2;
            } else if (_at(w, len, pos, "TION") || _at(w, len, pos, "TIA") || _at(w, len, pos, "TCH")) {
                EMIT('X');
                pos += _at(w, len, pos, "TCH") ? 3 : 2;
            } else {
                EMIT('T');
                pos += (pos + 1 < len && (w[pos + 1] == 'T' || w[pos + 1] == 'D')) ? 2 : 1;
            }
            break;

        case 'V':
            EMIT('F');
            pos += (pos + 1 < len && w[pos + 1] == 'V') ? 2 : 1;
            break;

        case 'W':
            if (pos + 1 < len && _is_vowel_ch(w[pos + 1])) {
                EMIT('A');
            }
            pos++;
            break;

        case 'X':
            if (!(pos == len - 1 &&
                  (_at(w, len, pos - 3, "IAU") || _at(w, len, pos - 2, "EAU")))) {
                EMIT('K'); EMIT('S');
            }
            pos += (pos + 1 < len && (w[pos + 1] == 'C' || w[pos + 1] == 'X')) ? 2 : 1;
            break;

        case 'Z':
            if (pos + 1 < len && w[pos + 1] == 'H') {
                EMIT('J'); pos += 2;
            } else if (_at(w, len, pos + 1, "ZO") || _at(w, len, pos + 1, "ZI") || _at(w, len, pos + 1, "ZA")) {
                EMIT('S'); EMIT('T');
                pos += 2;
            } else {
                EMIT(is_slavo ? 'S' : 'T');
                EMIT('S');
                pos += (pos + 1 < len && w[pos + 1] == 'Z') ? 2 : 1;
            }
            break;

        default:
            pos++;
            break;
        }
    }

    #undef EMIT

    primary[pi] = '\0';
    return prove_string_new(primary, pi);
}

/* ═══════════════════════════════════════════════════════════════════
   ngrams() / bigrams()
   ═══════════════════════════════════════════════════════════════════ */

Prove_List *prove_language_ngrams(Prove_String *text, int64_t n) {
    Prove_List *word_list = prove_language_words(text);
    int64_t wcount = word_list->length;
    Prove_List *result = prove_list_new(wcount > n ? wcount - n + 1 : 1);

    if (n <= 0 || wcount < n) return result;

    for (int64_t i = 0; i <= wcount - n; i++) {
        /* Join n words with spaces using a builder (one allocation) */
        Prove_Builder *b = prove_text_builder();
        Prove_String *first = (Prove_String *)prove_list_get(word_list, i);
        b = prove_text_write(b, first);
        for (int64_t j = 1; j < n; j++) {
            b = prove_text_write_char(b, ' ');
            Prove_String *next = (Prove_String *)prove_list_get(word_list, i + j);
            b = prove_text_write(b, next);
        }
        Prove_String *combined = prove_text_build(b);
        free(b);
        prove_list_push(result, combined);
    }

    return result;
}

Prove_List *prove_language_bigrams(Prove_String *text) {
    return prove_language_ngrams(text, 2);
}

/* ═══════════════════════════════════════════════════════════════════
   normalize() — lowercase + accent folding
   ═══════════════════════════════════════════════════════════════════ */

/* Latin Extended accent folding table.
   Maps 2-byte UTF-8 sequences (0xC3 0x80..0xBF and 0xC4..0xC5 range)
   to ASCII equivalents. */

typedef struct { unsigned char b0; unsigned char b1; char ascii; } AccentEntry;

static const AccentEntry _ACCENT_TABLE[] = {
    /* À-Å */  {0xC3,0x80,'a'}, {0xC3,0x81,'a'}, {0xC3,0x82,'a'}, {0xC3,0x83,'a'}, {0xC3,0x84,'a'}, {0xC3,0x85,'a'},
    /* Æ */    {0xC3,0x86,'a'},
    /* Ç */    {0xC3,0x87,'c'},
    /* È-Ë */ {0xC3,0x88,'e'}, {0xC3,0x89,'e'}, {0xC3,0x8A,'e'}, {0xC3,0x8B,'e'},
    /* Ì-Ï */ {0xC3,0x8C,'i'}, {0xC3,0x8D,'i'}, {0xC3,0x8E,'i'}, {0xC3,0x8F,'i'},
    /* Ð */    {0xC3,0x90,'d'},
    /* Ñ */    {0xC3,0x91,'n'},
    /* Ò-Ö */ {0xC3,0x92,'o'}, {0xC3,0x93,'o'}, {0xC3,0x94,'o'}, {0xC3,0x95,'o'}, {0xC3,0x96,'o'},
    /* Ø */    {0xC3,0x98,'o'},
    /* Ù-Ü */ {0xC3,0x99,'u'}, {0xC3,0x9A,'u'}, {0xC3,0x9B,'u'}, {0xC3,0x9C,'u'},
    /* Ý */    {0xC3,0x9D,'y'},
    /* ß */    {0xC3,0x9F,'s'},
    /* à-å */  {0xC3,0xA0,'a'}, {0xC3,0xA1,'a'}, {0xC3,0xA2,'a'}, {0xC3,0xA3,'a'}, {0xC3,0xA4,'a'}, {0xC3,0xA5,'a'},
    /* æ */    {0xC3,0xA6,'a'},
    /* ç */    {0xC3,0xA7,'c'},
    /* è-ë */ {0xC3,0xA8,'e'}, {0xC3,0xA9,'e'}, {0xC3,0xAA,'e'}, {0xC3,0xAB,'e'},
    /* ì-ï */ {0xC3,0xAC,'i'}, {0xC3,0xAD,'i'}, {0xC3,0xAE,'i'}, {0xC3,0xAF,'i'},
    /* ð */    {0xC3,0xB0,'d'},
    /* ñ */    {0xC3,0xB1,'n'},
    /* ò-ö */ {0xC3,0xB2,'o'}, {0xC3,0xB3,'o'}, {0xC3,0xB4,'o'}, {0xC3,0xB5,'o'}, {0xC3,0xB6,'o'},
    /* ø */    {0xC3,0xB8,'o'},
    /* ù-ü */ {0xC3,0xB9,'u'}, {0xC3,0xBA,'u'}, {0xC3,0xBB,'u'}, {0xC3,0xBC,'u'},
    /* ý */    {0xC3,0xBD,'y'}, {0xC3,0xBF,'y'},
    /* Ā-ą */ {0xC4,0x80,'a'}, {0xC4,0x81,'a'}, {0xC4,0x82,'a'}, {0xC4,0x83,'a'}, {0xC4,0x84,'a'}, {0xC4,0x85,'a'},
    /* Ć-č */ {0xC4,0x86,'c'}, {0xC4,0x87,'c'}, {0xC4,0x88,'c'}, {0xC4,0x89,'c'}, {0xC4,0x8A,'c'}, {0xC4,0x8B,'c'}, {0xC4,0x8C,'c'}, {0xC4,0x8D,'c'},
    /* Ď-đ */ {0xC4,0x8E,'d'}, {0xC4,0x8F,'d'}, {0xC4,0x90,'d'}, {0xC4,0x91,'d'},
    /* Ē-ę */ {0xC4,0x92,'e'}, {0xC4,0x93,'e'}, {0xC4,0x94,'e'}, {0xC4,0x95,'e'}, {0xC4,0x96,'e'}, {0xC4,0x97,'e'}, {0xC4,0x98,'e'}, {0xC4,0x99,'e'},
    /* Ě-ě */ {0xC4,0x9A,'e'}, {0xC4,0x9B,'e'},
    /* Ĝ-ģ */ {0xC4,0x9C,'g'}, {0xC4,0x9D,'g'}, {0xC4,0x9E,'g'}, {0xC4,0x9F,'g'}, {0xC4,0xA0,'g'}, {0xC4,0xA1,'g'}, {0xC4,0xA2,'g'}, {0xC4,0xA3,'g'},
    /* Ĩ-ı */ {0xC4,0xA8,'i'}, {0xC4,0xA9,'i'}, {0xC4,0xAA,'i'}, {0xC4,0xAB,'i'}, {0xC4,0xAC,'i'}, {0xC4,0xAD,'i'}, {0xC4,0xAE,'i'}, {0xC4,0xAF,'i'}, {0xC4,0xB0,'i'}, {0xC4,0xB1,'i'},
    /* Ĺ-ŀ */ {0xC4,0xB9,'l'}, {0xC4,0xBA,'l'}, {0xC4,0xBB,'l'}, {0xC4,0xBC,'l'}, {0xC4,0xBD,'l'}, {0xC4,0xBE,'l'}, {0xC4,0xBF,'l'},
    /* Ł-ł */ {0xC5,0x81,'l'}, {0xC5,0x82,'l'},
    /* Ń-ň */ {0xC5,0x83,'n'}, {0xC5,0x84,'n'}, {0xC5,0x85,'n'}, {0xC5,0x86,'n'}, {0xC5,0x87,'n'}, {0xC5,0x88,'n'},
    /* Ō-ő */ {0xC5,0x8C,'o'}, {0xC5,0x8D,'o'}, {0xC5,0x8E,'o'}, {0xC5,0x8F,'o'}, {0xC5,0x90,'o'}, {0xC5,0x91,'o'},
    /* Ŕ-ř */ {0xC5,0x94,'r'}, {0xC5,0x95,'r'}, {0xC5,0x96,'r'}, {0xC5,0x97,'r'}, {0xC5,0x98,'r'}, {0xC5,0x99,'r'},
    /* Ś-š */ {0xC5,0x9A,'s'}, {0xC5,0x9B,'s'}, {0xC5,0x9C,'s'}, {0xC5,0x9D,'s'}, {0xC5,0x9E,'s'}, {0xC5,0x9F,'s'}, {0xC5,0xA0,'s'}, {0xC5,0xA1,'s'},
    /* Ţ-ť */ {0xC5,0xA2,'t'}, {0xC5,0xA3,'t'}, {0xC5,0xA4,'t'}, {0xC5,0xA5,'t'},
    /* Ũ-ű */ {0xC5,0xA8,'u'}, {0xC5,0xA9,'u'}, {0xC5,0xAA,'u'}, {0xC5,0xAB,'u'}, {0xC5,0xAC,'u'}, {0xC5,0xAD,'u'}, {0xC5,0xAE,'u'}, {0xC5,0xAF,'u'}, {0xC5,0xB0,'u'}, {0xC5,0xB1,'u'},
    /* Ŵ-ŵ */ {0xC5,0xB4,'w'}, {0xC5,0xB5,'w'},
    /* Ŷ-ÿ */ {0xC5,0xB6,'y'}, {0xC5,0xB7,'y'}, {0xC5,0xB8,'y'},
    /* Ź-ž */ {0xC5,0xB9,'z'}, {0xC5,0xBA,'z'}, {0xC5,0xBB,'z'}, {0xC5,0xBC,'z'}, {0xC5,0xBD,'z'}, {0xC5,0xBE,'z'},
    {0,0,0} /* sentinel */
};

/* Number of real entries (excluding sentinel) */
static const int _ACCENT_TABLE_SIZE =
    (int)(sizeof(_ACCENT_TABLE) / sizeof(_ACCENT_TABLE[0])) - 1;

static char _lookup_accent(unsigned char b0, unsigned char b1) {
    /* Table is sorted by (b0, b1) — use binary search O(log n). */
    int lo = 0, hi = _ACCENT_TABLE_SIZE - 1;
    uint16_t key = ((uint16_t)b0 << 8) | b1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        uint16_t mk = ((uint16_t)_ACCENT_TABLE[mid].b0 << 8) | _ACCENT_TABLE[mid].b1;
        if (mk == key) return _ACCENT_TABLE[mid].ascii;
        if (mk < key) lo = mid + 1;
        else           hi = mid - 1;
    }
    return 0;
}

Prove_String *prove_language_normalize(Prove_String *text) {
    const char *src = text->data;
    int64_t len = text->length;

    /* Worst case: same length (accent folding shrinks 2->1) */
    char *buf = (char *)malloc((size_t)(len + 1));
    if (!buf) prove_panic("out of memory");

    int64_t out = 0;
    int64_t i = 0;

    while (i < len) {
        unsigned char c = (unsigned char)src[i];

        if (c < 0x80) {
            /* ASCII — lowercase */
            buf[out++] = (char)tolower(c);
            i++;
        } else if ((c & 0xE0) == 0xC0 && i + 1 < len) {
            /* 2-byte UTF-8 */
            unsigned char b1 = (unsigned char)src[i + 1];
            char mapped = _lookup_accent(c, b1);
            if (mapped) {
                buf[out++] = mapped;
            } else {
                buf[out++] = (char)c;
                buf[out++] = (char)b1;
            }
            i += 2;
        } else if ((c & 0xF0) == 0xE0 && i + 2 < len) {
            /* 3-byte UTF-8 — pass through */
            buf[out++] = (char)c;
            buf[out++] = src[i + 1];
            buf[out++] = src[i + 2];
            i += 3;
        } else if ((c & 0xF8) == 0xF0 && i + 3 < len) {
            /* 4-byte UTF-8 — pass through */
            buf[out++] = (char)c;
            buf[out++] = src[i + 1];
            buf[out++] = src[i + 2];
            buf[out++] = src[i + 3];
            i += 4;
        } else {
            buf[out++] = (char)c;
            i++;
        }
    }

    Prove_String *result = prove_string_new(buf, out);
    free(buf);
    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   transliterate() — accent-to-ASCII only (no case fold)
   ═══════════════════════════════════════════════════════════════════ */

Prove_String *prove_language_transliterate(Prove_String *text) {
    const char *src = text->data;
    int64_t len = text->length;

    char *buf = (char *)malloc((size_t)(len + 1));
    if (!buf) prove_panic("out of memory");

    int64_t out = 0;
    int64_t i = 0;

    while (i < len) {
        unsigned char c = (unsigned char)src[i];

        if (c < 0x80) {
            buf[out++] = (char)c;
            i++;
        } else if ((c & 0xE0) == 0xC0 && i + 1 < len) {
            unsigned char b1 = (unsigned char)src[i + 1];
            char mapped = _lookup_accent(c, b1);
            if (mapped) {
                /* Preserve case: if original was uppercase, uppercase the result */
                if (c == 0xC3 && b1 >= 0x80 && b1 <= 0x9E) {
                    buf[out++] = (char)toupper(mapped);
                } else if (c == 0xC4 && (b1 % 2 == 0) && b1 >= 0x80) {
                    buf[out++] = (char)toupper(mapped);
                } else if (c == 0xC5 && (b1 % 2 == 0) && b1 >= 0x80) {
                    buf[out++] = (char)toupper(mapped);
                } else {
                    buf[out++] = mapped;
                }
            } else {
                buf[out++] = (char)c;
                buf[out++] = (char)b1;
            }
            i += 2;
        } else if ((c & 0xF0) == 0xE0 && i + 2 < len) {
            buf[out++] = (char)c;
            buf[out++] = src[i + 1];
            buf[out++] = src[i + 2];
            i += 3;
        } else if ((c & 0xF8) == 0xF0 && i + 3 < len) {
            buf[out++] = (char)c;
            buf[out++] = src[i + 1];
            buf[out++] = src[i + 2];
            buf[out++] = src[i + 3];
            i += 4;
        } else {
            buf[out++] = (char)c;
            i++;
        }
    }

    Prove_String *result = prove_string_new(buf, out);
    free(buf);
    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   stopwords — static English stopword list with hash set
   ═══════════════════════════════════════════════════════════════════ */

static const char *_STOPWORD_LIST[] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "get", "got", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "isn't", "it", "its", "itself", "just", "let", "like", "ll", "me",
    "might", "more", "most", "must", "mustn't", "my", "myself", "no",
    "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other",
    "our", "ours", "ourselves", "out", "over", "own", "re", "s", "same",
    "shall", "shan't", "she", "should", "shouldn't", "so", "some", "such",
    "t", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to",
    "too", "under", "until", "up", "ve", "very", "was", "wasn't", "we",
    "were", "weren't", "what", "when", "where", "which", "while", "who",
    "whom", "why", "will", "with", "won't", "would", "wouldn't", "you",
    "your", "yours", "yourself", "yourselves",
    NULL
};

/* Simple hash set for fast stopword lookup. */

#define STOP_HASH_SIZE 512

static const char *_stop_hash_table[STOP_HASH_SIZE];
static bool _stop_hash_ready = false;

static uint32_t _stop_hash(const char *s) {
    uint32_t h = 5381;
    while (*s) h = h * 33 + (unsigned char)*s++;
    return h;
}

static void _stop_hash_init(void) {
    if (_stop_hash_ready) return;
    memset(_stop_hash_table, 0, sizeof(_stop_hash_table));
    for (int i = 0; _STOPWORD_LIST[i]; i++) {
        uint32_t slot = _stop_hash(_STOPWORD_LIST[i]) % STOP_HASH_SIZE;
        /* Linear probing */
        while (_stop_hash_table[slot] != NULL) {
            slot = (slot + 1) % STOP_HASH_SIZE;
        }
        _stop_hash_table[slot] = _STOPWORD_LIST[i];
    }
    _stop_hash_ready = true;
}

static bool _is_stopword(const char *word, int64_t len) {
    _stop_hash_init();

    /* Lowercase the word for comparison */
    char lbuf[64];
    if (len >= 64) return false;
    for (int64_t i = 0; i < len; i++) lbuf[i] = (char)tolower((unsigned char)word[i]);
    lbuf[len] = '\0';

    uint32_t slot = _stop_hash(lbuf) % STOP_HASH_SIZE;
    for (int tries = 0; tries < STOP_HASH_SIZE; tries++) {
        if (_stop_hash_table[slot] == NULL) return false;
        if (strcmp(_stop_hash_table[slot], lbuf) == 0) return true;
        slot = (slot + 1) % STOP_HASH_SIZE;
    }
    return false;
}

Prove_List *prove_language_stopwords(void) {
    _stop_hash_init();
    Prove_List *result = prove_list_new(180);
    for (int i = 0; _STOPWORD_LIST[i]; i++) {
        prove_list_push(result, prove_string_from_cstr(_STOPWORD_LIST[i]));
    }
    return result;
}

Prove_List *prove_language_without_stopwords(Prove_String *text) {
    Prove_List *word_list = prove_language_words(text);
    Prove_List *result = prove_list_new(word_list->length);

    for (int64_t i = 0; i < word_list->length; i++) {
        Prove_String *w = (Prove_String *)prove_list_get(word_list, i);
        if (!_is_stopword(w->data, w->length)) {
            prove_list_push(result, w);
        }
    }

    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   frequency() — word frequency table
   ═══════════════════════════════════════════════════════════════════ */

Prove_Table *prove_language_frequency(Prove_String *text) {
    Prove_List *word_list = prove_language_words(text);
    Prove_Table *table = prove_table_new();

    for (int64_t i = 0; i < word_list->length; i++) {
        Prove_String *w = (Prove_String *)prove_list_get(word_list, i);

        /* Lowercase the word for counting */
        char lbuf[256];
        int64_t wlen = w->length < 255 ? w->length : 255;
        for (int64_t j = 0; j < wlen; j++) lbuf[j] = (char)tolower((unsigned char)w->data[j]);
        lbuf[wlen] = '\0';

        Prove_String *key = prove_string_new(lbuf, wlen);
        Prove_Option existing = prove_table_get(key, table);

        int64_t *count = (int64_t *)prove_alloc(sizeof(Prove_Header) + sizeof(int64_t));
        if (existing.tag == 1) {
            int64_t *old_count = (int64_t *)((char *)existing.value + sizeof(Prove_Header));
            *((int64_t *)((char *)count + sizeof(Prove_Header))) = *old_count + 1;
        } else {
            *((int64_t *)((char *)count + sizeof(Prove_Header))) = 1;
        }
        table = prove_table_add(key, count, table);
    }

    return table;
}

/* ═══════════════════════════════════════════════════════════════════
   keywords() — top N words by frequency
   ═══════════════════════════════════════════════════════════════════ */

Prove_List *prove_language_keywords(Prove_String *text, int64_t count) {
    /* Use the hash-based frequency table, then sort by frequency. */
    Prove_Table *freq_table = prove_language_frequency(text);

    /* Extract entries into a sortable array */
    typedef struct { Prove_String *word; int64_t freq; } WordFreq;

    Prove_List *keys = prove_table_keys(freq_table);
    int64_t nkeys = keys->length;
    WordFreq *freqs = (WordFreq *)calloc((size_t)(nkeys + 1), sizeof(WordFreq));
    if (!freqs) prove_panic("out of memory");
    int64_t nfreqs = 0;

    for (int64_t i = 0; i < nkeys; i++) {
        Prove_String *key = (Prove_String *)prove_list_get(keys, i);

        /* Filter out stopwords */
        if (_is_stopword(key->data, key->length)) continue;

        Prove_Option val = prove_table_get(key, freq_table);
        int64_t f = 1;
        if (val.tag == 1) {
            f = *((int64_t *)((char *)val.value + sizeof(Prove_Header)));
        }
        freqs[nfreqs].word = key;
        freqs[nfreqs].freq = f;
        nfreqs++;
    }

    /* Sort by frequency descending (insertion sort) */
    for (int64_t i = 1; i < nfreqs; i++) {
        WordFreq tmp = freqs[i];
        int64_t j = i - 1;
        while (j >= 0 && freqs[j].freq < tmp.freq) {
            freqs[j + 1] = freqs[j];
            j--;
        }
        freqs[j + 1] = tmp;
    }

    /* Collect top N */
    int64_t n = count < nfreqs ? count : nfreqs;
    Prove_List *result = prove_list_new(n);
    for (int64_t i = 0; i < n; i++) {
        prove_list_push(result, freqs[i].word);
    }

    free(freqs);
    return result;
}

