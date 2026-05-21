from __future__ import annotations

import json
import os
from argparse import Namespace
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from .cli import run_report


ROOT = Path(__file__).resolve().parents[1]


class MarketWatchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/generate":
            self.send_error(404, "Not found")
            return

        query = parse_qs(parsed.query)
        use_ai = query.get("ai", ["false"])[0].lower() == "true"
        as_of = query.get("as_of", [date.today().isoformat()])[0]
        output = ROOT / "reports" / f"market-{as_of}.md"

        try:
            load_dotenv(ROOT / ".env", override=True)
            if use_ai and not os.getenv("OPENAI_API_KEY"):
                self.send_json(
                    {
                        "ok": False,
                        "error": "OPENAI_API_KEY is not configured. AI analysis was not run.",
                    },
                    status=400,
                )
                return
            run_report(
                Namespace(
                    config=str(ROOT / "config" / "targets.yaml"),
                    as_of=as_of,
                    output=str(output),
                    no_ai=not use_ai,
                )
            )
            payload = json.loads((ROOT / "reports" / "latest.json").read_text(encoding="utf-8"))
            self.send_json(
                {
                    "ok": True,
                    "ai_requested": use_ai,
                    "ai_used": bool(payload.get("ai_used")),
                    "as_of": payload.get("as_of"),
                    "generated_at": payload.get("generated_at"),
                }
            )
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=500)

    def send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    load_dotenv(ROOT / ".env", override=True)
    server = ThreadingHTTPServer(("0.0.0.0", 8000), MarketWatchHandler)
    print("Market Watch server: http://localhost:8000/pwa/")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
