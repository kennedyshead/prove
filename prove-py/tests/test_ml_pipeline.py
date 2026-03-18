"""Tests for the ML extraction, training, and store-building pipeline."""

from __future__ import annotations

import json
import sys
import tarfile
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "prove-py" / "src"))

ml_extract_spec = spec_from_loader(
    "ml_extract",
    SourceFileLoader("ml_extract", str(_REPO_ROOT / "scripts" / "ml_extract.py")),
)
ml_extract = module_from_spec(ml_extract_spec)
ml_extract_spec.loader.exec_module(ml_extract)

ml_train_spec = spec_from_loader(
    "ml_train",
    SourceFileLoader("ml_train", str(_REPO_ROOT / "scripts" / "ml_train.py")),
)
ml_train = module_from_spec(ml_train_spec)
ml_train_spec.loader.exec_module(ml_train)

build_stores_spec = spec_from_loader(
    "build_stores",
    SourceFileLoader(
        "build_stores",
        str(_REPO_ROOT / "prove-py" / "scripts" / "build_stores.py"),
    ),
)
build_stores = module_from_spec(build_stores_spec)
build_stores_spec.loader.exec_module(build_stores)


# ── ml_extract ────────────────────────────────────────────────────────────────


class TestTokenText:
    def test_value_takes_precedence(self) -> None:
        from prove.tokens import TokenKind

        result = ml_extract._token_text(TokenKind.IDENTIFIER, "myVar")
        assert result == "myVar"

    def test_kind_name_for_empty_value(self) -> None:
        from prove.tokens import TokenKind

        result = ml_extract._token_text(TokenKind.NEWLINE, "")
        assert result == "<NEWLINE>"

    def test_kind_name_snake_case(self) -> None:
        from prove.tokens import TokenKind

        result = ml_extract._token_text(TokenKind.DOC_COMMENT, "")
        assert result == "<DOC_COMMENT>"


class TestTypeExprToStr:
    def test_simple_type(self) -> None:
        from prove.ast_nodes import SimpleType
        from prove.source import Span

        span = Span("<test>", 1, 1, 1, 8)
        te = SimpleType("Integer", span)
        assert ml_extract._type_expr_to_str(te) == "Integer"

    def test_generic_type(self) -> None:
        from prove.ast_nodes import GenericType, SimpleType
        from prove.source import Span

        span = Span("<test>", 1, 1, 1, 8)
        te = GenericType("List", [SimpleType("Integer", span)], span)
        assert ml_extract._type_expr_to_str(te) == "List[Integer]"

    def test_generic_multiple_args(self) -> None:
        from prove.ast_nodes import GenericType, SimpleType
        from prove.source import Span

        span = Span("<test>", 1, 1, 1, 8)
        te = GenericType(
            "Map",
            [SimpleType("String", span), SimpleType("Integer", span)],
            span,
        )
        assert ml_extract._type_expr_to_str(te) == "Map[String, Integer]"

    def test_modified_type(self) -> None:
        from prove.ast_nodes import ModifiedType, TypeModifier
        from prove.source import Span

        span = Span("<test>", 1, 1, 1, 8)
        te = ModifiedType(
            "Integer",
            [TypeModifier(None, "Unsigned", span)],
            span,
        )
        assert ml_extract._type_expr_to_str(te) == "Integer:[Unsigned]"


class TestCollectPrvFiles:
    def test_finds_files_in_stdlib(self, tmp_path: Path) -> None:
        stdlib = tmp_path / "prove-py" / "src" / "prove" / "stdlib"
        stdlib.mkdir(parents=True)
        p = stdlib / "math.prv"
        p.write_text("module Math\ntransforms add(a Integer, b Integer) Integer\n")
        p = stdlib / "text.prv"
        p.write_text("module Text\ntransforms length(s String) Integer\n")

        files = ml_extract.collect_prv_files(tmp_path)
        names = {rel for _abs, rel in files}
        assert "prove-py/src/prove/stdlib/math.prv" in names
        assert "prove-py/src/prove/stdlib/text.prv" in names

    def test_skips_missing_directories(self, tmp_path: Path) -> None:
        files = ml_extract.collect_prv_files(tmp_path)
        assert files == []

    def test_finds_in_multiple_dirs(self, tmp_path: Path) -> None:
        stdlib = tmp_path / "prove-py" / "src" / "prove" / "stdlib"
        examples = tmp_path / "examples"
        stdlib.mkdir(parents=True)
        examples.mkdir(parents=True)
        p = stdlib / "math.prv"
        p.write_text("module Math\ntransforms add(a Integer, b Integer) Integer\n")
        p = examples / "demo.prv"
        p.write_text("module Demo\ntransforms demo(s String) Unit\n")

        files = ml_extract.collect_prv_files(tmp_path)
        names = {rel for _abs, rel in files}
        assert "prove-py/src/prove/stdlib/math.prv" in names
        assert "examples/demo.prv" in names


class TestExtractFile:
    def test_extracts_ngrams(self, tmp_path: Path) -> None:
        prv = tmp_path / "demo.prv"
        content = "module Test\n/// Read a file.\ntransforms read_file(path String) Integer\n"
        prv.write_text(content)

        ngrams, triples, docstrings, from_blocks = ml_extract.extract_file(prv, "demo.prv")

        assert len(ngrams) > 0
        for ngram in ngrams:
            assert "prev2" in ngram
            assert "prev1" in ngram
            assert "next" in ngram
            assert ngram["file"] == "demo.prv"
            assert "line" in ngram

    def test_extracts_function_triples(self, tmp_path: Path) -> None:
        prv = tmp_path / "demo.prv"
        content = (
            "module Test\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n    result as Integer = a + b\n"
        )
        prv.write_text(content)

        _ngrams, triples, _docstrings, _from_blocks = ml_extract.extract_file(prv, "demo.prv")

        assert len(triples) == 1
        triple = triples[0]
        assert triple["verb"] == "transforms"
        assert triple["name"] == "add"
        assert triple["kind"] == "function_triple"
        assert triple["first_param_type"] == "Integer"
        assert triple["return_type"] == "Integer"

    def test_extracts_docstrings(self, tmp_path: Path) -> None:
        prv = tmp_path / "demo.prv"
        content = (
            "module Test\n"
            "/// Computes SHA-256 hash of input.\n"
            "transforms sha256(data String) String\n"
            "from\n    result as String = data\n"
        )
        prv.write_text(content)

        _ngrams, _triples, docstrings, _from_blocks = ml_extract.extract_file(prv, "demo.prv")

        assert len(docstrings) == 1
        assert docstrings[0]["doc"] == "Computes SHA-256 hash of input."
        assert docstrings[0]["verb"] == "transforms"
        assert docstrings[0]["name"] == "sha256"

    def test_extracts_from_block_tokens(self, tmp_path: Path) -> None:
        prv = tmp_path / "demo.prv"
        prv.write_text(
            "module Test\ntransforms read(s String) String\n"
            "from\n    result as String = text.split value s\n"
        )

        _ngrams, _triples, _docstrings, from_blocks = ml_extract.extract_file(prv, "demo.prv")

        assert len(from_blocks) > 0
        for fb in from_blocks:
            assert fb["kind"] == "from_block"
            assert "prev2" in fb
            assert "prev1" in fb
            assert "next" in fb
            assert fb["verb"] == "transforms"
            assert fb["file"] == "demo.prv"

    def test_handles_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.prv"
        ngrams, triples, docstrings, from_blocks = ml_extract.extract_file(
            missing, "nonexistent.prv"
        )
        assert ngrams == []
        assert triples == []
        assert docstrings == []
        assert from_blocks == []

    def test_handles_parse_error_gracefully(self, tmp_path: Path) -> None:
        prv = tmp_path / "broken.prv"
        prv.write_text("module Broken\ntransforms bad(x Integer) Integer\n")

        ngrams, triples, docstrings, from_blocks = ml_extract.extract_file(prv, "broken.prv")
        assert len(ngrams) > 0
        assert triples == []

    def test_module_name_from_qualified_decls(self, tmp_path: Path) -> None:
        prv = tmp_path / "qualified.prv"
        content = (
            "module Math\n"
            "/// Add two integers.\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n    result as Integer = a + b\n"
        )
        prv.write_text(content)

        _ngrams, triples, docstrings, _from_blocks = ml_extract.extract_file(prv, "qualified.prv")

        assert len(triples) == 1
        assert docstrings[0]["module"] == "Math"


# ── ml_train ────────────────────────────────────────────────────────────────


class TestBuildBigramModel:
    def test_groups_by_context(self) -> None:
        ngrams = [
            {"prev2": "<START>", "prev1": "verb", "next": "add"},
            {"prev2": "<START>", "prev1": "verb", "next": "subtract"},
            {"prev2": "<START>", "prev1": "verb", "next": "add"},
        ]
        model = ml_train.build_bigram_model(ngrams, top_k=10)

        key = json.dumps(["<START>", "verb"])
        assert key in model
        tokens = [t for t, _c in model[key]]
        assert "add" in tokens
        assert "subtract" in tokens

    def test_respects_top_k(self) -> None:
        ngrams = [{"prev2": "a", "prev1": "b", "next": f"tok{i}"} for i in range(20)]
        model = ml_train.build_bigram_model(ngrams, top_k=3)

        key = json.dumps(["a", "b"])
        assert len(model[key]) == 3

    def test_empty_ngrams(self) -> None:
        model = ml_train.build_bigram_model([], top_k=5)
        assert model == {}

    def test_counts_are_sorted_descending(self) -> None:
        ngrams = [
            {"prev2": "x", "prev1": "y", "next": "low"},
            {"prev2": "x", "prev1": "y", "next": "high"},
            {"prev2": "x", "prev1": "y", "next": "high"},
            {"prev2": "x", "prev1": "y", "next": "high"},
            {"prev2": "x", "prev1": "y", "next": "mid"},
            {"prev2": "x", "prev1": "y", "next": "mid"},
        ]
        model = ml_train.build_bigram_model(ngrams, top_k=10)
        key = json.dumps(["x", "y"])
        counts = [c for _t, c in model[key]]
        assert counts == sorted(counts, reverse=True)


class TestBuildUnigramModel:
    def test_groups_by_prev1(self) -> None:
        ngrams = [
            {"prev1": "transforms", "next": "add"},
            {"prev1": "transforms", "next": "subtract"},
            {"prev1": "from", "next": "text"},
        ]
        model = ml_train.build_unigram_model(ngrams, top_k=10)

        assert "transforms" in model
        assert "from" in model

    def test_respects_top_k(self) -> None:
        ngrams = [{"prev1": "verb", "next": f"tok{i}"} for i in range(15)]
        model = ml_train.build_unigram_model(ngrams, top_k=5)
        assert len(model["verb"]) == 5

    def test_empty_ngrams(self) -> None:
        model = ml_train.build_unigram_model([], top_k=5)
        assert model == {}


class TestBuildFromBlockModel:
    def test_builds_context_model(self) -> None:
        records = [
            {"prev2": "<START>", "prev1": "<START>", "next": "from"},
            {"prev2": "<START>", "prev1": "<START>", "next": "result"},
            {"prev2": "<START>", "prev1": "<START>", "next": "from"},
        ]
        model = ml_train.build_from_block_model(records, top_k=10)

        key = json.dumps(["<START>", "<START>"])
        assert key in model
        tokens = [t for t, _c in model[key]]
        assert "from" in tokens
        assert "result" in tokens


class TestBuildDocstringIndex:
    def test_indexes_by_words(self) -> None:
        records = [
            {
                "doc": "Computes SHA-256 hash of input data",
                "module": "Hash",
                "name": "sha256",
                "verb": "transforms",
                "first_param_type": "String",
                "return_type": "String",
            },
        ]
        index = ml_train.build_docstring_index(records)

        assert "sha256" in index or "hash" in index
        entries = index.get("sha256", index.get("hash", []))
        assert len(entries) >= 1
        assert entries[0]["module"] == "Hash"
        assert entries[0]["name"] == "sha256"

    def test_strips_short_words(self) -> None:
        records = [
            {
                "doc": "ab cd ef gh",
                "module": "Test",
                "name": "foo",
                "verb": "transforms",
            },
        ]
        index = ml_train.build_docstring_index(records)
        for word, _entries in index.items():
            assert len(word) >= 3

    def test_multiple_entries_per_word(self) -> None:
        records = [
            {
                "doc": "hash using sha algorithm",
                "module": "Hash",
                "name": "sha256",
                "verb": "transforms",
            },
            {
                "doc": "hash using md5 algorithm",
                "module": "Hash",
                "name": "md5",
                "verb": "transforms",
            },
        ]
        index = ml_train.build_docstring_index(records)
        assert "hash" in index
        assert len(index["hash"]) == 2

    def test_empty_records(self) -> None:
        index = ml_train.build_docstring_index([])
        assert index == {}


class TestLoadRecords:
    def test_load_ngrams_filters_non_ngrams(self, tmp_path: Path) -> None:
        records = [
            {"kind": "ngram", "prev2": "a", "prev1": "b", "next": "c"},
            {"kind": "function_triple", "verb": "add"},
            {"kind": "docstring_mapping", "doc": "x"},
        ]
        p = tmp_path / "test.json"
        p.write_text(json.dumps(records))
        result = ml_train.load_ngrams(p)
        assert len(result) == 1
        assert result[0]["prev2"] == "a"

    def test_load_docstring_records(self, tmp_path: Path) -> None:
        records = [
            {"kind": "docstring_mapping", "doc": "test"},
            {"kind": "ngram", "prev2": "a", "prev1": "b", "next": "c"},
        ]
        p = tmp_path / "test.json"
        p.write_text(json.dumps(records))
        result = ml_train.load_docstring_records(p)
        assert len(result) == 1
        assert result[0]["doc"] == "test"

    def test_load_from_block_records(self, tmp_path: Path) -> None:
        records = [
            {"kind": "from_block", "prev2": "a", "prev1": "b", "next": "c"},
            {"kind": "function_triple", "verb": "add"},
        ]
        p = tmp_path / "test.json"
        p.write_text(json.dumps(records))
        result = ml_train.load_from_block_records(p)
        assert len(result) == 1


# ── build_stores ───────────────────────────────────────────────────────────


class TestBuildStoresHelpers:
    def test_prv_str_escapes_backslash(self) -> None:
        result = build_stores._prv_str('say "hello"')
        assert '\\"' in result

    def test_prv_str_simple(self) -> None:
        result = build_stores._prv_str("hello")
        assert result == '"hello"'

    def test_row_id_increments(self) -> None:
        assert build_stores._row_id(0) == "r00000"
        assert build_stores._row_id(42) == "r00042"
        assert build_stores._row_id(999) == "r00999"

    def test_strip_quotes(self) -> None:
        assert build_stores._strip_quotes('"hello"') == "hello"
        assert build_stores._strip_quotes("hello") == "hello"
        assert build_stores._strip_quotes('""') == ""


class TestWriteLspStores:
    def test_writes_bigrams_prv(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        out_dir = tmp_path / "out"
        data_dir.mkdir(parents=True)

        (data_dir / "bigrams_model.json").write_text(
            json.dumps({"transforms": [["add", 10], ["subtract", 5]]})
        )

        build_stores._write_lsp_stores(data_dir, out_dir, top_k=5)

        bigrams_prv = out_dir / "bigrams" / "current.prv"
        assert bigrams_prv.exists()
        content = bigrams_prv.read_text()
        assert "type Bigram" in content
        assert "add" in content
        assert "transforms" in content

    def test_writes_completions_prv(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        out_dir = tmp_path / "out"
        data_dir.mkdir(parents=True)

        (data_dir / "completions_model.json").write_text(
            json.dumps({'["transforms", "<START>"]': [["add", 8], ["subtract", 3]]})
        )

        build_stores._write_lsp_stores(data_dir, out_dir, top_k=5)

        comps_prv = out_dir / "completions" / "current.prv"
        assert comps_prv.exists()
        assert "type Completion" in comps_prv.read_text()

    def test_writes_from_blocks_prv(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        out_dir = tmp_path / "out"
        data_dir.mkdir(parents=True)

        (data_dir / "from_blocks_model.json").write_text(
            json.dumps({'["<START>", "<START>"]': [["from", 12], ["result", 7]]})
        )

        build_stores._write_lsp_stores(data_dir, out_dir, top_k=5)

        fb_prv = out_dir / "from_blocks" / "current.prv"
        assert fb_prv.exists()
        assert "type FromBlockML" in fb_prv.read_text()

    def test_writes_docstrings_prv(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        out_dir = tmp_path / "out"
        data_dir.mkdir(parents=True)

        (data_dir / "docstring_index.json").write_text(
            json.dumps(
                {
                    "sha256": [
                        {
                            "module": "Hash",
                            "name": "sha256",
                            "verb": "transforms",
                            "doc": "Computes SHA-256 hash",
                        }
                    ]
                }
            )
        )

        build_stores._write_lsp_stores(data_dir, out_dir, top_k=5)

        doc_prv = out_dir / "docstrings" / "current.prv"
        assert doc_prv.exists()
        content = doc_prv.read_text()
        assert "type DocstringMap" in content
        assert "sha256" in content

    def test_creates_versions_directory(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        out_dir = tmp_path / "out"
        data_dir.mkdir(parents=True)

        (data_dir / "bigrams_model.json").write_text(json.dumps({"x": [["y", 1]]}))

        build_stores._write_lsp_stores(data_dir, out_dir, top_k=5)

        assert (out_dir / "bigrams" / "versions").is_dir()


class TestCreateTarball:
    def test_creates_tarball(self, tmp_path: Path) -> None:
        source = tmp_path / "pkg"
        source.mkdir()
        (source / "readme.txt").write_text("hello world")

        tar_path = tmp_path / "out.tar.gz"
        build_stores._create_tarball(source, tar_path)

        assert tar_path.exists()
        assert tar_path.stat().st_size > 0

        with tarfile.open(tar_path) as tar:
            names = tar.getnames()
            assert any("lsp-ml-stores/readme.txt" in n for n in names)

    def test_creates_version_file(self, tmp_path: Path) -> None:
        source = tmp_path / "pkg"
        source.mkdir()
        tar_path = tmp_path / "out.tar.gz"

        build_stores._create_tarball(source, tar_path)

        with tarfile.open(tar_path) as tar:
            names = tar.getnames()
            assert any("VERSION.txt" in n for n in names)


# ── e2e integration test ──────────────────────────────────────────────────────


class TestMLPipelineE2E:
    def test_full_pipeline_extract_train_build(self, tmp_path: Path) -> None:
        stdlib = tmp_path / "prove-py" / "src" / "prove" / "stdlib"
        stdlib.mkdir(parents=True)

        p = stdlib / "math.prv"
        content = (
            "module Math\n"
            "/// Add two integers.\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n    result as Integer = a + b\n"
        )
        p.write_text(content)

        all_records: list[dict[str, object]] = []
        for prv_file in sorted(stdlib.rglob("*.prv")):
            rel = str(prv_file.relative_to(tmp_path))
            ngrams, triples, docstrings, from_blocks = ml_extract.extract_file(prv_file, rel)
            all_records.extend(ngrams)
            all_records.extend(triples)
            all_records.extend(docstrings)
            all_records.extend(from_blocks)

        assert len(all_records) > 0
        ngrams_records = [
            r
            for r in all_records
            if "prev2" in r and "prev1" in r and "next" in r and r.get("kind") is None
        ]
        triple_records = [r for r in all_records if r.get("kind") == "function_triple"]
        assert len(ngrams_records) > 0
        assert len(triple_records) == 1
        assert triple_records[0]["verb"] == "transforms"
        assert triple_records[0]["name"] == "add"

        bigram_model = ml_train.build_bigram_model(ngrams_records, top_k=5)
        unigram_model = ml_train.build_unigram_model(ngrams_records, top_k=5)
        docstring_records = [r for r in all_records if r.get("kind") == "docstring_mapping"]
        docstring_index = ml_train.build_docstring_index(docstring_records)
        from_block_records = [r for r in all_records if r.get("kind") == "from_block"]
        from_block_model = ml_train.build_from_block_model(from_block_records, top_k=5)

        assert len(bigram_model) > 0
        assert len(unigram_model) > 0
        assert len(docstring_index) > 0
        assert len(from_block_model) > 0

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        completions_model = {json.dumps(["<START>", "<START>"]): [["from", 10]]}
        (data_dir / "completions_model.json").write_text(json.dumps(completions_model))
        (data_dir / "bigrams_model.json").write_text(json.dumps(unigram_model))
        (data_dir / "from_blocks_model.json").write_text(json.dumps(from_block_model))
        (data_dir / "docstring_index.json").write_text(json.dumps(docstring_index))

        stores_out = tmp_path / "stores_out"
        build_stores._write_lsp_stores(data_dir, stores_out, top_k=5)

        bigrams_prv = stores_out / "bigrams" / "current.prv"
        assert bigrams_prv.exists()
        content = bigrams_prv.read_text()
        assert "type Bigram" in content

        completions_prv = stores_out / "completions" / "current.prv"
        assert completions_prv.exists()
        assert "type Completion" in completions_prv.read_text()
