def test_saude(client):
    r = client.get("/saude/")
    assert r.status_code == 200
    assert r.content == b"ok"
