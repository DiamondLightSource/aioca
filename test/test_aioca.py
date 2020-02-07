import asyncio
import socket
from dataclasses import dataclass
from pathlib import Path

import pytest

from aioca import caget

SOFT_RECORDS = Path(__file__).parent / "soft_records.db"


@dataclass
class IOC:
    pv_prefix: str
    process: asyncio.subprocess.Process


@pytest.fixture
async def ioc():
    # Get something reasonably unique for the PV prefix
    pv_prefix = socket.gethostname().split(".")[0]
    process = await asyncio.create_subprocess_shell(
        f"softIoc -m P={pv_prefix} -d {SOFT_RECORDS}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    while True:
        line = await process.stdout.readline()
        if "complete" in line.decode():
            break
    yield IOC(pv_prefix, process)
    await process.communicate(b"exit")


def my_func(x: int) -> int:
    return x



@pytest.mark.asyncio
async def test_get_pv(ioc: IOC):
    value = await caget(f"{ioc.pv_prefix}longout")
    assert 42 == value
    assert my_func("s") == "s"
