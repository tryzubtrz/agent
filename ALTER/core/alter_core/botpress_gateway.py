from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BotpressUnavailableError(RuntimeError):
    pass


class BotpressRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotpressGatewayStatus:
    configured: bool
    bot_id_configured: bool
    credential_configured: bool
    action: str = "alterThink"


class BotpressGateway:
    """Least-privilege runtime gateway for the ALTER reasoning specialist.

    The gateway intentionally targets one Botpress Runtime action only. It does
    not expose the Admin API and never includes secrets in raised errors.
    """

    DEFAULT_BOT_ID = "64f3490a-183a-47c5-b825-97210771822f"

    def __init__(
        self,
        *,
        token: str | None = None,
        bot_id: str | None = None,
        base_url: str = "https://api.botpress.cloud/v1/chat",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.token = (token if token is not None else os.getenv("BOTPRESS_RUNTIME_TOKEN", "")).strip()
        configured_bot_id = bot_id if bot_id is not None else os.getenv("BOTPRESS_BOT_ID", self.DEFAULT_BOT_ID)
        self.bot_id = configured_bot_id.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def status(self) -> BotpressGatewayStatus:
        return BotpressGatewayStatus(
            configured=bool(self.token and self.bot_id),
            bot_id_configured=bool(self.bot_id),
            credential_configured=bool(self.token),
        )

    def think(self, *, objective: str, context: str = "", mode: str = "normal") -> dict[str, Any]:
        if not self.token or not self.bot_id:
            raise BotpressUnavailableError("Botpress specialist credential is not configured in ALTER Core.")

        payload = {
            "type": "alterThink",
            "input": {
                "objective": objective,
                "context": context,
                "mode": mode,
            },
        }
        request = Request(
            f"{self.base_url}/actions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "x-bot-id": self.bot_id,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - fixed HTTPS host by default
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            # Never surface the response body because providers may include
            # sensitive operational details. The status code is sufficient.
            raise BotpressRuntimeError(f"Botpress Runtime API returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise BotpressRuntimeError("Botpress Runtime API is unreachable.") from exc

        try:
            parsed = json.loads(body)
            output = parsed["output"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise BotpressRuntimeError("Botpress Runtime API returned an invalid action response.") from exc

        if not isinstance(output, dict):
            raise BotpressRuntimeError("Botpress specialist output was not an object.")
        return output
