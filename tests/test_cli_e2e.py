import subprocess
from pathlib import Path


def _run_cli(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["waveos", *args],
        cwd=cwd,
        check=True,
    )


def test_cli_end_to_end(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    demo_dir = tmp_path / "demo_data"
    out_dir = tmp_path / "out"

    _run_cli(["sim", "--out", str(demo_dir)], cwd=repo_root)
    _run_cli(["baseline", "--in", str(demo_dir / "baseline")], cwd=repo_root)
    _run_cli(
        [
            "run",
            "--in",
            str(demo_dir / "run"),
            "--baseline",
            str(demo_dir / "baseline"),
            "--out",
            str(out_dir),
        ],
        cwd=repo_root,
    )
    _run_cli(["report", "--in", str(out_dir)], cwd=repo_root)

    assert (out_dir / "health_summary.json").exists()
    assert (out_dir / "events.jsonl").exists()
    assert (out_dir / "report.html").exists()
