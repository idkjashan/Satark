"""`python -m satark` — run the API with uvicorn (CONTRACTS §6; LLD §19)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "satark.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,
    )


if __name__ == "__main__":
    main()
