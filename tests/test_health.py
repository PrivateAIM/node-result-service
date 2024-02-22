def test_200_healthcheck(test_client):
    r = test_client.get("/healthz")

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
