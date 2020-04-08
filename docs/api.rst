.. _API:

aioca API
=========

.. module:: aioca

.. _Common:

Common Notes
------------

All four functions take an argument ``pv`` which can specify the name of a
single PV or can be a list of PVs.  In all cases the returned result has the
same "shape" as the ``pv`` argument, in other words, if ``pv`` is a single
string then a single value (error code, value, or subscription) is returned, and
if ``pv`` is a list then a list of exactly the same length is returned.

In general there are advantages to calling `caput`, `caget` or `connect` on a
list of PVs, as in this case the channel connection and access delays will occur
in parallel.

Several arguments are common through this API: ``throw`` determines how errors are
handled, ``timeout`` determines timeouts, and finally ``datatype``, ``format`` and
``count`` determine data formats and are documented in `Augmented`.

``timeout``
    The ``timeout`` argument specified how long `caput` or `caget`
    will wait for the entire operation to complete.  This timeout is in seconds,
    and can be one of several formats: a timeout interval in seconds, an
    absolute deadline (in `time.time` format) as a single element tuple,
    or None to specify that no timeout will occur.  Note that a timeout of 0
    will timeout immediately if any waiting is required.

    If a timeout occurs then a `CANothing` will be raised unless
    ``throw=False`` has been set.

``throw``
    This parameter determines the behaviour of `caget`, `caput`, and
    `connect` when an error occurs.  If ``throw=True`` (the default) is
    set then an exception is raised, otherwise if ``False`` is specified an
    error code value is returned for each failing PV.


Functions
---------

.. automodule:: aioca
    :members: caput

The return value from `caput` is either a list or a single value,
depending on the shape of ``pv``.  For each PV a `CANothing` success
code is returned on success, otherwise either an exception is raised or an
appropriate error code is returned for each failing PV if ``throw=True`` is
set. The return code can be tested for boolean success, so for example it
is possible to write::

    if not caput(pv, value, throw=False):
        # process caput error

If all the PVs listed in ``pv`` have already been connected, through a
successful call to any `aioca` method, then the library guarantees
that the puts for each PV will occur strictly in sequence.  For any PVs
which need a connection to be established the order of execution of puts
is completely undefined.

.. automodule:: aioca
    :members: caget

The various arguments control the behaviour of `caget` as follows:

``datatype``, ``format``, ``count``
    See documentation for :ref:`Augmented` below.

``timeout``, ``throw``
    Documented in :ref:`Common` above.  If a value cannot be retrieved
    and ``throw=False`` is set then for each failing PV an empty value with
    ``.ok==False`` is returned.

The format of values returned depends on the number of values requested
for each PV.  If only one value is requested then the value is returned
as a scalar, otherwise as a numpy array.

.. autofunction:: camonitor

For a single pv callbacks will be called as::

    callback(value)

for each update where value is an `AugmentedValue`. For a list of pvs then
each update is called as::

    callback(value, index)

where index is the position in the original array of pvs of the name
generating this update.

Subscriptions will remain active until the :meth:`~Subscription.close()` method
is called on the returned subscription object:

.. autoclass:: Subscription()
    :members:

.. automodule:: aioca
    :members: connect

It is possible to test whether a channel has successfully connected without
provoking suspension by calling ``connect(pv, wait=False, cainfo=True)``
and testing the ``.state`` attribute of the result.

.. automodule:: aioca
    :members: cainfo

.. autoclass:: CAInfo()
    :members:

The `str` representation of this structure can be printed to
produce output similar to that produced by the ``cainfo`` command line
tool.

All the async functions in the `aioca` interface can be run under the asyncio
event loop. A convenience function is provided to do this:

.. autofunction:: run

..  _Values:

Working with Values
-------------------

There are two types of values returned by `aioca` functions:
`Augmented` and `Error`.  The `caput` function only returns
an error code value (which may indicate success), while `caget` and
`camonitor` will normally return (or deliver) augmented values, but will
return (or deliver) an error code on failure.

The following fields are common to both types of value.  This means that is is
always safe to test ``value.ok`` for a value returned by `caget` or
`caput` or delivered by `camonitor`.

``ok``
    Set to ``True`` if the data is good, ``False`` if there was an
    error. For augmented values ``ok`` is always set to ``True``.

``name``
    Name of the pv.


Values and their Types
~~~~~~~~~~~~~~~~~~~~~~

The type of values returned by `caget` or delivered by `camonitor`
callbacks is determined by the requested datatype in the original `caget`
or `camonitor` call together with the underlying length of the requested
EPICS field.

If the underlying length (`element_count`) of the EPICS value is 1 then
the value will be returned as a Python scalar, and will be one of the three
basic scalar types (string, integer or floating point number), but wrapped as an
augmented type.

If on the other hand `element_count` is not 1 then the value is treated
as an array and is always returned as a numpy array, again wrapped as an
augmented type.  Note that this means that even if ``caget(pv, count=1)`` is
used to fetch a value with one element, if the underlying PV is an array then
the result returned will be an array.

The table below enumerates the possibilities:

    =========== =============== ========================================
    aioca type  Derived from    For these values
    =========== =============== ========================================
    `ca_str`    `str`           String value
    `ca_int`    `int`           Integral value
    `ca_float`  `float`         Floating point value
    `ca_array`  `ndarray`       Any array value
    =========== =============== ========================================

..  class:: ca_str
..  class:: ca_int
..  class:: ca_float

    Scalar types derived from basic Python types.

..  class:: ca_array

    Array type derived from `numpy.ndarray`. The associated
    :attr:`~numpy.ndarray.dtype` will be as close a fit to the underlying data
    as possible.



.. _Error:

Error Code Values
~~~~~~~~~~~~~~~~~

.. autoclass:: CANothing
    :members:

The following ECA error codes from ``epicscorelibs.ca.cadef`` are worth noting:

``ECA_SUCCESS``
    Success error code. In this case ``.ok`` is ``True``.
    Returned by successful `caput` and `connect` calls.

``ECA_DISCONN``
    Channel disconnected.  This is used by `camonitor` to report
    channel disconnect events.

``ECA_TIMEOUT``
    Channel timed out.  Reported if user specified timeout ocurred
    before completion and if ``throw=False`` specified.


..  _Augmented:

Augmented Values
~~~~~~~~~~~~~~~~

Augmented values are normally Python or `numpy` values with extra fields:
the `!.ok` and `!.name` fields are already mentioned above, and
further extra fields will be present depending on format requested for the data.
As pointed out above, `!.ok` is always `True` for valid data.

Four different types of augmented value are returned: strings, integers,
floating point numbers or arrays, depending on the length of the data
requested -- an array is only used when the data length is >1.

In almost all circumstances an augmented value will behave exactly like a
normal value, but there are a few rare cases where differences in behaviour are
observed (these are mostly bugs).  If this occurs the augumentation can be
stripped from an augmented value ``value`` by writing ``+value`` -- this returns
the underlying value.

The type of augmented values is determined both by parameters passed to `caget`
and `camonitor` and by the underlying datatype.  Both of these functions share
parameters ``datatype``, ``format`` and ``count`` which can be used to control
the type of the data returned:

``datatype``
    For `caget` and `camonitor` this controls the format of the
    data that will be requested, while for `caput` the data will be
    coerced into the requested format. ``datatype`` can be any of the
    following:

    1.  ``None`` (the default).  In this case the "native" datatype
        provided by the channel will be returned.

    2.  A `Dbr` value. See items 5 onwards for details of the special values.

    3.  A python type compatible with any of the above values, such as
        `int`, `float` or `str`.  These correspond to
        ``DBR_LONG``, ``DBR_DOUBLE`` and ``DBR_STRING``
        respectively.

    4.  Any `numpy.dtype` compatible with any of the above values.

    5.  One of the special values ``DBR_CHAR_STR``,
        ``DBR_CHAR_UNICODE``, or ``DBR_CHAR_BYTES``.  This is used to
        request a char array which is then converted to a Python `str`
        or `bytes` string on receipt.  It is not
        sensible to specify `count` with this option.  The options
        ``DBR_CHAR_BYTES`` and ``DBR_CHAR_UNICODE`` are meaningless
        and not supported for `caput`.

        Note that if the PV name ends in ``$`` and ``datatype`` is not specified
        then ``DBR_CHAR_STR`` will be used.

    6.  The special value ``DBR_ENUM_STR``, only for `caget` and
        `camonitor`.  In this case the "native" channel datatype is used
        unless the channel is an enumeration, in which case the corresponding
        string is returned.

    7.  For `caget` and `camonitor` two further special values are
        supported.  In both of these cases `format` is ignored:

        ..  data:: DBR_STSACK_STRING

            Returns the current value as a string together with extra fields
            `status`, `severity`, `ackt`, `acks`.

        ..  data:: DBR_CLASS_NAME

            Returns the name of the "enclosing interface", typically the
            record type, and typically the same as the EPICS ``.RTYP`` field.

        For `caput` also two further values are supported:

        ..  data:: DBR_PUT_ACKT
                   DBR_PUT_ACKS

            These are used for global alarm acknowledgement, where
            `DBR_PUT_ACKT` configures whether alarms need to be acknowleged
            and `DBR_PUT_ACKS` acknowledges alarms of a particular severity.

``format``
    The `Format` controls how much auxilliary information will be returned with
    the retrieved data.

``count``
    The `Count` determines how many elements to fetch for arrays

.. automodule:: aioca.types
    :members:
    :member-order: alphabetical
