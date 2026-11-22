"""
Runs every scripts/try_*.py and fails (exit code 1) when any check fails.

    uv run --with httpx python -m bx_sch_4_nbs.scripts.run_try_scripts

Each try script prints "OK" or "ERRO" per check but always ends with exit code 0, so on its
own a CI server would never notice a failure. This runner reads their output instead:
a script fails when it prints "ERRO", crashes (Traceback) or prints no "OK" at all.
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent


def main() -> int:
    failed: list[str] = []
    total_ok = 0
    for path in sorted(SCRIPTS.glob("try_*.py")):
        module = f"bx_sch_4_nbs.scripts.{path.stem}"
        result = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = result.stdout + result.stderr
        lines = output.splitlines()
        ok = sum(1 for line in lines if line.startswith("OK"))
        errors = [line for line in lines if line.startswith("ERRO")]
        crashed = "Traceback" in output or result.returncode != 0
        total_ok += ok

        if errors or crashed or ok == 0:
            failed.append(path.stem)
            print(f"FAIL  {path.stem}  ok={ok} erro={len(errors)}{' crashed' if crashed else ''}")
            for line in (errors or lines)[-15:]:
                print(f"        {line}")
        else:
            print(f"ok    {path.stem}  ({ok})")

    print(f"\n{total_ok} checks passed; {len(failed)} script(s) failed{': ' + ', '.join(failed) if failed else ''}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
