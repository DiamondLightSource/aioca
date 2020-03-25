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
from epicscorelibs.ca import cadef, dbr

from aioca import (
    FORMAT_CTRL,
    AugmentedValue,
    Subscription,
    _catools,
    ca_info,
    ca_nothing,
    caget,
    cainfo,
    camonitor,
    caput,
    connect,
    run,
)

SOFT_RECORDS = str(Path(__file__).parent / "soft_records.db")

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
# A read only PV
RO = PV_PREFIX + "waveform.NELM"


def boom(value, *args):
    """Function for raising an error"""
    raise ValueError("Boom")


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
    assert isinstance(conn.host, str)
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
async def test_get_ne_pvs_no_throw(ioc: subprocess.Popen) -> None:
    values = await caget([WAVEFORM, NE], throw=False, timeout=0.5)
    assert [True, False] == [v.ok for v in values]
    assert pytest.approx([]) == values[0]
    ioc.communicate("exit")
    await asyncio.sleep(0.5)
    # Fake the channel still being connected so we get a Disconnect
    channel = _catools.get_channel(WAVEFORM)
    channel.on_ca_connect_(op=cadef.CA_OP_CONN_UP)
    values = await caget([WAVEFORM, NE], throw=False, timeout=0.1)
    assert [False, False] == [v.ok for v in values]
    assert [cadef.ECA_DISCONN, cadef.ECA_TIMEOUT] == [v.errorcode for v in values]
    with pytest.raises(ca_nothing):
        await caget(NE, timeout=0.1)
    with pytest.raises(cadef.Disconnected):
        await caget(WAVEFORM, timeout=0.1)


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
    assert isinstance(value, dbr.ca_array)
    await caput(WAVEFORM, [1, 2, 3, 4])
    assert pytest.approx([1, 2, 3, 4]) == await caget(WAVEFORM)
    assert pytest.approx([1, 2, 3, 4, 0]) == await caget(WAVEFORM, count=6)
    assert pytest.approx([1, 2, 3, 4, 0]) == await caget(WAVEFORM, count=-1)
    assert pytest.approx([1, 2]) == await caget(WAVEFORM, count=2)


@pytest.mark.asyncio
async def test_caput(ioc: subprocess.Popen) -> None:
    value = await caput(LONGOUT, 43, timeout=None)
    assert isinstance(value, ca_nothing)
    value = await caget(LONGOUT)
    assert 43 == value


@pytest.mark.asyncio
async def test_caput_on_ro_pv_fails(ioc: subprocess.Popen) -> None:
    with pytest.raises(cadef.CAException):
        await caput(RO, 43)
    result = await caput(RO, 43, throw=False)
    assert str(result).endswith("Write access denied")


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
async def test_caget_non_existent_and_good(ioc: subprocess.Popen) -> None:
    await caput(WAVEFORM, [1, 2, 3, 4])
    try:
        await caget([NE, WAVEFORM], timeout=1.0)
    except ca_nothing:
        # That's what we expected
        pass
    await asyncio.sleep(0.5)
    import gc

    gc.collect()
    x = [x for x in gc.get_objects() if isinstance(x, dbr.ca_array)]
    assert len(x) == 0


@pytest.mark.asyncio
async def test_monitor(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    m = camonitor(LONGOUT, values.append, notify_disconnect=True, connect_timeout=1.0)

    # Wait for connection
    while not values:
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)
    await caput(LONGOUT, 43, wait=True)
    await asyncio.sleep(0.1)
    await caput(LONGOUT, 44, wait=True)
    await asyncio.sleep(0.1)
    ioc.communicate("exit")

    await asyncio.sleep(0.1)
    m.close()

    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]


@pytest.mark.asyncio
async def test_monitor_with_failing_dbr(ioc: subprocess.Popen, capsys) -> None:
    values: List[AugmentedValue] = []
    m = camonitor(LONGOUT, values.append, notify_disconnect=True, connect_timeout=1.0)

    # Wait for connection
    while not values:
        await asyncio.sleep(0.1)

    assert values == [42]
    values.clear()

    m.dbr_to_value = boom
    assert m.state == m.OPEN
    await caput(LONGOUT, 43, wait=True)

    await asyncio.sleep(0.1)
    assert m.state == m.CLOSED
    assert values == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ValueError: Boom" in captured.err

    ioc.communicate("exit")
    await asyncio.sleep(0.1)
    m.close()
    await asyncio.sleep(0.1)

    assert values == []


@pytest.mark.asyncio
async def test_monitor_two_pvs(ioc: subprocess.Popen) -> None:
    values: List[Tuple[AugmentedValue, int]] = []
    await caput(WAVEFORM, [1, 2], wait=True)
    ms = camonitor([WAVEFORM, LONGOUT], lambda v, n: values.append((v, n)), count=-1)

    # Wait for connection
    while len(values) != 2:
        await asyncio.sleep(0.1)

    assert values == [(pytest.approx([1, 2, 0, 0, 0]), 0), (42, 1)]
    values.clear()
    await caput(LONGOUT, 11, wait=True)
    await asyncio.sleep(0.1)
    await caput(LONGOUT, 12, wait=True)
    await asyncio.sleep(0.1)
    assert values == [(11, 1), (12, 1)]
    values.clear()

    for m in ms:
        m.close()
    ioc.communicate("exit")
    await asyncio.sleep(1.0)

    assert values == []


@pytest.mark.asyncio
async def test_long_monitor_callback(ioc: subprocess.Popen) -> None:
    values = []

    async def cb(value):
        values.append(value)
        await asyncio.sleep(0.2)

    m = camonitor(LONGOUT, cb, connect_timeout=(time.time() + 0.5,))
    # Wait for connection, callling first cb
    while not values:
        await asyncio.sleep(0.01)
    # These two caputs happen during the sleep of the first cb, and are
    # squashed together for the second cb
    await caput(LONGOUT, 43)
    await caput(LONGOUT, 44)
    # Wait until everything has cleared and put in two more that will
    # be squashed together for the third
    await asyncio.sleep(0.5)
    await caput(LONGOUT, 45)
    await caput(LONGOUT, 46)
    # Block the event loop to make sure the caputs have triggered updates
    # without the callback running
    time.sleep(0.05)
    # Then a single one for the fourth
    await asyncio.sleep(0.1)
    await caput(LONGOUT, 47)
    # Only first three should have completed
    assert [42, 44, 46] == values
    values.clear()
    # Wait for the last to have started
    await asyncio.sleep(0.25)
    assert [47] == values
    values.clear()
    assert m.dropped_callbacks == 1
    # And then for it to be finished
    await asyncio.sleep(0.4)
    assert [] == values
    assert m.dropped_callbacks == 2
    # Then add another three and close before the cb can fire
    await caput(LONGOUT, 48)
    await caput(LONGOUT, 49)
    # Manually flush to make sure it goes
    cadef.ca_flush_io()
    # Block the event loop to make sure the caputs have triggered updates
    # without the callback running
    time.sleep(0.05)
    # Now close so that the callback finds the connection closed and doesn't fire
    m.close()
    await asyncio.sleep(0.2)
    assert [] == values
    assert m.dropped_callbacks == 2


@pytest.mark.asyncio
async def test_exception_raising_monitor_callback(
    ioc: subprocess.Popen, capsys
) -> None:
    m = camonitor(LONGOUT, boom)
    assert m.state == m.OPENING
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    # Wait for first update to come in and close the subscription
    await asyncio.sleep(0.5)
    assert m.state == m.CLOSED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ValueError: Boom" in captured.err

    # Check no more updates
    values: List[str] = []
    m.callback = values.append
    await caput(LONGOUT, 32)
    assert m.state == m.CLOSED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert len(values) == 0


@pytest.mark.asyncio
async def test_camonitor_non_existent(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    m = camonitor(NE, values.append, connect_timeout=0.2)
    try:
        assert len(values) == 0
        await asyncio.sleep(0.5)
        assert len(values) == 1
        assert not values[0].ok
    finally:
        m.close()


@pytest.mark.asyncio
async def test_monitor_gc(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    while not values:
        await asyncio.sleep(0.01)
    assert len(values) == 1
    await caput(LONGOUT, 43, wait=True)
    # Check the monitor survives a garbage collect
    gc.collect()
    await caput(LONGOUT, 44, wait=True)
    await asyncio.sleep(0.1)
    ioc.communicate("exit")
    await asyncio.sleep(0.2)

    # Check everything is there
    assert 4 == len(values)
    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]


async def monitor_for_a_bit(callback: Callable) -> Subscription:
    m = camonitor(TICKING, callback, notify_disconnect=True)
    await asyncio.sleep(0.6)
    return m


def test_closing_event_loop(ioc: subprocess.Popen, capsys) -> None:
    def closed_messages(text):
        return [x for x in text.splitlines() if x.endswith("Event loop is closed")]

    q: queue.Queue = queue.Queue()
    m = run(monitor_for_a_bit(q.put))
    # We should have a single update and no errors
    assert q.get_nowait() == 0
    assert q.get_nowait() == 1
    assert q.qsize() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    time.sleep(1.1)
    # We should have 2 more updates that didn't make it to the queue
    # because loop closed
    assert q.qsize() == 0
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
    assert q.qsize() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(closed_messages(captured.err)) == 1, captured.err


@pytest.mark.asyncio
async def test_value_event_raises():
    e = _catools.ValueEvent()
    e.set(ca_nothing("blah"))
    with pytest.raises(ca_nothing):
        await e.wait()


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
