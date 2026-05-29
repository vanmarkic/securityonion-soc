import pytest

from src.adapters.elasticsearch.escaping import (
    escape_lucene,
    escape_painless,
    to_uuid,
    validate_id,
    validate_public_id,
)


def test_escape_lucene_order_backslash_then_quote():
    # backslash escaped FIRST, then double-quote
    assert escape_lucene(r'a\b"c') == r'a\\b\"c'


def test_escape_painless_backslash_then_singlequote():
    assert escape_painless(r"a\b'c") == r"a\\b\'c"


def test_to_uuid_deterministic_and_v4_shape():
    u = to_uuid("my-public-id")
    assert u == to_uuid("my-public-id")            # deterministic
    assert len(u) == 36
    assert u[14] == "4"                            # version nibble forced '4'
    assert u[19] == "b"                            # variant char forced 'b'


def test_to_uuid_matches_go_golden():
    # Golden values captured from the real Go util.ToUUID (verified byte-identical).
    assert to_uuid("12345") == "dd85fe82-bddb-4489-b936-3428988506bb"
    assert to_uuid("my-public-id") == "972b27fb-a7ac-4820-b98c-8640e2425d98"


@pytest.mark.parametrize("ident", ["abc", "a-b_c", "x" * 128, "12345"])
def test_validate_public_id_ok(ident):
    assert validate_public_id(ident, "publicId") is None


@pytest.mark.parametrize("ident", ["", "ab", "x" * 129, "bad id", "a@b"])
def test_validate_public_id_rejects(ident):
    assert validate_public_id(ident, "publicId") == "invalid ID for publicId"


def test_validate_public_id_rejects_trailing_newline():
    # Go RE2 `^...$` anchors at end-of-text; Python's `$` would accept a trailing
    # "\n". Faithful port must reject it (verified against Go MatchString=false).
    assert validate_public_id("abc\n", "publicId") == "invalid ID for publicId"
    assert validate_public_id("my-public-id\n", "publicId") == "invalid ID for publicId"


@pytest.mark.parametrize("ident", ["abcde", "a-b_c12", "x" * 50])
def test_validate_id_ok(ident):
    assert validate_id(ident, "caseId") is None


@pytest.mark.parametrize("ident", ["abcd", "x" * 51, "", "has space"])
def test_validate_id_rejects(ident):
    assert validate_id(ident, "caseId") == "invalid ID for caseId"


def test_validate_id_rejects_trailing_newline():
    # Go RE2 `^...$` anchors at end-of-text; Python's `$` would accept a trailing
    # "\n". Faithful port must reject it (verified against Go MatchString=false).
    assert validate_id("abcde\n", "caseId") == "invalid ID for caseId"
