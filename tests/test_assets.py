from __future__ import annotations

import hashlib
import os
import re
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.llm.fake import FakeLLM, FakeTurn
from app.main import create_app

ASSET_NAMES = {"app.css", "htmx.min.js", "shell.js", "chat.js"}


def static_urls(html: str) -> dict[str, str]:
    return {
        urlsplit(url).path.rsplit("/", 1)[-1]: url
        for url in re.findall(r'(?:src|href)="([^"]+)"', html)
        if "/static/" in urlsplit(url).path
    }


def test_pages_reference_content_versioned_assets_and_revalidate_html(conn, settings):
    app = create_app(settings, conn=conn, llm=FakeLLM([FakeTurn(text="Olá!")]))
    with TestClient(app) as client:
        page = client.get("/")
        assert page.headers["cache-control"] == "no-cache"
        urls = static_urls(page.text)
        assert set(urls) == ASSET_NAMES
        for url in urls.values():
            response = client.get(url)
            assert response.status_code == 200
            version = parse_qs(urlsplit(url).query)["v"]
            assert version == [hashlib.sha256(response.content).hexdigest()[:16]]
            assert response.headers["cache-control"] == "no-cache"
        assert static_urls(client.get("/").text) == urls
        dashboard = client.get("/ops")
        assert dashboard.headers["cache-control"] == "no-cache"
        assert static_urls(dashboard.text) == {
            name: url for name, url in urls.items() if name != "chat.js"
        }


def test_asset_url_changes_after_same_size_edit_without_restarting_app(
    conn, settings, tmp_path, monkeypatch
):
    for name in ASSET_NAMES:
        (tmp_path / name).write_bytes(b"old content")
    monkeypatch.setattr("app.main.STATIC_DIR", tmp_path)
    app = create_app(settings, conn=conn, llm=FakeLLM([]))
    with TestClient(app) as client:
        old_urls = static_urls(client.get("/").text)
        assert client.get(old_urls["app.css"]).content == b"old content"
        css = tmp_path / "app.css"
        previous_stat = css.stat()
        css.write_bytes(b"new content")
        os.utime(css, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns))

        new_urls = static_urls(client.get("/").text)
        assert new_urls["app.css"] != old_urls["app.css"]
        for name in ASSET_NAMES - {"app.css"}:
            assert new_urls[name] == old_urls[name]
        response = client.get(new_urls["app.css"])
        assert response.status_code == 200
        assert response.content == b"new content"


def test_static_conditional_requests_keep_revalidation_headers(conn, settings):
    app = create_app(settings, conn=conn, llm=FakeLLM([]))
    with TestClient(app) as client:
        urls = static_urls(client.get("/").text)
        for url in ["/static/app.css", urls["app.css"]]:
            initial = client.get(url)
            unchanged = client.get(url, headers={"If-None-Match": initial.headers["etag"]})
            assert unchanged.status_code == 304
            assert unchanged.content == b""
            assert unchanged.headers["cache-control"] == "no-cache"
