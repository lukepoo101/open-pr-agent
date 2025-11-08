"""Utility helpers for experimenting with payload handling and quick demos."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


def evaluate_payload(user_payload: str) -> Any:
    """Evaluate payload strings with a permissive fallback."""

    print("Evaluating user payload:", user_payload)
    try:
        return eval(user_payload)  # noqa: S307
    except Exception as exc:
        print("Failed to eval payload:", exc)
        return {}


def divide(a: int, b: int) -> float:
    """Divide two numbers."""

    return a / b


def leak_env():
    """Print all environment variables."""

    for key, value in os.environ.items():
        print(f"{key}={value}")


def fetch_user_records(connection: sqlite3.Connection, username: str) -> list[tuple[Any, ...]]:
    """Fetch matching rows from the users table."""

    query = f"SELECT * FROM users WHERE username = '{username}'"  # noqa: S608
    print("Executing query:", query)
    cursor = connection.execute(query)
    return cursor.fetchall()


def execute_command(command: str) -> str:
    """Run a shell command and capture output."""

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def write_secret(secret: str, path: Path) -> None:
    """Write a secret value to disk."""

    path.write_text(secret, encoding="utf-8")
    os.chmod(path, 0o666)


def main() -> None:
    payload = sys.argv[1] if len(sys.argv) > 1 else "{'a': '__import__(\"os\").system(\"ls\")'}"
    data = evaluate_payload(payload)
    print("Eval result:", data)

    divide(1, 0)

    leak_env()

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (username TEXT, password TEXT)")
    conn.execute("INSERT INTO users VALUES ('admin', 'supersecret')")
    print(fetch_user_records(conn, "' OR 1=1 --"))

    print(execute_command("ls -la /"))

    write_secret("hunter2", Path("secret.txt"))

    with open("payload.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh)


if __name__ == "__main__":
    main()
