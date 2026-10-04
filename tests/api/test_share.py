"""POST /share (CONTRACTS §6; LLD §22.2)."""

from __future__ import annotations

from urllib.parse import unquote


async def test_share_redirects_with_text_and_url(client):
    resp = await client.post(
        "/share", data={"title": "WhatsApp", "text": "check this out", "url": "http://scam.example"}, follow_redirects=False
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/check?text=")
    assert unquote(location.removeprefix("/check?text=")) == "check this out http://scam.example"


async def test_share_text_only(client):
    resp = await client.post("/share", data={"text": "just text, no link"}, follow_redirects=False)
    assert resp.status_code == 303
    assert unquote(resp.headers["location"].removeprefix("/check?text=")) == "just text, no link"


async def test_share_truncated_to_4000_chars(client):
    resp = await client.post("/share", data={"text": "a" * 5000}, follow_redirects=False)
    decoded = unquote(resp.headers["location"].removeprefix("/check?text="))
    assert len(decoded) == 4000


async def test_share_ignores_files(client):
    resp = await client.post(
        "/share",
        data={"text": "hello"},
        files={"media": ("photo.jpg", b"\xff\xd8\xff" + b"\x00" * 20, "image/jpeg")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert unquote(resp.headers["location"].removeprefix("/check?text=")) == "hello"
