import asyncio
import gc
import queue
import random
import string
import subprocess
import sys
import threading
import time
from asyncio.events import AbstractEventLoop
from pathlib import Path
from typing import Callable, List, Tuple, Union
from unittest.mock import patch

import pytest
from _pytest.unraisableexception import catch_unraisable_exception
from epicscorelibs.ca import cadef, dbr

from aioca import (
    FORMAT_CTRL,
    CAInfo,
    CANothing,
    Subscription,
    _catools,
    caget,
    cainfo,
    camonitor,
    caput,
    connect,
    get_channel_infos,
    purge_channel_caches,
    run,
)
from aioca.types import AugmentedValue

SOFT_RECORDS = str(Path(__file__).parent / "soft_records.db")

PV_PREFIX = "".join(random.choice(string.ascii_uppercase) for _ in range(12))
# An int that starts as 42
LONGOUT = PV_PREFIX + "longout"
# A string that starts as "me"
SI = PV_PREFIX + "si"
# A PV that increments every 0.5s
TICKING = PV_PREFIX + "ticking"
# A non-existent pv
NE = PV_PREFIX + "ne"
# A PV with bad EGU field
BAD_EGUS = PV_PREFIX + "bad_egus"
# A Waveform PV
WAVEFORM = PV_PREFIX + "waveform"
# A read only PV
RO = PV_PREFIX + "waveform.NELM"
# Longer test timeouts as GHA has slow runners on Mac
TIMEOUT = 10


@pytest.fixture
def ioc():
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "epicscorelibs.ioc",
            "-m",
            f"P={PV_PREFIX}",
            "-d",
            SOFT_RECORDS,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    yield process
    # close channel caches before the vent loop
    purge_channel_caches()
    try:
        process.communicate("exit")
    except ValueError:
        # Someone else already called communicate
        pass


def wait_for_ioc(ioc, timeout=TIMEOUT):
    start = time.time()
    while True:
        assert time.time() - start < timeout
        line = ioc.stdout.readline()
        if "complete" in line:
            return


@pytest.mark.asyncio
async def test_connect(ioc: subprocess.Popen) -> None:
    conn = await connect(LONGOUT, timeout=TIMEOUT)
    assert type(conn) is CANothing
    conn2 = await connect([SI, NE], throw=False, timeout=1.0)
    assert len(conn2) == 2
    assert type(conn2[0]) is CANothing
    assert conn2[0].ok
    assert type(conn2[1]) is CANothing
    assert not conn2[1].ok


@pytest.mark.asyncio
async def test_cainfo(ioc: subprocess.Popen) -> None:
    conn2 = await cainfo([WAVEFORM, SI], timeout=TIMEOUT)
    assert conn2[0].datatype == 1  # array
    assert conn2[1].datatype == 0  # string
    conn = await cainfo(LONGOUT)
    assert type(conn) is CAInfo
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
async def test_get_non_existent_pvs_no_throw(ioc: subprocess.Popen) -> None:
    wait_for_ioc(ioc)
    values = await caget([WAVEFORM, NE], throw=False, timeout=1.0)
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
    with pytest.raises(CANothing):
        await caget(NE, timeout=0.1)
    with pytest.raises(cadef.Disconnected):
        await caget(WAVEFORM, timeout=0.1)


# Ensure both lists and tuples of PVs can be handled.
@pytest.mark.asyncio
@pytest.mark.parametrize("pvs", ([LONGOUT, SI], (LONGOUT, SI)))
async def test_get_two_pvs(
    ioc: subprocess.Popen, pvs: Union[List[str], Tuple[str]]
) -> None:
    value = await caget(pvs, timeout=TIMEOUT)
    assert [42, "me"] == value


@pytest.mark.asyncio
async def test_get_pv_with_bad_egus(ioc: subprocess.Popen) -> None:
    value = await caget(BAD_EGUS, format=FORMAT_CTRL, timeout=TIMEOUT)
    assert 32 == value
    assert value.units == "\ufffd"  # unicode REPLACEMENT CHARACTER


@pytest.mark.asyncio
async def test_get_waveform_pv(ioc: subprocess.Popen) -> None:
    value = await caget(WAVEFORM, timeout=TIMEOUT)
    assert len(value) == 0
    assert isinstance(value, dbr.ca_array)
    await caput(WAVEFORM, [1, 2, 3, 4])
    assert pytest.approx([1, 2, 3, 4]) == await caget(WAVEFORM)
    assert pytest.approx([1, 2, 3, 4, 0]) == await caget(WAVEFORM, count=6)
    assert pytest.approx([1, 2, 3, 4, 0]) == await caget(WAVEFORM, count=-1)
    assert pytest.approx([1, 2]) == await caget(WAVEFORM, count=2)


@pytest.mark.asyncio
async def test_caput(ioc: subprocess.Popen) -> None:
    # Need to test the timeout=None branch, but wrap with wait_for in case it fails
    v1 = await asyncio.wait_for(caput(LONGOUT, 43, wait=True, timeout=None), TIMEOUT)
    assert isinstance(v1, CANothing)
    v2 = await caget(LONGOUT)
    assert 43 == v2


@pytest.mark.asyncio
async def test_caput_on_ro_pv_fails(ioc: subprocess.Popen) -> None:
    with pytest.raises(cadef.CAException):
        await caput(RO, 43, timeout=TIMEOUT)
    result = await caput(RO, 43, throw=False)
    assert str(result).endswith("Write access denied")


@pytest.mark.asyncio
@pytest.mark.parametrize("pvs", ([LONGOUT, SI], (LONGOUT, SI)))
async def test_caput_two_pvs_same_value(
    ioc: subprocess.Popen, pvs: Union[List[str], Tuple[str]]
) -> None:
    await caput(pvs, 43, timeout=TIMEOUT)
    value = await caget(pvs)
    assert [43, "43"] == value
    await caput(pvs, "44")
    value = await caget(pvs)
    assert [44, "44"] == value


@pytest.mark.asyncio
async def test_caput_two_pvs_different_value(ioc: subprocess.Popen) -> None:
    await caput([LONGOUT, SI], [44, "blah"], timeout=TIMEOUT)
    value = await caget([LONGOUT, SI])
    assert [44, "blah"] == value


@pytest.mark.asyncio
async def test_caget_non_existent() -> None:
    with pytest.raises(CANothing) as cm:
        await caget(NE, timeout=0.1)

    assert f"CANothing('{NE}', 80)" == repr(cm.value)
    assert f"{NE}: User specified timeout on IO operation expired" == str(cm.value)
    assert False is bool(cm.value)
    with pytest.raises(TypeError):
        for _ in cm.value:  # type: ignore
            pass


@pytest.mark.asyncio
async def test_caget_non_existent_and_good(ioc: subprocess.Popen) -> None:
    await caput(WAVEFORM, [1, 2, 3, 4], timeout=TIMEOUT)
    try:
        await caget([NE, WAVEFORM], timeout=1.0)
    except CANothing:
        # That's what we expected
        pass
    await asyncio.sleep(0.5)
    import gc

    gc.collect()
    x = [x for x in gc.get_objects() if isinstance(x, dbr.ca_array)]
    assert len(x) == 0


async def poll_length(array, gt=0, timeout=TIMEOUT):
    start = time.time()
    while not len(array) > gt:
        await asyncio.sleep(0.01)
        assert time.time() - start < timeout


@pytest.mark.asyncio
async def test_monitor(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    m = camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    await poll_length(values)
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
    m = camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    await poll_length(values)

    assert values == [42]
    values.clear()

    def boom(value, *args) -> None:
        """Function for raising an error"""
        raise ValueError("Boom")

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
    await caput(WAVEFORM, [1, 2], wait=True, timeout=TIMEOUT)
    ms = camonitor([WAVEFORM, LONGOUT], lambda v, n: values.append((v, n)), count=-1)

    # Wait for connection
    await poll_length(values, gt=1)

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
    wait_for_ioc(ioc)

    async def cb(value):
        values.append(value)
        await asyncio.sleep(0.4)

    m = camonitor(LONGOUT, cb, connect_timeout=(time.time() + 0.5,))
    # Wait for connection, calling first cb
    await poll_length(values)
    assert values == [42]
    assert m.dropped_callbacks == 0
    # These two caputs happen during the sleep of the first cb, and are
    # squashed together for the second cb
    await caput(LONGOUT, 43)
    await caput(LONGOUT, 44)
    # Check we get a dropped callback before the second cb fires
    await asyncio.sleep(0.2)
    assert [42] == values
    assert m.dropped_callbacks == 1
    # Wait until the second cb (which is dropped) has finished
    await asyncio.sleep(0.6)
    assert [42, 44] == values
    assert m.dropped_callbacks == 1
    values.clear()
    # Add another one and close before the cb can fire
    await caput(LONGOUT, 45)
    # Block the event loop to make sure the caput has triggered updates
    # without the callback running
    time.sleep(0.4)
    # Now close so that the callback finds the connection closed and doesn't fire
    m.close()
    await asyncio.sleep(0.4)
    assert [] == values
    assert m.dropped_callbacks == 1


@pytest.mark.asyncio
async def test_long_monitor_all_updates(ioc: subprocess.Popen) -> None:
    # Like above, but check all_updates gives us everything
    values = []
    wait_for_ioc(ioc)

    async def cb(value):
        values.append(value)
        await asyncio.sleep(0.4)

    m = camonitor(LONGOUT, cb, connect_timeout=(time.time() + 0.5,), all_updates=True)
    # Wait for connection, calling first cb
    await poll_length(values)
    assert values == [42]
    assert m.dropped_callbacks == 0
    # These two caputs happen during the sleep of the first cb,
    # they shouldn't be squashed as we ask for all_updates
    await caput(LONGOUT, 43)
    await caput(LONGOUT, 44)
    # Wait until the second cb has finished
    await asyncio.sleep(0.6)
    assert [42, 43] == values
    assert m.dropped_callbacks == 0
    # Wait until the third cb (which is not dropped) has finished
    await asyncio.sleep(0.6)
    assert [42, 43, 44] == values
    assert m.dropped_callbacks == 0


@pytest.mark.asyncio
async def test_exception_raising_monitor_callback(
    ioc: subprocess.Popen, capsys
) -> None:
    expected = [42]

    wait_for_ioc(ioc)
    m = camonitor(LONGOUT, lambda v: expected.remove(v))
    assert m.state == m.OPENING
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    # Wait for first update to come in and work
    await asyncio.sleep(0.5)
    assert expected == []

    # Make it trigger an error
    await caput(LONGOUT, 35)
    await asyncio.sleep(0.5)
    assert m.state == m.CLOSED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ValueError: list.remove(x): x not in list" in captured.err

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
async def test_async_exception_raising_monitor_callback(
    ioc: subprocess.Popen, capsys
) -> None:
    wait_for_ioc(ioc)

    async def boom_async(value) -> None:
        """Async function for raising an error"""
        raise ValueError("Boom")

    m = camonitor(LONGOUT, boom_async)
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
async def test_camonitor_non_existent() -> None:
    values: List[AugmentedValue] = []
    m = camonitor(NE, values.append, connect_timeout=0.2)
    try:
        assert len(values) == 0
        await asyncio.sleep(0.1)
        assert len(values) == 0
        await asyncio.sleep(0.5)
        assert len(values) == 1
        assert not values[0].ok
    finally:
        m.close()


@pytest.mark.asyncio
async def test_camonitor_non_existent_async() -> None:
    q: asyncio.Queue[AugmentedValue] = asyncio.Queue()
    m = camonitor(NE, q.put, connect_timeout=0.2)
    try:
        assert q.qsize() == 0
        await asyncio.sleep(0.1)
        assert q.qsize() == 0
        await asyncio.sleep(0.5)
        assert q.qsize() == 1
        assert not q.get_nowait().ok
    finally:
        m.close()


@pytest.mark.asyncio
async def test_monitor_gc(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    await poll_length(values)
    assert len(values) == 1
    await caput(LONGOUT, 43, wait=True)
    # Check the monitor survives a garbage collect
    await asyncio.sleep(0.1)
    gc.collect()
    await asyncio.sleep(0.1)
    await caput(LONGOUT, 44, wait=True)
    await asyncio.sleep(0.1)
    ioc.communicate("exit")
    await asyncio.sleep(0.2)

    # Check everything is there
    assert [42, 43, 44] == values[:3]
    assert [True, True, True, False] == [v.ok for v in values]


async def monitor_for_a_bit(callback: Callable, ioc) -> Subscription:
    wait_for_ioc(ioc)
    m = camonitor(TICKING, callback, notify_disconnect=True, all_updates=True)
    await asyncio.sleep(1.1)
    return m


def test_closing_event_loop(
    ioc: subprocess.Popen,
) -> None:
    with catch_unraisable_exception() as cm:
        q: queue.Queue = queue.Queue()
        m = run(monitor_for_a_bit(q.put, ioc))
        # Most of we get the initial value 0, then an update of 1
        # On travis sometimes the IOC is too late to startup and we
        # get 1 and 2
        updates = (q.get_nowait(), q.get_nowait())
        assert updates in [(0, 1), (1, 2)]
        assert q.qsize() == 0
        assert len(m.pending_values) == 0

        time.sleep(2.0)
        m.close()
        time.sleep(1.0)

        # We should have 2 more updates that didn't make it to the queue
        # because loop closed
        assert q.qsize() == 0
        assert len(m.pending_values) == 2

        # Check that there are no more updates
        time.sleep(2.0)
        assert len(m.pending_values) == 2

        ioc.communicate("exit")
        time.sleep(0.5)
        # There should be no more updates, but one error from the close message
        assert q.qsize() == 0
        assert len(m.pending_values) == 2

        # We expect there to be an unraiseable exception, caused by trying dispatch a
        # function to a closed event loop.
        # Detecting this is a bit hacky - pytest has code to catch unraiseable
        # exceptions, but no publicly declared API to examine them nor configuration
        # settings to do anything but ignore them.
        # So we use an internal API to examine it.
        assert cm.unraisable
        assert cm.unraisable.exc_value
        assert "Event loop is closed" in cm.unraisable.exc_value.args


@pytest.mark.asyncio
async def test_value_event_raises():
    e = _catools.ValueEvent()
    e.set(CANothing("blah"))
    with pytest.raises(CANothing):
        await e.wait()


def test_ca_nothing_dunder_methods():
    good = CANothing("all ok")
    assert good
    with pytest.raises(TypeError):
        for _x in good:  # type: ignore
            pass
    bad = CANothing("not all ok", cadef.ECA_DISCONN)
    assert not bad
    with pytest.raises(TypeError):
        for _x in bad:  # type: ignore
            pass


def test_run_forever(event_loop: AbstractEventLoop):
    asyncio.set_event_loop(event_loop)

    async def run_for_a_bit():
        while True:
            await asyncio.sleep(0.2)
            asyncio.get_event_loop().stop()

    start = time.time()
    run(run_for_a_bit(), forever=True)
    assert 0.2 < time.time() - start < 0.4


def test_import_in_a_different_thread(ioc: subprocess.Popen) -> None:
    wait_for_ioc(ioc)
    output = subprocess.check_output(
        [
            sys.executable,
            str(Path(__file__).parent / "import_in_different_thread.py"),
            LONGOUT,
        ]
    )
    assert output.strip() == b"42"


@pytest.mark.asyncio
async def test_read_pvs_from_different_threads(ioc: subprocess.Popen) -> None:
    wait_for_ioc(ioc)
    returned_values = []
    threads = []

    returned_values.append(await caget(LONGOUT, timeout=0.5))

    async def get_value():
        returned_values.append(await caget(LONGOUT, timeout=0.5))
        await asyncio.sleep(1)

    t = threading.Thread(
        target=asyncio.new_event_loop().run_until_complete, args=[get_value()]
    )
    threads.append(t)
    t.start()
    t.join()

    assert len(returned_values) == 2


@pytest.mark.asyncio
async def test_channel_connected(ioc: subprocess.Popen) -> None:
    values: List[AugmentedValue] = []
    m = camonitor(LONGOUT, values.append, notify_disconnect=True)

    # Wait for connection
    await poll_length(values)

    channels = get_channel_infos()
    assert len(channels) == 1

    channel = channels[0]
    # Initially the PV is connected and has one monitor
    assert channel.name == LONGOUT
    assert channel.connected
    assert channel.subscriber_count == 1

    ioc.communicate("exit")
    await asyncio.sleep(0.1)

    # After IOC exits the channel is disconnected but still has one monitor
    channel = get_channel_infos()[0]
    assert not channel.connected
    assert channel.subscriber_count == 1

    m.close()

    # Once the monitor is closed the subscription disappears
    channel = get_channel_infos()[0]
    assert channel.subscriber_count == 0


@patch("aioca._catools.cadef.ca_current_context")
def test_given_there_already_is_a_context_then_aioca_uses_it(existing_context):
    _catools._Context._teardown()
    _catools._Context._ensure_context()
    assert _catools._Context._ca_context == existing_context.return_value
