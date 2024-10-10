import subprocess
import sys

from aioca import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "aioca", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
