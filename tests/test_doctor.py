from pathlib import Path

from app.main import main
from app.services.doctor import format_report, run_checks


def test_doctor_runs_and_reports(tmp_path: Path):
    results = run_checks(tmp_path)
    names = {r.name for r in results}
    assert {"Python", "Git", "Free disk", "RAM"} <= names
    report = format_report(results)
    assert "Python" in report


def test_config_command_succeeds(capsys):
    assert main(["config"]) == 0
    assert "Settings OK" in capsys.readouterr().out
