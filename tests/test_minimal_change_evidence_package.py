import csv
import json

from scripts.package_minimal_change_evidence import package_evidence


def test_evidence_package_redacts_provider_and_local_paths(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "public"
    run_dir = tmp_path / "raw-run"
    source.mkdir()
    run_dir.mkdir()
    private_url = "https://private.example.test/v1"
    trace_path = run_dir / "trace.jsonl"
    report_path = run_dir / "report.json"
    patch_path = run_dir / "patch.diff"
    trace_path.write_text(
        json.dumps(
            {
                "event": "model_parsed",
                "completion_metadata": {"provider_base_url": private_url},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps({"status": "completed", "provider_base_url": private_url}),
        encoding="utf-8",
    )
    patch_path.write_text("--- a/app.py\n+++ b/app.py\n", encoding="utf-8")
    row = {
        "run_key": "task__minimal_policy__r1",
        "task_id": "task",
        "arm": "minimal_policy",
        "trace_path": str(trace_path),
        "report_path": str(report_path),
        "patch_path": str(patch_path),
        "usage": {"provider_base_url": private_url, "total_tokens": 10},
    }
    (source / "manifest.json").write_text(
        json.dumps({"provider_profile": "openai", "rows": [row]}), encoding="utf-8"
    )
    with (source / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=row)
        writer.writeheader()
        writer.writerow({**row, "usage": json.dumps(row["usage"])})
    (source / "summary.json").write_text('{"passed": 1}\n', encoding="utf-8")
    (source / "report.md").write_text(
        f"provider: {private_url}\npath: {tmp_path}\n", encoding="utf-8"
    )

    package_evidence(
        source,
        output,
        [("benefit", "task__minimal_policy__r1")],
        repo_root=tmp_path,
    )

    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file()
    )
    assert private_url not in public_text
    assert str(tmp_path) not in public_text
    assert "<redacted>" in public_text
    assert (output / "sample-runs" / "benefit" / "trace-excerpt.jsonl").is_file()
