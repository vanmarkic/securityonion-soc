from src.adapters.elasticsearch.client import ElasticClients, build_async_client


def test_build_client_no_auth_omits_basic_auth(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, hosts, **kwargs):
            captured["hosts"] = hosts
            captured.update(kwargs)

    monkeypatch.setattr("src.adapters.elasticsearch.client.AsyncElasticsearch", FakeClient)
    build_async_client("https://es:9200", "", "", verify_cert=True, timeout_ms=300000)
    assert captured["hosts"] == ["https://es:9200"]
    assert "basic_auth" not in captured
    assert captured["verify_certs"] is True  # verify_cert True -> verify_certs True
    assert captured["request_timeout"] == 300.0


def test_build_client_with_auth_and_verify_false(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, hosts, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.adapters.elasticsearch.client.AsyncElasticsearch", FakeClient)
    build_async_client("https://es:9200", "user", "pass", verify_cert=False, timeout_ms=120000)
    assert captured["basic_auth"] == ("user", "pass")
    assert captured["verify_certs"] is False  # InsecureSkipVerify = !verify_cert
    assert captured["request_timeout"] == 120.0


def test_clients_primary_and_remotes():
    clients = ElasticClients(primary="P", remotes=["R1", "R2"])
    assert clients.read_client == "P"          # reads/index/delete/fieldcaps/tasks use primary
    assert clients.all_clients == ["P", "R1", "R2"]  # update/ack fan out over all
