"""Observable classifier unit tests.

Ports ``server/modules/elastic/observables_test.go`` (``TestObservables``) byte
for byte: the same input/expected pairs, the same evaluation order
(ip/domain/fqdn/url/filename/uriPath/hash, default ``other``), and the IP check
backed by Python's ``ipaddress`` (Go's ``net.ParseIP``).
"""

from __future__ import annotations

import pytest

from src.adapters.elasticsearch.observables import Observables


@pytest.mark.parametrize(
    ("expr", "expect"),
    [
        ("www.google.com", "fqdn"),
        ("sub.www.google.com", "fqdn"),
        ("test.com", "domain"),
        ("test.co", "domain"),
        ("c:/test.doc", "filename"),
        ("/var/log/syslog.tgz", "filename"),
        ("/test/foo", "uriPath"),
        ("/test/foo/bar", "uriPath"),
        ("file://some/file/path.txt", "url"),
        ("http://www.example.com:8080/path", "url"),
        ("127.0.0.1", "ip"),
        ("ff02::1:ffc5:a922", "ip"),
        ("ff02::16", "ip"),
        (
            "0e2fc59194659497c8d0aec1762add1324ad2e02549bb3e41d58ca8f39e14843",
            "hash",
        ),
        ("3b43c8fadd64750525a2e285d83fa01d62227999", "hash"),
        ("db7298d2ae5733b53f40ab2e99058a9f", "hash"),
        (
            "ea04541a17986a92e4d68f57e97d477845e778721044d0dcf96d380a7eddfc"
            "427a7ff0528931c39c35428cf78176da2c9741023b9c298be82521c96d547d68e8",
            "hash",
        ),
        ("xyz", "other"),
    ],
)
def test_get_type(expr: str, expect: str) -> None:
    assert Observables().get_type(expr) == expect


def test_long_hash_does_not_hang() -> None:
    """Regression: the FQDN regex must be linear-time.

    A 64-char SHA-256 reaches the FQDN check before HASH in the eval order.
    Ported verbatim from Go's RE2 pattern, the nested-quantifier label group
    backtracks exponentially on a long unbroken alphanumeric run and never
    returns. Classify a hash on a worker thread with a hard timeout so a
    re-introduced catastrophic backtrack fails the test instead of wedging the
    whole suite.
    """
    import concurrent.futures

    long_hash = "0e2fc59194659497c8d0aec1762add1324ad2e02549bb3e41d58ca8f39e14843"
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(Observables().get_type, long_hash)
        try:
            result = future.result(timeout=5)
        except concurrent.futures.TimeoutError:  # pragma: no cover
            pytest.fail("Observables.get_type hung on a SHA-256 hash (FQDN regex backtracking)")
    assert result == "hash"
