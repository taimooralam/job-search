from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def build_remote_launcher_script(
    *,
    command_tokens: list[str],
    log_path: str,
    pid_path: str,
    workdir: str = "/tmp",
    startup_check_seconds: int = 5,
) -> str:
    if not command_tokens:
        raise ValueError("command_tokens must not be empty")
    quoted_command = shlex.join(command_tokens)
    quoted_log_path = shlex.quote(log_path)
    quoted_pid_path = shlex.quote(pid_path)
    quoted_workdir = shlex.quote(workdir)
    startup_delay = max(int(startup_check_seconds), 0)
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f"cd {quoted_workdir}",
            f"rm -f {quoted_pid_path}",
            f": > {quoted_log_path}",
            f"setsid nohup {quoted_command} > {quoted_log_path} 2>&1 < /dev/null &",
            "pid=$!",
            f"printf '%s\\n' \"$pid\" > {quoted_pid_path}",
            f"sleep {startup_delay}",
            "if ! kill -0 \"$pid\" 2>/dev/null; then",
            "  echo \"launcher startup check failed: detached process exited before initial poll\" >&2",
            f"  cat {quoted_log_path} >&2 || true",
            "  exit 1",
            "fi",
            "printf '%s\\n' \"$pid\"",
            "",
        ]
    )


def _run_checked(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.stdout.strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a remote wrapper and launch a detached VPS command with a real PID file.",
    )
    parser.add_argument("--host", required=True, help="SSH destination, e.g. root@72.61.92.76")
    parser.add_argument("--launcher-name", required=True, help="Stable name used for /tmp launcher and artifacts")
    parser.add_argument("--log-path", required=True, help="Remote log path, typically /tmp/<run>.out")
    parser.add_argument("--pid-path", required=True, help="Remote pid path, typically /tmp/<run>.pid")
    parser.add_argument(
        "--workdir",
        default="/tmp",
        help="Remote working directory for the launcher wrapper. Defaults to /tmp.",
    )
    parser.add_argument(
        "--startup-check-seconds",
        type=int,
        default=5,
        help="Seconds to wait before verifying the detached process is still alive. Defaults to 5.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to launch after '--', e.g. -- /root/scout-cron/.venv/bin/python -u ...",
    )
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a detached command must be provided after '--'")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    remote_launcher_path = f"/tmp/{args.launcher_name}.sh"
    script_text = build_remote_launcher_script(
        command_tokens=args.command,
        log_path=args.log_path,
        pid_path=args.pid_path,
        workdir=args.workdir,
        startup_check_seconds=args.startup_check_seconds,
    )

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, suffix=".sh") as handle:
        handle.write(script_text)
        local_launcher_path = Path(handle.name)

    try:
        _run_checked(["scp", str(local_launcher_path), f"{args.host}:{remote_launcher_path}"])
        _run_checked(["ssh", args.host, "chmod", "+x", remote_launcher_path])
        launched_pid = _run_checked(["ssh", "-tt", args.host, "bash", remote_launcher_path]).strip()
        sys.stdout.write(f"{launched_pid}\n")
        return 0
    finally:
        local_launcher_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
