import asyncio
import random
import string
from dataclasses import dataclass
from pathlib import Path

import pytest
from epicscorelibs.ca import cadef

from aioca import ca_nothing, caget, camonitor, caput, connect

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
    pv_prefix = "".join(random.choice(string.ascii_uppercase) for _ in range(12))
    process = await asyncio.create_subprocess_shell(
        f"python -m epicscorelibs.ioc -m P={pv_prefix} -d {SOFT_RECORDS}",
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


# All test coroutines will be treated as marked.
pytestmark = pytest.mark.asyncio


async def test_get_pv(ioc: IOC):
    pv = f"{ioc.pv_prefix}longout"
    value = await caget(pv)
    assert 42 == value


async def test_caput(ioc: IOC):
    pv = f"{ioc.pv_prefix}longout"
    await caput(pv, 43)
    value = await caget(pv)
    assert 43 == value


async def test_caput_wait(ioc: IOC):
    pv = f"{ioc.pv_prefix}longout"
    await caput(pv, 44, wait=True)
    value = await caget(pv)
    assert 44 == value


async def test_caput_callback(ioc: IOC):
    pv = f"{ioc.pv_prefix}longout"
    e = asyncio.Event()
    await caput(pv, 45, callback=lambda _: e.set())
    await asyncio.wait_for(e.wait(), timeout=1.0)
    assert e.is_set()


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


async def test_monitor(ioc: IOC):
    pv = f"{ioc.pv_prefix}longout"
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

    await asyncio.sleep(0.1)
    m.close()

    assert 4 == len(values)
    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]


async def test_connect(ioc: IOC):
    pv = f"{ioc.pv_prefix}longout"
    conn = await connect(pv)
    assert type(conn) == ca_nothing


async def test_ca_nothing_dunder_methods():
    good = ca_nothing("all ok")
    assert good
    with pytest.raises(TypeError):
        for x in good:
            pass
    bad = ca_nothing("not all ok", cadef.ECA_DISCONN)
    assert not bad
    with pytest.raises(TypeError):
        for x in bad:
            pass
