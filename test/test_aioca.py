import asyncio
import socket
from dataclasses import dataclass
from pathlib import Path

import pytest

from aioca import caget, ca_nothing, camonitor, caput

SOFT_RECORDS = Path(__file__).parent / "soft_records.db"


@dataclass
class IOC:
    pv_prefix: str
    process: asyncio.subprocess.Process

    async def stop(self):
        await self.process.communicate(b"exit")


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
    ioc = IOC(pv_prefix, process)
    yield ioc
    await ioc.stop()


@pytest.mark.asyncio
async def test_get_pv(ioc: IOC):
    value = await caget(f"{ioc.pv_prefix}longout")
    assert 42 == value


@pytest.mark.asyncio
async def test_non_existant(ioc: IOC):
    pv = ioc.pv_prefix + "ne"
    with pytest.raises(ca_nothing) as cm:
        await caget(pv, timeout=0.1)

    assert f"ca_nothing('{pv}', 80)" == repr(cm.value)
    assert f"{pv}: User specified timeout on IO operation expired" == str(cm.value)
    assert False is bool(cm.value)
    with pytest.raises(TypeError):
        for _ in cm.value:
            pass


@pytest.mark.asyncio
async def test_monitor(ioc: IOC):
    pv = ioc.pv_prefix + "longout"
    values = []

    def callback(value):
        values.append(value)

    m = await camonitor(pv, callback, notify_disconnect=True)

    # Wait for connection
    while not values:
        await asyncio.sleep(0.1)
    await caput(pv, 43, wait=True)
    await caput(pv, 44, wait=True)
    await ioc.stop()

    m.close()

    assert 4 == len(values)
    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]

