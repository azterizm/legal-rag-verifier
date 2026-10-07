"""Check the built wheel ships code only and declares no runtime dependencies.

Usage: python scripts/check_wheel.py DIST_DIR

The wheel must contain the ``legal_rag_verifier`` package and its ``.dist-info``
directory and nothing else: scripts, batteries, results, data and tests stay out of it.
"""

from __future__ import annotations

import sys
import zipfile
from email.parser import Parser
from pathlib import Path

PACKAGE = "legal_rag_verifier"


def check_wheel(wheel: Path) -> list[str]:
    """Return a list of problems found in ``wheel`` (empty when it is clean)."""
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        dist_info = [n for n in names if n.split("/", 1)[0].endswith(".dist-info")]
        stray = [n for n in names if n.split("/", 1)[0] not in {PACKAGE} and n not in dist_info]
        problems.extend(f"unexpected file in wheel: {n}" for n in stray)
        if f"{PACKAGE}/py.typed" not in names:
            problems.append("py.typed marker missing")
        metadata_name = next((n for n in dist_info if n.endswith("/METADATA")), None)
        if metadata_name is None:
            problems.append("METADATA missing")
        else:
            metadata = Parser().parsestr(zf.read(metadata_name).decode("utf-8"))
            problems.extend(
                f"runtime dependency declared: {req}"
                for req in metadata.get_all("Requires-Dist") or []
                if "extra ==" not in req
            )
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:  # noqa: PLR2004
        print(__doc__, file=sys.stderr)
        return 2
    wheels = sorted(Path(argv[1]).glob("*.whl"))
    if len(wheels) != 1:
        print(f"expected exactly one wheel in {argv[1]}, found {len(wheels)}", file=sys.stderr)
        return 1
    problems = check_wheel(wheels[0])
    for problem in problems:
        print(f"FAIL {wheels[0].name}: {problem}", file=sys.stderr)
    if not problems:
        print(f"OK {wheels[0].name}: code only, zero runtime dependencies")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
