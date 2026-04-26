from scripts.ops.launch_vps_detached import build_remote_launcher_script


def test_build_remote_launcher_script_writes_real_pid_file() -> None:
    script = build_remote_launcher_script(
        command_tokens=[
            "/root/scout-cron/.venv/bin/python",
            "-u",
            "/root/scout-cron/scripts/vps_run_presentation_contract.py",
            "--job-id",
            "abc123",
        ],
        log_path="/tmp/presentation_contract_424.out",
        pid_path="/tmp/presentation_contract_424.pid",
    )

    assert "setsid nohup /root/scout-cron/.venv/bin/python -u /root/scout-cron/scripts/vps_run_presentation_contract.py --job-id abc123 > /tmp/presentation_contract_424.out 2>&1 < /dev/null &" in script
    assert "pid=$!" in script
    assert "printf '%s\\n' \"$pid\" > /tmp/presentation_contract_424.pid" in script
    assert ": > /tmp/presentation_contract_424.out" in script
    assert "sleep 5" in script
    assert "launcher startup check failed: detached process exited before initial poll" in script
    assert "if ! kill -0 \"$pid\" 2>/dev/null; then" in script
    assert script.endswith("\n")
