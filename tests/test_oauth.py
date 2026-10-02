from urllib.parse import parse_qs, urlparse

from yahoo_waiver_assistant.oauth import AUTH_URL, build_authorization_url


def test_authorization_url_contains_required_fields():
    url = build_authorization_url(
        "client-id", "https://localhost:8080/callback", "state-1"
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTH_URL
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://localhost:8080/callback"]
    assert params["response_type"] == ["code"]
    assert params["state"] == ["state-1"]
