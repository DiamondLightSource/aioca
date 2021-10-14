import asyncio
import atexit
import collections
import ctypes
import functools
import inspect
import sys
import time
import traceback
from typing import (
    Any,
    Awaitable,
    Callable,
    Deque,
    Dict,
    Generic,
    List,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
    overload,
)

from epicscorelibs.ca import cadef, dbr

from .types import AugmentedValue, Count, Datatype, Dbe, Format, Timeout

T = TypeVar("T")
PVs = Union[List[str], Tuple[str, ...]]

DEFAULT_TIMEOUT = 5.0


class ValueEvent(Generic[T]):
    def __init__(self):
        self.value = None
        self._event = asyncio.Event()

    def set(self, value: Union[T, Exception] = None):
        self._event.set()
        self.value = value

    def clear(self):
        self._event.clear()
        self.value = None

    async def wait(self) -> T:
        if not self._event.is_set():
            await self._event.wait()
        if isinstance(self.value, Exception):
            raise self.value
        else:
            return self.value


class CANothing(Exception):
    """This value is returned as a success or failure indicator from `caput`,
    as a failure indicator from `caget`, and may be raised as an exception to
    report a data error on caget or caput with wait."""

    def __init__(self, name, errorcode=cadef.ECA_NORMAL):
        #: Name of the PV
        self.name: str = name
        #: True for successful completion, False for error code
        self.ok: int = errorcode == cadef.ECA_NORMAL
        #: ECA error code
        self.errorcode: int = errorcode

    def __repr__(self):
        return "CANothing(%r, %d)" % (self.name, self.errorcode)

    def __str__(self):
        return "%s: %s" % (self.name, cadef.ca_message(self.errorcode))

    def __bool__(self):
        return self.ok


def maybe_throw(async_function):
    """Function decorator for optionally catching exceptions.  Exceptions
    raised by the wrapped function are normally propagated unchanged, but if
    throw=False is specified as a keyword argument then the exception is
    transformed into an ordinary CANothing value!"""

    @functools.singledispatch
    async def throw_wrapper(
        pv, *args, timeout: Timeout = DEFAULT_TIMEOUT, throw=True, **kwargs
    ):
        awaitable = ca_timeout(async_function(pv, *args, **kwargs), pv, timeout)
        if throw:
            return await awaitable
        else:
            # We catch all the expected exceptions, converting them into
            # CANothing() objects as appropriate.  Any unexpected exceptions
            # will be raised anyway, which seems fair enough!
            try:
                return await awaitable
            except CANothing as error:
                return error
            except cadef.CAException as error:
                return CANothing(pv, error.status)
            except cadef.Disconnected:
                return CANothing(pv, cadef.ECA_DISCONN)

    # The singledispatch decorator makes a sync wrapper. We need it to be
    # async so it works with inspect.iscoroutine, so wrap it again
    @functools.wraps(async_function)
    async def call_wrapper(*args, **kwargs):
        return await throw_wrapper(*args, **kwargs)

    # But keep the register function and register a signature that includes
    # the extras we added
    call_wrapper.register = throw_wrapper.register
    original_sig = inspect.signature(async_function)
    throw_parameters = inspect.signature(throw_wrapper).parameters
    parameters = [
        *original_sig.parameters.values(),
        throw_parameters["timeout"],
        throw_parameters["throw"],
    ]
    call_wrapper.__signature__ = original_sig.replace(parameters=parameters)
    return call_wrapper


async def ca_timeout(awaitable: Awaitable[T], name: str, timeout: Timeout = None) -> T:
    """Wait for awaitable to complete, with timeout one of:
    None            Wait forever
    interval        Wait for this amount of seconds
    (deadline,)     Wait until this absolute timestamp
    Convert any timeouts into a CANothing timeout containing the pv name
    """
    if timeout is not None:
        # Convert (abstimeout,) to relative timeout for asyncio
        if isinstance(timeout, tuple):
            timeout = timeout[0] - time.time()
        try:
            result = await asyncio.wait_for(awaitable, timeout)
        except asyncio.TimeoutError as e:
            raise CANothing(name, cadef.ECA_TIMEOUT) from e
    else:
        result = await awaitable
    return result


def parallel_timeout(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Return kwargs with a suitable timeout for running in parallel"""
    if kwargs.get("throw", True):
        # told to throw, so remove the timeout as it will be done at the top level
        kwargs = dict(kwargs, timeout=None)
    return kwargs


async def in_parallel(
    awaitables: Sequence[Awaitable[T]], kwargs: Dict[str, Any]
) -> List[T]:
    if kwargs.get("throw", True):
        # timeout at this level, awaitables will not timeout themselves
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)
        results = await ca_timeout(asyncio.gather(*awaitables), "Multiple PVs", timeout)
    else:
        # timeout being done at the level of each awaitable
        results = await asyncio.gather(*awaitables)
    return list(results)


# ----------------------------------------------------------------------------
#   Channel object and cache


class Channel(object):
    """Wraps a single channel access channel object."""

    __slots__ = [
        "name",
        "__subscriptions",  # Set of listening subscriptions
        "__connect_event",  # Connection event used to notify changes
        "__event_loop",
        "_as_parameter_",  # Associated channel access channel handle
    ]

    @staticmethod
    @cadef.connection_handler
    def on_ca_connect(args):  # pragma: no cover
        """This routine is called every time the connection status of the
        channel changes.  This is called directly from channel access, which
        means that user callbacks should not be called directly."""

        self = cadef.ca_puser(args.chid)
        op = args.op
        self.__event_loop.call_soon_threadsafe(self.on_ca_connect_, op)

    def on_ca_connect_(self, op):
        assert op in [cadef.CA_OP_CONN_UP, cadef.CA_OP_CONN_DOWN]
        connected = op == cadef.CA_OP_CONN_UP

        if connected:
            # Trigger wakeup of all listeners
            self.__connect_event.set()
        else:
            self.__connect_event.clear()

        # Inform all the connected subscriptions
        for subscription in self.__subscriptions:
            subscription._on_connect(connected)

    def __init__(self, name, loop):
        """Creates a channel access channel with the given name."""
        self.name = name
        self.__subscriptions: Set[Subscription] = set()
        self.__connect_event = ValueEvent()
        self.__event_loop = loop

        chid = ctypes.c_void_p()
        cadef.ca_create_channel(
            name, self.on_ca_connect, ctypes.py_object(self), 0, ctypes.byref(chid)
        )
        # Setting this allows a channel object to autoconvert into the chid
        # when passed to ca_ functions.
        self._as_parameter_ = chid.value
        _flush_io()

    def _purge(self):
        """Forcible purge of channel.  As well as closing the channels,
        ensures that all subscriptions attached to the channel are also
        closed."""
        for subscription in list(self.__subscriptions):
            subscription.close()
        cadef.ca_clear_channel(self)
        del self._as_parameter_

    def _add_subscription(self, subscription):
        """Adds the given subscription to the list of receivers of connection
        notification."""
        self.__subscriptions.add(subscription)

    def _remove_subscription(self, subscription):
        """Removes the given subscription from the list of receivers."""
        self.__subscriptions.remove(subscription)

    async def wait(self):
        """Waits for the channel to become connected if not already connected."""
        await self.__connect_event.wait()


class ChannelCache(object):
    """A cache of all open channels.  If a channel is not present in the
    cache it is automatically opened.  The cache needs to be purged to
    ensure a clean shutdown."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.__channels: Dict[str, Channel] = {}
        self.loop = loop

    def get_channel(self, name: str) -> Channel:
        try:
            # When the channel already exists, just return that
            return self.__channels[name]
        except KeyError:
            # Have to create a new channel
            channel = Channel(name, self.loop)
            self.__channels[name] = channel
            return channel

    def purge(self):
        """Purges all the channels in the cache: closes them right now.  Will
        cause other channel access to fail, so only to be done on shutdown."""
        for channel in self.__channels.values():
            channel._purge()
        self.__channels.clear()


# ----------------------------------------------------------------------------
#   camonitor


class Subscription(object):
    """A Subscription object wraps a single channel access subscription, and
    notifies all updates through an event queue."""

    __slots__ = [
        "name",  # Name of the PV subscribed to
        "callback",  # The user callback function
        "dbr_to_value",  # Conversion from dbr
        "channel",  # The associated channel object
        "state",  # Whether the subscription is active
        "dropped_callbacks",  # How many values have been dropped without callback
        "_as_parameter_",  # Associated channel access subscription handle
        "all_updates",  # True iff all updates delivered without merging
        "notify_disconnect",  # Whether to report disconnect events
        "__values",  # Most recent updates from event handler
        "__lock",  # Taken while a callback is running
        "__event_loop",  # The event loop the caller created this from
        "__tasks",  # Tasks that have been spawned from within asyncio
    ]

    # Subscription state values:
    OPENING = 0  # Subscription not complete yet
    OPEN = 1  # Normally active
    CLOSED = 2  # Closed but not yet deleted

    # Mapping from format to event mask for default events
    __default_events = {
        dbr.FORMAT_RAW: cadef.DBE_VALUE,
        dbr.FORMAT_TIME: cadef.DBE_VALUE | cadef.DBE_ALARM,
        dbr.FORMAT_CTRL: cadef.DBE_VALUE | cadef.DBE_ALARM | cadef.DBE_PROPERTY,
    }

    @staticmethod
    @cadef.event_handler
    def __on_event(args):  # pragma: no cover
        """This is called each time the subscribed value changes.  As this is
        called asynchronously, a signal must be queued for later dispatching
        to the monitoring user."""
        self = args.usr

        try:
            assert (
                args.status == cadef.ECA_NORMAL
            ), f"Subscription {self.name} got bad status {args.status}"
            # Good data: extract value from the dbr. Note that this can fail
            self.__values.append(self.dbr_to_value(args.raw_dbr, args.type, args.count))
            # This signals update merging should occur
            value = None
        except Exception:
            # Something went wrong, insert it into the processing chain
            value = sys.exc_info()
        self.__event_loop.call_soon_threadsafe(self.__create_signal_task, value)

    def __create_signal_task(self, value):
        task = asyncio.ensure_future(self.__signal(value))
        self.__tasks.append(task)

    async def __signal(self, value):
        """Wrapper for performing callbacks safely: only performs the callback
        if the subscription is open and reports and handles any exceptions that
        might arise."""
        if self.state == self.CLOSED:
            # We have closed this subscription, don't callback on pending values
            return
        # Take the lock so two callbacks can't run at once
        async with self.__lock:
            if value is None:
                try:
                    # Consume a single value from the queue
                    value = self.__values.popleft()
                except IndexError:
                    # Deque has overflowed, count and return
                    self.dropped_callbacks += 1
                    return
            try:
                if isinstance(value, tuple):
                    # This should only happen if the asynchronous callback
                    # caught an exception for us to re-raise here.
                    raise value[1].with_traceback(value[2])
                else:
                    ret = self.callback(value)
                    if inspect.isawaitable(ret):
                        await ret
            except Exception:
                # We try and be robust about exceptions in handlers, but to
                # prevent a perpetual storm of exceptions, we close the
                # subscription after reporting the problem.
                print(
                    "Subscription %s callback raised exception" % self.name,
                    file=sys.stderr,
                )
                traceback.print_exc()
                print("Subscription %s closed" % self.name, file=sys.stderr)
                self.close()

    def _on_connect(self, connected):
        """This is called each time the connection state of the underlying
        channel changes.  It is called synchronously."""
        if not connected and self.notify_disconnect:
            # Channel has become disconnected: tell the subscriber.
            self.__create_signal_task(CANothing(self.name, cadef.ECA_DISCONN))

    def close(self):
        """Closes the subscription and releases any associated resources.
        Note that no further callbacks will occur on a closed subscription,
        not even callbacks currently queued for execution."""
        if self.state == self.OPEN:
            self.channel._remove_subscription(self)
            cadef.ca_clear_subscription(self)

        if not self.__event_loop.is_closed():
            _flush_io()
            for task in self.__tasks:
                task.cancel()

        self.state = self.CLOSED

    def __init__(
        self,
        name: str,
        callback: Callable[[Any], Union[None, Awaitable]],
        events: Dbe,
        datatype: Datatype,
        format: Format,
        count: Count,
        all_updates: bool,
        notify_disconnect: bool,
        connect_timeout: Timeout,
    ):
        self.name = name
        self.callback = callback
        self.notify_disconnect = notify_disconnect
        #: The number of updates that have been dropped as they happened
        #: while another callback was in progress
        self.dropped_callbacks: int = 0
        self.__event_loop = asyncio.get_event_loop()
        self.__values: Deque[AugmentedValue] = collections.deque(
            maxlen=0 if all_updates else 1
        )
        self.__lock = asyncio.Lock()

        # If events not specified then compute appropriate default corresponding
        # to the requested format.
        if events is None:
            events = self.__default_events[format]

        # Trigger channel connection if channel not already known.
        self.channel = get_channel(name)

        # Spawn the actual task of creating the subscription into the
        # background, as we may have to wait for the channel to become
        # connected.
        self.state = self.OPENING
        self.__tasks = [
            asyncio.ensure_future(
                self.__create_subscription(
                    events, datatype, format, count, connect_timeout
                )
            )
        ]

    async def __wait_for_channel(self, timeout):
        try:
            # Wait for channel to be connected
            await ca_timeout(self.channel.wait(), self.name, timeout)
        except CANothing as e:
            # Connection timeout.  Let the caller know and now just block
            # until we connect (if ever).  Note that in this case the caller
            # is notified even if notify_disconnect=False is set.
            self.__create_signal_task(e)
            await self.channel.wait()

    async def __create_subscription(
        self, events, datatype, format, count, connect_timeout
    ):
        """Creates the channel subscription with the specified parameters:
        event mask, datatype and format, array count.  Waits for the channel
        to become connected."""

        # Need to first wait for the channel to connect before we can do
        # anything else. This will either succeed, or wait forever, raising
        # if close() is called
        await self.__wait_for_channel(connect_timeout)

        self.state = self.OPEN

        # Treat a negative count as a request for the complete data
        if count < 0:
            count = cadef.ca_element_count(self.channel)

        # Connect to the channel to be kept informed of connection updates.
        self.channel._add_subscription(self)
        # Convert the datatype request into the subscription datatype.
        dbrcode, self.dbr_to_value = dbr.type_to_dbr(self.channel, datatype, format)

        # Finally create the subscription with all the requested properties
        # and hang onto the returned event id as our implicit ctypes
        # parameter.
        event_id = ctypes.c_void_p()
        cadef.ca_create_subscription(
            dbrcode,
            count,
            self.channel,
            events,
            self.__on_event,
            ctypes.py_object(self),
            ctypes.byref(event_id),
        )
        _flush_io()
        self._as_parameter_ = event_id.value


@overload
def camonitor(
    pv: str,
    callback: Callable[[Any], Union[None, Awaitable]],
    events: Dbe = ...,
    datatype: Datatype = ...,
    format: Format = ...,
    count: Count = ...,
    all_updates: bool = ...,
    notify_disconnect: bool = ...,
    connect_timeout: Timeout = ...,
) -> Subscription:
    ...  # pragma: no cover


@overload
def camonitor(
    pv: PVs,
    callback: Callable[[Any, int], Union[None, Awaitable]],
    events: Dbe = ...,
    datatype: Datatype = ...,
    format: Format = ...,
    count: Count = ...,
    all_updates: bool = ...,
    notify_disconnect: bool = ...,
    connect_timeout: Timeout = ...,
) -> List[Subscription]:
    ...  # pragma: no cover


def camonitor(
    pv,
    callback,
    events=None,
    datatype=None,
    format=dbr.FORMAT_RAW,
    count=0,
    all_updates=False,
    notify_disconnect=False,
    connect_timeout=None,
):
    """Create a subscription to one or more PVs

    Args:
        callback: Regular function or async function
        events: Bit-wise or of `Dbe` types to notify about. If not given the
            default mask depends on the requested format
        datatype: Override `Datatype` to a non-native type
        format: Request extra `Format` fields
        count: Request a specific element `Count` in an array
        all_updates: If True then every update received from channel
            access will trigger a callback, otherwise any updates received
            during the previous callback will be merged into the most recent
            value, incrementing `Subscription.dropped_callbacks`
        notify_disconnect: If True then IOC disconnect events will be reported
            by calling the callback with a `CANothing` error with .ok False,
            otherwise only valid values will be passed to the callback routine
        connect_timeout: If specified then the camonitor will report a
            disconnection event after the specified interval if connection
            has not completed by this time. Note that this notification will be
            made even if notify_disconnect is False, and that if the PV
            subsequently connects it will update as normal.

    Returns:
        `Subscription` for single PV or [`Subscription`] for a list of PVs
    """
    kwargs = locals().copy()
    if isinstance(kwargs.pop("pv"), str):
        return Subscription(pv, **kwargs)
    else:

        def make_cb(index, cb=kwargs.pop("callback")):
            return lambda v: cb(v, index)

        subs = [Subscription(x, make_cb(i), **kwargs) for i, x in enumerate(pv)]
        return subs


# ----------------------------------------------------------------------------
#   caget


@cadef.event_handler
def _caget_event_handler(args):  # pragma: no cover
    """This will be called when a caget request completes, either with a
    brand new data value or with failure.  The result is communicated back
    to the original caller."""

    # We are called exactly once, so can consume the context right now.  Note
    # that we have to do some manual reference counting on the user context,
    # as this is a python object that is invisible to the C api.
    pv, dbr_to_value, done, event_loop = args.usr
    ctypes.pythonapi.Py_DecRef(args.usr)

    if args.status == cadef.ECA_NORMAL:
        try:
            value = dbr_to_value(args.raw_dbr, args.type, args.count)
        except Exception as e:
            value = e
    else:
        value = CANothing(pv, args.status)
    event_loop.call_soon_threadsafe(done.set, value)


@overload
async def caget(
    pv: str,
    datatype: Datatype = ...,
    format: Format = ...,
    count: Count = ...,
    timeout: Timeout = ...,
    throw: bool = ...,
) -> AugmentedValue:
    ...  # pragma: no cover


@overload
async def caget(
    pvs: PVs,
    datatype: Datatype = ...,
    format: Format = ...,
    count: Count = ...,
    timeout: Timeout = ...,
    throw: bool = ...,
) -> List[AugmentedValue]:
    ...  # pragma: no cover


@maybe_throw
async def caget(pv: str, datatype=None, format=dbr.FORMAT_RAW, count=0):
    """Retrieves an `AugmentedValue` from one or more PVs.

    Args:
        datatype: Override `Datatype` to a non-native type
        format: Request extra `Format` fields
        count: Request a specific element `Count` in an array
        timeout: After how long should caget `Timeout`
        throw: If False then return `CANothing` instead of raising an exception

    Returns:
        `AugmentedValue` for single PV or [`AugmentedValue`] for a list of PVs
    """
    # Note: docstring refers to both this function and caget_array below
    # Retrieve the requested channel and ensure it's connected.
    channel = get_channel(pv)
    await channel.wait()

    # A count of zero will be treated by EPICS in a version dependent manner,
    # either returning the entire waveform (equivalent to count=-1) or a data
    # dependent waveform length.
    if count < 0:
        # Treat negative count request as request for fixed underlying channel
        # size.
        count = cadef.ca_element_count(channel)
    elif count > 0:
        # Need to ensure we don't ask for more than the channel can provide as
        # otherwise may get API error.
        count = min(count, cadef.ca_element_count(channel))

    # Assemble the callback context.  Note that we need to explicitly
    # increment the reference count so that the context survives until the
    # callback routine gets to see it.
    dbrcode, dbr_to_value = dbr.type_to_dbr(channel, datatype, format)
    done = ValueEvent[AugmentedValue]()
    loop = asyncio.get_event_loop()
    context = (pv, dbr_to_value, done, loop)
    ctypes.pythonapi.Py_IncRef(context)

    # Perform the actual put as a non-blocking operation: we wait to be
    # informed of completion, or time out.
    cadef.ca_array_get_callback(
        dbrcode, count, channel, _caget_event_handler, ctypes.py_object(context)
    )
    _flush_io()
    result = await done.wait()
    return result


@caget.register(list)  # type: ignore
@caget.register(tuple)  # type: ignore
async def caget_array(pvs: PVs, **kwargs):
    # Spawn a separate caget task for each pv: this allows them to complete
    # in parallel which can speed things up considerably.
    coros = [caget(pv, **parallel_timeout(kwargs)) for pv in pvs]
    results = await in_parallel(coros, kwargs)
    return results


# ----------------------------------------------------------------------------
#   caput


@cadef.event_handler
def _caput_event_handler(args):  # pragma: no cover
    """Event handler for caput with callback completion.  Returns status
    code to caller."""

    # This is called exactly once when a caput request completes.  Extract
    # our context information and discard the context immediately.
    pv, done, event_loop = args.usr
    ctypes.pythonapi.Py_DecRef(args.usr)

    if args.status == cadef.ECA_NORMAL:
        value = None
    else:
        value = CANothing(pv, args.status)
    event_loop.call_soon_threadsafe(done.set, value)


@overload
async def caput(
    pv: str,
    value,
    datatype: Datatype = ...,
    wait: bool = ...,
    timeout: Timeout = ...,
    throw: bool = ...,
) -> CANothing:
    ...  # pragma: no cover


@overload
async def caput(
    pvs: PVs,
    values,
    repeat_value: bool = ...,
    datatype: Datatype = ...,
    wait: bool = ...,
    timeout: Timeout = ...,
    throw: bool = ...,
) -> List[CANothing]:
    ...  # pragma: no cover


@maybe_throw
async def caput(pv: str, value, datatype=None, wait=False):
    """Writes values to one or more PVs

    If a list of PVs is given, then normally value will have the same length
    and value[i] is written to pv[i]. If value is a scalar or
    repeat_value=True then the same value is written to all PVs.

    Args:
        repeat_value: If True and a list of PVs is given, write the same
            value to every PV.
        datatype: Override `Datatype` to a non-native type
        wait: Do a caput with callback, waiting for completion
        timeout: After how long should a caput with wait=True `Timeout`
        throw: If False then return `CANothing` instead of raising an exception

    Returns:
        `CANothing` for single PV or [`CANothing`] for a list of PVs
    """

    # Connect to the channel and wait for connection to complete.
    channel = get_channel(pv)
    await channel.wait()

    # Note: the unused value returned below needs to be retained so that
    # dbr_array, a pointer to C memory, has the right lifetime: it has to
    # survive until ca_array_put[_callback] has been called.
    dbrtype, count, dbr_array, value = dbr.value_to_dbr(channel, datatype, value)
    if wait:
        # Assemble the callback context and give it an extra reference count
        # to keep it alive until the callback handler sees it.
        done = ValueEvent[None]()
        context = (pv, done, asyncio.get_event_loop())
        ctypes.pythonapi.Py_IncRef(context)

        # caput with callback requested: need to wait for response from
        # server before returning.
        cadef.ca_array_put_callback(
            dbrtype,
            count,
            channel,
            dbr_array,
            _caput_event_handler,
            ctypes.py_object(context),
        )
        _flush_io()
        await done.wait()
    else:
        # Asynchronous caput, just do it now.
        cadef.ca_array_put(dbrtype, count, channel, dbr_array)
        _flush_io()

    # Return a success code for compatibility with throw=False code.
    return CANothing(pv)


@caput.register(list)  # type: ignore
@caput.register(tuple)  # type: ignore
async def caput_array(pvs: PVs, values, repeat_value=False, **kwargs):
    # Bring the arrays of pvs and values into alignment.
    if repeat_value or isinstance(values, str):
        # If repeat_value is requested or the value is a string then we treat
        # it as a single value.
        values = [values] * len(pvs)
    else:
        try:
            values = list(values)
        except TypeError:
            # If the value can't be treated as a list then again we treat it
            # as a single value
            values = [values] * len(pvs)
    assert len(pvs) == len(values), "PV and value lists must match in length"
    coros = [
        caput(pv, value, **parallel_timeout(kwargs)) for pv, value in zip(pvs, values)
    ]
    results = await in_parallel(coros, kwargs)
    return results


# ----------------------------------------------------------------------------
#   connect


class CAInfo:
    """Object representing the information returned from `cainfo`"""

    #: Converts `state` into a printable description of the connection state.
    state_strings = ["never connected", "previously connected", "connected", "closed"]
    #: Textual descriptions of the possible channel data types, can be
    #: used to convert `datatype` into a printable string
    datatype_strings = [
        "string",
        "short",
        "float",
        "enum",
        "char",
        "long",
        "double",
        "no access",
    ]

    def __init__(self, pv: str, channel: Channel):
        #: True iff the channel was successfully connected
        self.ok: bool = True
        #: The name of the PV
        self.name: str = pv
        #: State of channel as an integer. Look up ``state_strings[state]``
        #: for textual description.
        self.state: int = cadef.ca_state(channel)
        #: Host name and port of server providing this PV
        self.host: str = cadef.ca_host_name(channel)
        #: True iff read access to this PV
        self.read: bool = cadef.ca_read_access(channel)
        #: True iff write access to this PV
        self.write: bool = cadef.ca_write_access(channel)
        if self.state == cadef.cs_conn:
            #: Data count of this channel
            self.count: int = cadef.ca_element_count(channel)
            #: Underlying channel datatype as `Dbr` value. Look up
            #: ``datatype_strings[datatype]`` for textual description.
            self.datatype: int = cadef.ca_field_type(channel)
        else:
            self.count = 0
            self.datatype = 7  # DBF_NO_ACCESS

    def __str__(self):
        return """%s:
    State: %s
    Host: %s
    Access: %s, %s
    Data type: %s
    Count: %d""" % (
            self.name,
            self.state_strings[self.state],
            self.host,
            self.read,
            self.write,
            self.datatype_strings[self.datatype],
            self.count,
        )


@overload
async def connect(
    pv: str, wait: bool = ..., timeout: Timeout = ..., throw: bool = ...
) -> CANothing:
    ...  # pragma: no cover


@overload
async def connect(
    pv: PVs, wait: bool = ..., timeout: Timeout = ..., throw: bool = ...
) -> List[CANothing]:
    ...  # pragma: no cover


@maybe_throw
async def connect(pv: str, wait=True):
    """Establishes a connection to one or more PVs

    A single PV or a list of PVs can be given. This does not normally need to be
    called, as the ca...() routines will establish their own connections as
    required, but after a successful connection we can guarantee that
    caput(..., wait=False) will complete immediately without suspension.

    This routine can safely be called repeatedly without any extra side effects.

    Args:
        wait: If False then queue a connection without waiting for completion
        timeout: After how long should the connect with wait=True `Timeout`
        throw: If False then return `CANothing` instead of raising an exception

    Returns:
        `CANothing` for single PV or [`CANothing`] for a list of PVs
    """

    channel = get_channel(pv)
    if wait:
        await channel.wait()
    return CANothing(pv)


@connect.register(list)  # type: ignore
@connect.register(tuple)  # type: ignore
async def connect_array(pvs: PVs, wait=True, **kwargs):
    coros = [connect(pv, **parallel_timeout(kwargs)) for pv in pvs]
    results = await in_parallel(coros, kwargs)
    return results


@overload
async def cainfo(
    pv: str, wait: bool = ..., timeout: Timeout = ..., throw: bool = ...
) -> CAInfo:
    ...  # pragma: no cover


@overload
async def cainfo(
    pv: PVs, wait: bool = ..., timeout: Timeout = ..., throw: bool = ...
) -> List[CAInfo]:
    ...  # pragma: no cover


@maybe_throw
async def cainfo(pv: str, wait=True):
    """Returns a `CAInfo` structure for the given PVs.

    See the documentation for `connect()` for details of arguments.
    """
    channel = get_channel(pv)
    if wait:
        await channel.wait()
    return CAInfo(pv, channel)


@cainfo.register(tuple)  # type: ignore
@cainfo.register(list)  # type: ignore
async def cainfo_array(pvs: PVs, wait=True, **kwargs):
    coros = [cainfo(pv, **parallel_timeout(kwargs)) for pv in pvs]
    results = await in_parallel(coros, kwargs)
    return results


# ----------------------------------------------------------------------------
#   CA Context manager


class _Context:
    created = False
    _channel_caches: Dict[asyncio.AbstractEventLoop, ChannelCache] = {}

    @classmethod
    def purge_channel_caches(cls):
        """Remove cached channel connections. This will close all subscriptions"""
        for channel_cache in cls._channel_caches.values():
            channel_cache.purge()
        cls._channel_caches.clear()

    @classmethod
    def get_channel_cache(cls):
        if not cls.created:
            # EPICS Channel Access event dispatching needs to done with a little
            # care.  In previous versions the solution was to repeatedly call
            # ca_pend_event() in polling mode, but this does not appear to be
            # efficient enough when receiving large amounts of data.  Instead we
            # enable preemptive Channel Access callbacks, which means we need to
            # cope with all of our channel access events occuring
            # asynchronously.
            cadef.ca_context_create(1)
            cls.created = True
        loop = asyncio.get_event_loop()
        try:
            channel_cache = cls._channel_caches[loop]
        except KeyError:
            # Channel from new event loop. Don't support multiple event loops, so
            # clear out all the old channels
            cls.purge_channel_caches()
            channel_cache = ChannelCache(loop)
            cls._channel_caches[loop] = channel_cache
        return channel_cache


purge_channel_caches = _Context.purge_channel_caches


def get_channel(pv: str) -> Channel:
    channel_cache = _Context.get_channel_cache()
    channel = channel_cache.get_channel(pv)
    return channel


@atexit.register
def _catools_atexit():  # pragma: no cover
    # On exit we do our best to ensure that channel access shuts down cleanly.
    # We do this by shutting down all channels and clearing the channel access
    # context: this should reduce the risk of unexpected errors during
    # application exit.
    #    One reason that it's rather important to do this properly is that we
    # can't safely do *any* ca_ calls once ca_context_destroy() is called!
    purge_channel_caches()
    if _Context.created:
        cadef.ca_flush_io()
        cadef.ca_context_destroy()


# Another delicacy arising from relying on asynchronous CA event dispatching is
# that we need to manually flush IO events such as caget commands.  To ensure
# that large blocks of channel access activity really are aggregated we used to
# ensure that ca_flush_io() is only called once in any scheduling cycle, but now
# we just call it every time
_flush_io = cadef.ca_flush_io


# ----------------------------------------------------------------------------
#   Helper function for running async code.


def run(coro, forever=False):
    """Convenience function that makes an event loop and runs the async
    function within it.

    Args:
        forever: If True then run the event loop forever, otherwise
            return on completion of the coro
    """
    loop = asyncio.get_event_loop()
    t = None
    try:
        if forever:
            t = asyncio.ensure_future(coro, loop=loop)
            loop.run_forever()
        else:
            return loop.run_until_complete(coro)
    finally:
        if t:
            t.cancel()
        loop.stop()
        loop.close()
