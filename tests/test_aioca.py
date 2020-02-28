import asyncio
import gc
import queue
import random
import string
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Tuple

import pytest
from epicscorelibs.ca import cadef

from aioca import (
    FORMAT_CTRL,
    AugmentedValue,
    Subscription,
    ca_info,
    ca_nothing,
    caget,
    cainfo,
    camonitor,
    caput,
    connect,
    run,
)

SOFT_RECORDS = Path(__file__).parent / "soft_records.db"

PV_PREFIX = "".join(random.choice(string.ascii_uppercase) for _ in range(12))
# An int that starts as 42
LONGOUT = PV_PREFIX + "longout"
# A string that starts as "me"
SI = PV_PREFIX + "si"
# A PV that increments every 0.5s
TICKING = PV_PREFIX + "ticking"
# A non-existant pv
NE = PV_PREFIX + "ne"
# A PV with bad EGU field
BAD_EGUS = PV_PREFIX + "bad_egus"
# A Waveform PV
WAVEFORM = PV_PREFIX + "waveform"


@pytest.fixture
async def ioc():
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "epicscorelibs.ioc",
            "-d",
            SOFT_RECORDS,
            "-m",
            f"P={PV_PREFIX}",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    while True:
        line = process.stdout.readline()
        if "complete" in line:
            break
    yield process
    try:
        process.communicate("exit")
    except ValueError:
        # Someone else already called communicate
        pass


@pytest.mark.asyncio
async def test_connect_one_pv(ioc: subprocess.Popen) -> None:
    conn = await connect(LONGOUT)
    assert type(conn) == ca_nothing


@pytest.mark.asyncio
async def test_cainfo_one_pv(ioc: subprocess.Popen) -> None:
    conn = await cainfo(LONGOUT)
    assert type(conn) == ca_info
    assert conn.ok is True
    assert conn.name == LONGOUT
    assert conn.state_strings[conn.state] == "connected"
    assert conn.host.endswith(":5064")
    assert conn.read is True
    assert conn.write is True
    assert conn.count == 1
    assert conn.datatype_strings[conn.datatype] == "long"
    ioc.communicate("exit")
    await asyncio.sleep(0.1)
    conn = await cainfo(LONGOUT, wait=False)
    assert conn.datatype == 7  # no access
    assert (
        str(conn)
        == f"""{LONGOUT}:
    State: previously connected
    Host: <disconnected>
    Access: False, False
    Data type: no access
    Count: 0"""
    )


@pytest.mark.asyncio
async def test_cainfo_two_pvs(ioc: subprocess.Popen) -> None:
    conn = await cainfo([LONGOUT, SI])
    assert conn[0].datatype == 5  # long
    assert conn[1].datatype == 0  # string


@pytest.mark.asyncio
async def test_get_pv(ioc: subprocess.Popen) -> None:
    value = await caget(LONGOUT)
    assert 42 == value


@pytest.mark.asyncio
async def test_get_two_pvs(ioc: subprocess.Popen) -> None:
    value = await caget([LONGOUT, SI])
    assert [42, "me"] == value


@pytest.mark.asyncio
async def test_get_pv_with_bad_egus(ioc: subprocess.Popen) -> None:
    value = await caget(BAD_EGUS, format=FORMAT_CTRL)
    assert 32 == value
    assert value.units == "\ufffd"  # unicode REPLACEMENT CHARACTER


@pytest.mark.asyncio
async def test_get_waveform_pv(ioc: subprocess.Popen) -> None:
    value = await caget(WAVEFORM)
    assert len(value) == 0
    await caput(WAVEFORM, [1, 2, 3, 4])
    assert pytest.approx([1, 2, 3, 4]) == await caget(WAVEFORM)
    assert pytest.approx([1, 2, 3, 4, 0]) == await caget(WAVEFORM, count=6)
    assert pytest.approx([1, 2, 3, 4, 0]) == await caget(WAVEFORM, count=-1)
    assert pytest.approx([1, 2]) == await caget(WAVEFORM, count=2)


@pytest.mark.asyncio
async def test_caput(ioc: subprocess.Popen) -> None:
    await caput(LONGOUT, 43)
    value = await caget(LONGOUT)
    assert 43 == value


@pytest.mark.asyncio
async def test_caput_two_pvs_same_value(ioc: subprocess.Popen) -> None:
    await caput([LONGOUT, SI], 43)
    value = await caget([LONGOUT, SI])
    assert [43, "43"] == value
    await caput([LONGOUT, SI], "44")
    value = await caget([LONGOUT, SI])
    assert [44, "44"] == value


@pytest.mark.asyncio
async def test_caput_two_pvs_different_value(ioc: subprocess.Popen) -> None:
    await caput([LONGOUT, SI], [44, "blah"])
    value = await caget([LONGOUT, SI])
    assert [44, "blah"] == value


@pytest.mark.asyncio
async def test_caput_wait(ioc: subprocess.Popen) -> None:
    await caput(LONGOUT, 44, wait=True)
    value = await caget(LONGOUT)
    assert 44 == value


@pytest.mark.asyncio
async def test_caput_callback(ioc: subprocess.Popen) -> None:
    e = asyncio.Event()
    await caput(LONGOUT, 45, callback=lambda _: e.set())
    await asyncio.wait_for(e.wait(), timeout=1.0)
    assert e.is_set()


@pytest.mark.asyncio
async def test_caget_non_existent(ioc: subprocess.Popen) -> None:
    with pytest.raises(ca_nothing) as cm:
        await caget(NE, timeout=0.1)

    assert f"ca_nothing('{NE}', 80)" == repr(cm.value)
    assert f"{NE}: User specified timeout on IO operation expired" == str(cm.value)
    assert False is bool(cm.value)
    with pytest.raises(TypeError):
        for _ in cm.value:
            pass


@pytest.mark.asyncio
async def test_monitor(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    m = await camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    while not values:
        await asyncio.sleep(0.1)
    await caput(LONGOUT, 43, wait=True)
    await caput(LONGOUT, 44, wait=True)
    ioc.communicate("exit")

    await asyncio.sleep(0.1)
    m.close()

    assert 4 == len(values)
    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]


@pytest.mark.asyncio
async def test_monitor_two_pvs(ioc: subprocess.Popen) -> None:
    values: List[Tuple[AugmentedValue, int]] = []
    await caput(WAVEFORM, [1, 2])
    ms = await camonitor(
        [WAVEFORM, TICKING], lambda v, n: values.append((v, n)), count=-1
    )

    # Wait for connection
    while not values:
        await asyncio.sleep(0.1)

    assert values == [(pytest.approx([1, 2, 0, 0, 0]), 0), (0, 1)]
    values.clear()
    await asyncio.sleep(1.0)
    assert values == [(1, 1), (2, 1)]
    values.clear()

    for m in ms:
        m.close()
    ioc.communicate("exit")
    await asyncio.sleep(1.0)

    assert values == []


@pytest.mark.asyncio
async def test_long_monitor_callback(ioc: subprocess.Popen) -> None:
    raise ValueError()


@pytest.mark.asyncio
async def test_exception_raising_monitor_callback(ioc: subprocess.Popen) -> None:
    raise ValueError()

@pytest.mark.asyncio
async def test_camonitor_non_existent(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    m = await camonitor(NE, values.append, connect_timeout=0.1)
    try:
        assert len(values) == 0
        await asyncio.sleep(0.2)
        assert len(values) == 1
        assert not values[0].ok
    finally:
        m.close()


@pytest.mark.asyncio
async def test_monitor_gc(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    await camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    while not values:
        await asyncio.sleep(0.1)
    await caput(LONGOUT, 43, wait=True)
    gc.collect()
    await caput(LONGOUT, 44, wait=True)
    ioc.communicate("exit")
    await asyncio.sleep(0.1)

    # Check everything is there
    assert 4 == len(values)
    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]


async def monitor_for_a_bit(callback: Callable) -> Subscription:
    m = await camonitor(TICKING, callback, notify_disconnect=True)
    await asyncio.sleep(0.5)
    return m


def test_closing_event_loop(ioc: subprocess.Popen, capsys) -> None:
    def closed_messages(text):
        return [x for x in text.splitlines() if x.endswith("Event loop is closed")]

    q: queue.Queue = queue.Queue()
    m = run(monitor_for_a_bit(q.put))
    # We should have a single update and no errors
    assert q.qsize() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    time.sleep(1.0)
    # We should have 2 more updates that didn't make it to the queue
    # because loop closed
    assert q.qsize() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(closed_messages(captured.err)) == 2, captured.err

    m.close()
    time.sleep(1.0)
    # There should be no more updates
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    ioc.communicate("exit")
    time.sleep(0.1)
    # We should have one more error from the disconnect
    assert q.qsize() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(closed_messages(captured.err)) == 1, captured.err


def test_ca_nothing_dunder_methods():
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
