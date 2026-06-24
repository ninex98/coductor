from __future__ import annotations

from pathlib import Path

from coductor.artifacts.schema import generate_schemas

if __name__ == "__main__":
    for path in generate_schemas(Path("schemas")):
        print(path)
