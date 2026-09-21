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


def test_unimplemented_command_names_its_phase():
    result = runner.invoke(app, ["export", "demo"])
    assert result.exit_code == 2
    assert "P10" in result.output
