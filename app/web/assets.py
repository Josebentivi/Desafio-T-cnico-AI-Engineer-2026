from __future__ import annotations

import hashlib

from jinja2 import pass_context
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


@pass_context
def asset_url(context, path: str) -> str:
    request = context["request"]
    content = (request.app.state.static_dir / path).read_bytes()
    version = hashlib.sha256(content).hexdigest()[:16]
    return str(request.url_for("static", path=path).include_query_params(v=version))


class RevalidateBrowserCache:
    """Revalidate HTML and assets without buffering streaming responses."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"].removeprefix(scope.get("root_path", ""))

        async def send_with_cache_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if path.startswith("/static/") or headers.get("content-type", "").startswith(
                    "text/html"
                ):
                    headers["Cache-Control"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_cache_headers)
