"""Tests for the Language C runtime module."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestLanguageWords:
    def test_basic_sentence(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("Hello world 42");
                Prove_List *words = prove_language_words(text);
                printf("%lld\\n", (long long)words->length);
                for (int64_t i = 0; i < words->length; i++) {
                    Prove_String *w = (Prove_String *)prove_list_get(words, i);
                    printf("%.*s\\n", (int)w->length, w->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_words")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "3"
        assert lines[1] == "Hello"
        assert lines[2] == "world"
        assert lines[3] == "42"

    def test_punctuation_stripped(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("one, two! three.");
                Prove_List *words = prove_language_words(text);
                printf("%lld\\n", (long long)words->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_words_p")
        assert result.returncode == 0
        assert result.stdout.strip().split("\n")[0] == "3"

    def test_empty_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("");
                Prove_List *words = prove_language_words(text);
                printf("%lld\\n", (long long)words->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_words_e")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestLanguageSentences:
    def test_two_sentences(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("Hello world. How are you?");
                Prove_List *sents = prove_language_sentences(text);
                printf("%lld\\n", (long long)sents->length);
                for (int64_t i = 0; i < sents->length; i++) {
                    Prove_String *s = (Prove_String *)prove_list_get(sents, i);
                    printf("%.*s\\n", (int)s->length, s->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sent")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "2"
        assert lines[1] == "Hello world."
        assert lines[2] == "How are you?"

    def test_abbreviation_handling(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("Dr. Smith went home. It was late.");
                Prove_List *sents = prove_language_sentences(text);
                printf("%lld\\n", (long long)sents->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sent_a")
        assert result.returncode == 0
        assert result.stdout.strip().split("\n")[0] == "2"


class TestLanguageStem:
    def test_known_pairs(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                const char *words[] = {"running", "caresses", "ponies", "cats"};
                for (int i = 0; i < 4; i++) {
                    Prove_String *w = prove_string_from_cstr(words[i]);
                    Prove_String *s = prove_language_stem(w);
                    printf("%.*s\\n", (int)s->length, s->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_stem")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "run"
        assert lines[1] == "caress"
        assert lines[2] == "poni"
        assert lines[3] == "cat"


class TestLanguageRoot:
    def test_suffix_strip(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                const char *words[] = {"validation", "running", "happiness", "parties"};
                for (int i = 0; i < 4; i++) {
                    Prove_String *w = prove_string_from_cstr(words[i]);
                    Prove_String *r = prove_language_root(w);
                    printf("%.*s\\n", (int)r->length, r->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_root")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "valid"
        assert lines[1] == "runn"
        assert lines[2] == "happi"
        assert lines[3] == "party"


class TestLanguageDistance:
    def test_identical(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *a = prove_string_from_cstr("hello");
                Prove_String *b = prove_string_from_cstr("hello");
                printf("%lld\\n", (long long)prove_language_distance(a, b));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_dist0")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_kitten_sitting(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *a = prove_string_from_cstr("kitten");
                Prove_String *b = prove_string_from_cstr("sitting");
                printf("%lld\\n", (long long)prove_language_distance(a, b));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_dist3")
        assert result.returncode == 0
        assert result.stdout.strip() == "3"

    def test_empty_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *a = prove_string_from_cstr("");
                Prove_String *b = prove_string_from_cstr("hello");
                printf("%lld\\n", (long long)prove_language_distance(a, b));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_dist_e")
        assert result.returncode == 0
        assert result.stdout.strip() == "5"


class TestLanguageSimilarity:
    def test_identical(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *a = prove_string_from_cstr("hello");
                Prove_String *b = prove_string_from_cstr("hello");
                printf("%.2f\\n", prove_language_similarity(a, b));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sim1")
        assert result.returncode == 0
        assert result.stdout.strip() == "1.00"

    def test_different(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *a = prove_string_from_cstr("hello");
                Prove_String *b = prove_string_from_cstr("world");
                double sim = prove_language_similarity(a, b);
                printf("%d\\n", sim < 1.0 ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sim2")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestLanguageSoundex:
    def test_robert(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *w = prove_string_from_cstr("Robert");
                Prove_String *s = prove_language_soundex(w);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sdx1")
        assert result.returncode == 0
        assert result.stdout.strip() == "R163"

    def test_ashcraft(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *w = prove_string_from_cstr("Ashcraft");
                Prove_String *s = prove_language_soundex(w);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sdx2")
        assert result.returncode == 0
        assert result.stdout.strip() == "A261"


class TestLanguageMetaphone:
    def test_basic(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *w = prove_string_from_cstr("Smith");
                Prove_String *m = prove_language_metaphone(w);
                printf("%.*s\\n", (int)m->length, m->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_meta")
        assert result.returncode == 0
        out = result.stdout.strip()
        assert len(out) > 0  # produces some phonetic code

    def test_empty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *w = prove_string_from_cstr("");
                Prove_String *m = prove_language_metaphone(w);
                printf("%lld\\n", (long long)m->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_meta_e")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestLanguageNgrams:
    def test_bigrams(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("one two three four");
                Prove_List *bi = prove_language_bigrams(text);
                printf("%lld\\n", (long long)bi->length);
                for (int64_t i = 0; i < bi->length; i++) {
                    Prove_String *s = (Prove_String *)prove_list_get(bi, i);
                    printf("%.*s\\n", (int)s->length, s->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_bi")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "3"
        assert lines[1] == "one two"
        assert lines[2] == "two three"
        assert lines[3] == "three four"

    def test_trigrams(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("a b c d");
                Prove_List *tri = prove_language_ngrams(text, 3);
                printf("%lld\\n", (long long)tri->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_tri")
        assert result.returncode == 0
        assert result.stdout.strip().split("\n")[0] == "2"

    def test_n_greater_than_words(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("one two");
                Prove_List *ng = prove_language_ngrams(text, 5);
                printf("%lld\\n", (long long)ng->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_ng_big")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestLanguageNormalize:
    def test_accents_stripped(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("caf\\xc3\\xa9");
                Prove_String *n = prove_language_normalize(text);
                printf("%.*s\\n", (int)n->length, n->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_norm")
        assert result.returncode == 0
        assert result.stdout.strip() == "cafe"

    def test_uppercase_folded(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("HELLO World");
                Prove_String *n = prove_language_normalize(text);
                printf("%.*s\\n", (int)n->length, n->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_norm2")
        assert result.returncode == 0
        assert result.stdout.strip() == "hello world"


class TestLanguageStopwords:
    def test_returns_list(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *sw = prove_language_stopwords();
                printf("%d\\n", sw->length > 100 ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sw")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_filter_works(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("the quick brown fox");
                Prove_List *filtered = prove_language_without_stopwords(text);
                printf("%lld\\n", (long long)filtered->length);
                for (int64_t i = 0; i < filtered->length; i++) {
                    Prove_String *w = (Prove_String *)prove_list_get(filtered, i);
                    printf("%.*s\\n", (int)w->length, w->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_sw_f")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "3"
        assert "quick" in lines
        assert "brown" in lines
        assert "fox" in lines


class TestLanguageFrequency:
    def test_word_counts(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("cat dog cat");
                Prove_Table *freq = prove_language_frequency(text);
                printf("%lld\\n", (long long)prove_table_length(freq));

                Prove_String *cat_key = prove_string_from_cstr("cat");
                Prove_Option opt = prove_table_get(cat_key, freq);
                if (opt.tag == 1) {
                    int64_t *val = (int64_t *)((char *)opt.value + sizeof(Prove_Header));
                    printf("cat=%lld\\n", (long long)*val);
                }

                Prove_String *dog_key = prove_string_from_cstr("dog");
                opt = prove_table_get(dog_key, freq);
                if (opt.tag == 1) {
                    int64_t *val = (int64_t *)((char *)opt.value + sizeof(Prove_Header));
                    printf("dog=%lld\\n", (long long)*val);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_freq")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "2"  # two unique words
        assert "cat=2" in lines
        assert "dog=1" in lines


class TestLanguageKeywords:
    def test_top_n(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("cat dog cat bird cat dog");
                Prove_List *kw = prove_language_keywords(text, 2);
                printf("%lld\\n", (long long)kw->length);
                /* First keyword should be 'cat' (freq=3) */
                Prove_String *first = (Prove_String *)prove_list_get(kw, 0);
                printf("%.*s\\n", (int)first->length, first->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_kw")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "2"
        assert lines[1] == "cat"


class TestLanguageTokens:
    def test_token_accessors(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *text = prove_string_from_cstr("Hi!");
                Prove_List *toks = prove_language_tokens(text);
                printf("%lld\\n", (long long)toks->length);
                for (int64_t i = 0; i < toks->length; i++) {
                    Prove_Language_Token *t = (Prove_Language_Token *)prove_list_get(toks, i);
                    Prove_String *txt = prove_language_token_text(t);
                    printf("%.*s %lld %lld %lld\\n",
                        (int)txt->length, txt->data,
                        (long long)prove_language_token_start(t),
                        (long long)prove_language_token_end(t),
                        (long long)prove_language_token_kind(t));
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_tok")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "2"  # "Hi" and "!"
        assert lines[1].startswith("Hi ")
        assert lines[1].endswith(" 0")  # kind=WORD=0


class TestLanguageTransliterate:
    def test_preserves_case(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_language.h"
            #include <stdio.h>
            int main(void) {
                /* "Café" in UTF-8 */
                Prove_String *text = prove_string_from_cstr("Caf\\xc3\\xa9");
                Prove_String *t = prove_language_transliterate(text);
                printf("%.*s\\n", (int)t->length, t->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="lang_trans")
        assert result.returncode == 0
        assert result.stdout.strip() == "Cafe"
