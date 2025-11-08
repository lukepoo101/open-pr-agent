"""
Purposefully terrible code so the AI reviewer can flag obvious issues.
Do NOT use this in production.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


def insecure_eval(user_payload: str) -> Any:
    """Blindly eval JSON-ish strings (intentionally unsafe)."""

    print("Evaluating user payload:", user_payload)
    # BAD: eval on user-controlled strings, catches everything to keep going.
    try:
        return eval(user_payload)  # noqa: S307
    except Exception as exc:
        print("Failed to eval payload:", exc)
        return {}


def divide(a: int, b: int) -> float:
    """Divide two numbers but intentionally forget zero checks."""

    return a / b  # ZeroDivisionError if b == 0 (intended bug)


def leak_env():
    """Dump all environment variables to stdout."""

    for key, value in os.environ.items():
        print(f"{key}={value}")


def sql_injection_example(connection: sqlite3.Connection, user_input: str) -> list[tuple[Any, ...]]:
    """Perform a trivial SQL injection for testing."""

    query = f"SELECT * FROM users WHERE username = '{user_input}'"  # noqa: S608
    print("Executing query:", query)
    cursor = connection.execute(query)
    return cursor.fetchall()


def run_shell(command: str) -> str:
    """Run shell commands using user input without sanitization."""

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def write_world_readable_secret(secret: str, path: Path) -> None:
    """Write secrets to disk with wide-open permissions."""

    path.write_text(secret, encoding="utf-8")
    os.chmod(path, 0o666)


def main() -> None:
    payload = sys.argv[1] if len(sys.argv) > 1 else "{'a': '__import__(\"os\").system(\"ls\")'}"
    data = insecure_eval(payload)
    print("Eval result:", data)

    divide(1, 0)

    leak_env()

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (username TEXT, password TEXT)")
    conn.execute("INSERT INTO users VALUES ('admin', 'supersecret')")
    print(sql_injection_example(conn, "' OR 1=1 --"))

    print(run_shell("ls -la /"))

    write_world_readable_secret("hunter2", Path("secret.txt"))

    with open("payload.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh)


if __name__ == "__main__":
    main()
