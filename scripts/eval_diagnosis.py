"""Golden-set evaluation of diagnosis quality.

Runs OpsPilot's diagnosis on a fixed set of realistic failures and reports:

* schema-valid rate   - the model returned usable structured output
* citation validity   - the top hypothesis cites at least one real fact
* category accuracy   - the top hypothesis has an acceptable root-cause category

This needs a real model (it is not part of the unit tests). Examples:

    python scripts/eval_diagnosis.py                       # default local model
    python scripts/eval_diagnosis.py --model qwen2.5:7b
    python scripts/eval_diagnosis.py --provider anthropic  # opt in to a cloud model
    python scripts/eval_diagnosis.py --markdown results.md
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from opspilot.exceptions import LLMError
from opspilot.llm import Deadline, LLMRouter
from opspilot.pipeline import AnalyzeOptions, run_analysis
from opspilot.settings import get_settings

CASES: list[dict] = [
    {
        "name": "python-missing-module",
        "expect": {"dependency"},
        "input": "Traceback (most recent call last):\n"
        '  File "app/main.py", line 2, in <module>\n'
        "    import redis\n"
        "ModuleNotFoundError: No module named 'redis'\n",
    },
    {
        "name": "node-module-not-found",
        "expect": {"dependency", "build"},
        "input": "node:internal/modules/cjs/loader:1080\n"
        "Error: Cannot find module 'express'\n"
        "Require stack:\n- /app/server.js\n",
    },
    {
        "name": "typescript-type-error",
        "expect": {"code_bug", "build"},
        "input": "src/app.ts:4:7 - error TS2322: Type 'string' is not assignable "
        "to type 'number'.\n\nFound 1 error in src/app.ts:4\n",
    },
    {
        "name": "postgres-connection-refused",
        "expect": {"database", "network", "external_service"},
        "input": "psycopg2.OperationalError: could not connect to server: "
        'Connection refused\n\tIs the server running on host "db" and accepting '
        "TCP/IP connections on port 5432?\n",
    },
    {
        "name": "redis-timeout",
        "expect": {"database", "network", "external_service", "resource_exhaustion"},
        "input": "2026-11-20 10:05:12 ERROR redis.exceptions.TimeoutError: Timeout "
        "reading from socket\n2026-11-20 10:05:40 ERROR redis.exceptions.TimeoutError: "
        "Timeout reading from socket\n",
    },
    {
        "name": "java-out-of-memory",
        "expect": {"resource_exhaustion"},
        "input": 'Exception in thread "main" java.lang.OutOfMemoryError: Java heap space\n'
        "\tat com.acme.Cache.load(Cache.java:88)\n",
    },
    {
        "name": "missing-env-var",
        "expect": {"configuration"},
        "input": "Traceback (most recent call last):\n"
        '  File "app/config.py", line 3, in <module>\n'
        '    DB_URL = os.environ["DATABASE_URL"]\n'
        "KeyError: 'DATABASE_URL'\n",
    },
    {
        "name": "permission-denied",
        "expect": {"permissions", "configuration"},
        "input": "PermissionError: [Errno 13] Permission denied: '/var/log/app/app.log'\n",
    },
    {
        "name": "python-syntax-error",
        "expect": {"code_bug", "build"},
        "input": '  File "app/main.py", line 10\n    def handler(:\n'
        "                ^\nSyntaxError: invalid syntax\n",
    },
    {
        "name": "go-nil-pointer",
        "expect": {"code_bug"},
        "input": "panic: runtime error: invalid memory address or nil pointer dereference\n"
        "[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0x4a2b3c]\n\n"
        "goroutine 1 [running]:\nmain.handler(...)\n\t/app/main.go:27 +0x1c\n",
    },
    {
        "name": "upstream-503",
        "expect": {"external_service", "network"},
        "input": "2026-11-20 10:05:13 ERROR upstream payments-api returned 503 Service "
        "Unavailable (3 retries exhausted)\n",
    },
    {
        "name": "disk-full",
        "expect": {"resource_exhaustion"},
        "input": "OSError: [Errno 28] No space left on device: '/tmp/upload_123'\n",
    },
]


def evaluate(provider: str | None, model: str | None) -> tuple[list[dict], str]:
    settings = get_settings(provider=provider, model=model, deadline=600)
    rows = []
    label = ""
    for case in CASES:
        router = LLMRouter(settings, deadline=Deadline(settings.deadline))
        if not router.ready():
            sys.exit("No permitted provider is ready; run 'opspilot doctor'.")
        with tempfile.TemporaryDirectory() as project:
            started = time.monotonic()
            row = {"name": case["name"], "expect": sorted(case["expect"])}
            try:
                result = run_analysis(
                    AnalyzeOptions(
                        project_root=project,
                        build_output=case["input"],
                        build_source="eval",
                        suggest_fixes=False,
                    ),
                    router,
                )
                top = (
                    (result.diagnosis.hypotheses or [None])[0]
                    if result.diagnosis
                    else None
                )
                row.update(
                    valid=result.diagnosis is not None,
                    cited=bool(top and top.supported),
                    category=top.category if top else "-",
                    correct=bool(top and top.category in case["expect"]),
                    cause=top.cause if top else "",
                )
                if result.llm:
                    label = f"{result.llm.provider} / {result.llm.model}"
            except LLMError as e:
                row.update(
                    valid=False,
                    cited=False,
                    category="error",
                    correct=False,
                    cause=str(e)[:80],
                )
            row["seconds"] = round(time.monotonic() - started, 1)
        rows.append(row)
        mark = "ok " if row["correct"] else "MISS"
        print(
            f"[{mark}] {row['name']:<28} {row['category']:<20} {row['seconds']:>5}s",
            flush=True,
        )
    return rows, label


def summary(rows: list[dict]) -> dict[str, str]:
    n = len(rows)

    def pct(key: str) -> str:
        hits = sum(1 for r in rows if r[key])
        return f"{hits}/{n} ({100 * hits / n:.0f}%)"

    return {
        "schema-valid": pct("valid"),
        "top hypothesis cites a real fact": pct("cited"),
        "category accuracy": pct("correct"),
    }


def to_markdown(rows: list[dict], label: str) -> str:
    lines = [f"### {label}", ""]
    lines += [f"- **{k}:** {v}" for k, v in summary(rows).items()]
    median = sorted(r["seconds"] for r in rows)[len(rows) // 2]
    lines += [f"- **median time per case:** {median}s", ""]
    lines += [
        "| Case | Expected | Got | Cites a fact | Top hypothesis |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        cause = r["cause"].replace("|", "/")[:90]
        lines.append(
            f"| {r['name']} | {', '.join(r['expect'])} | {r['category']}"
            f"{'' if r['correct'] else ' ✗'} | {'yes' if r['cited'] else 'no'} | {cause} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--markdown", help="write results as Markdown to this file")
    args = parser.parse_args()
    rows, label = evaluate(args.provider, args.model)
    print()
    for key, value in summary(rows).items():
        print(f"{key}: {value}")
    if args.markdown:
        Path(args.markdown).write_text(to_markdown(rows, label), encoding="utf-8")


if __name__ == "__main__":
    main()
