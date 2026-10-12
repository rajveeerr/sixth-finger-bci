from typer.testing import CliRunner

from sixthfinger.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("doctor", "data", "epochs", "run", "export"):
        assert name in result.output


def test_doctor_runs():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "accelerator" in result.output


def test_export_demo_is_a_command():
    result = runner.invoke(app, ["export", "demo", "--help"])
    assert result.exit_code == 0
    assert "demo bundle" in result.output
