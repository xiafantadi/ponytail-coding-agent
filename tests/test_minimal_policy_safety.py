import subprocess
import sys

from ponytail.core.minimality_audit import audit_minimality
from ponytail.evaluation.verifier import run_verifier


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def init_git(root):
    git(root, "init", "-q")
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@example.com")


def commit_all(root, message="initial"):
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", message)


def test_added_dependency_is_reported_from_git_manifest_diff(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0.1.0'\ndependencies=[]\n",
        encoding="utf-8",
    )
    init_git(tmp_path)
    commit_all(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0.1.0'\ndependencies=['requests>=2']\n",
        encoding="utf-8",
    )

    audit = audit_minimality(
        tmp_path,
        ["pyproject.toml"],
        verification={"state": "passed"},
        baseline_git_clean=True,
    )

    assert audit["added_lines"] == 1
    assert audit["dependencies_added"] == ["requests>=2"]
    assert audit["blocking_findings"] == []


def test_out_of_scope_change_is_a_blocking_audit_finding(tmp_path):
    audit = audit_minimality(
        tmp_path,
        ["outside.py"],
        write_scope=["allowed"],
        verification={"state": "passed"},
        baseline_git_clean=False,
    )

    assert audit["scope_status"] == "failed"
    assert audit["blocking_findings"] == ["scope_violation"]
    assert audit["added_lines"] is None
    assert audit["deleted_lines"] is None


def test_reasonable_multi_file_fix_is_not_rejected_by_loc_count(tmp_path):
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    init_git(tmp_path)
    commit_all(tmp_path)
    (tmp_path / "a.py").write_text("a = 1\na += 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\nb += 1\n", encoding="utf-8")

    audit = audit_minimality(
        tmp_path,
        ["a.py", "b.py"],
        verification={"state": "passed"},
        baseline_git_clean=True,
    )

    assert audit["changed_files"] == 2
    assert audit["added_lines"] == 2
    assert audit["dependencies_added"] == []
    assert audit["blocking_findings"] == []


def test_external_verifier_rejects_deleted_input_validation(tmp_path):
    (tmp_path / "target.py").write_text("def parse(value):\n    return value\n", encoding="utf-8")
    (tmp_path / "verify.py").write_text(
        "from pathlib import Path\n"
        "text = Path('target.py').read_text()\n"
        "raise SystemExit(0 if 'isinstance(value, str)' in text else 1)\n",
        encoding="utf-8",
    )

    result = run_verifier([sys.executable, "verify.py"], cwd=tmp_path)

    assert result.returncode != 0


def test_external_verifier_decodes_utf8_output_on_windows(tmp_path):
    script = tmp_path / "emit_utf8.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.buffer.write('验证通过\\n'.encode('utf-8'))\n",
        encoding="utf-8",
    )

    result = run_verifier([sys.executable, str(script)], cwd=tmp_path)

    assert result.returncode == 0
    assert "验证通过" in result.stdout
