from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

PUBLIC_KEY_URL = "https://alter-app-three.vercel.app/api/vault/bootstrap/public-key"
OUTPUT_PATH = Path("/tmp/alter-public-key.json")


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Fail closed instead of following a public-key endpoint redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_public_key(
    *,
    url: str = PUBLIC_KEY_URL,
    attempts: int = 12,
    sleep_seconds: float = 10,
    opener: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Fetch and validate the public sealing key without forwarding credentials."""
    client = opener or urllib.request.build_opener(NoRedirectHandler)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ALTER-GitHub-Bootstrap/1.0"},
        )
        try:
            with client.open(request, timeout=20) as response:
                if response.geturl() != url:
                    raise RuntimeError(
                        "ALTER public-key endpoint changed origin or redirected."
                    )
                record = json.loads(response.read().decode("utf-8"))
            _validate_public_key(record)
            return record
        except urllib.error.HTTPError as exc:
            propagation_404 = exc.code == 404 and attempt <= min(3, attempts)
            recoverable = exc.code in {408, 425, 429} or 500 <= exc.code <= 599
            if not (propagation_404 or recoverable):
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc

        if attempt < attempts:
            print(
                f"ALTER endpoint is not ready (attempt {attempt}/{attempts}); "
                f"retrying in {sleep_seconds:g} seconds."
            )
            sleep(sleep_seconds)

    raise RuntimeError(f"ALTER public-key endpoint did not become ready: {last_error}")


def _validate_public_key(record: Any) -> None:
    if not isinstance(record, dict):
        raise RuntimeError("Unexpected ALTER public-key response.")
    if (
        record.get("version") != 1
        or record.get("algorithm") != "X25519-HKDF-SHA256+A256GCM"
    ):
        raise RuntimeError("Unexpected ALTER public-key response.")
    if record.get("value_exposed") is not False:
        raise RuntimeError("ALTER public-key endpoint violated no-secret contract.")


def main() -> None:
    record = fetch_public_key()
    OUTPUT_PATH.write_text(json.dumps(record), encoding="utf-8")
    print("Fetched ALTER public sealing key; no private material was returned.")


if __name__ == "__main__":
    main()

