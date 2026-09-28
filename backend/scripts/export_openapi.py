"""Write the OpenAPI schema to docs/openapi.json (for frontend type generation).

Usage (from backend/):  python -m scripts.export_openapi
Frontend:               npx openapi-typescript ../docs/openapi.json -o src/api/schema.d.ts
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
