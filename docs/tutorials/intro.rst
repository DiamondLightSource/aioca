Introduction
================================================================================

.. .. include:: ../../README.md
..     :end-before: <!-- README only content

`caget(pvs, ...) <caget>`
    Returns a single snapshot of the current value of each PV.

`caput(pvs, values, ...) <caput>`
    Writes values to one or more PVs.

`camonitor(pvs, callback, ...) <camonitor>`
    Receive notification each time any of the listed PVs changes.

`connect(pvs, ...) <connect>`
    Optionally can be used to establish PV connection before using the PV.

To use these functions a certain amount of setup work is required. The following
code illustrates a simple application which reads a value from one PV, writes to
another PV, and monitors a third until terminated with control-C::

    from aioca import caget, caput, camonitor, run

    async def do_stuff():
        # Using caput: write 1234 into PV1.  Raises exception on failure
        await caput('PV1', 1234)

        # Print out the value reported by PV2.
        print(await caget('PV2'))

        # Monitor PV3, printing out each update as it is received.
        def callback(value):
            print('callback', value)

        camonitor('PV3', callback)

    # Now run the camonitor process until interrupted by Ctrl-C.
    run(do_stuff(), forever=True)

The `run` function is just a convenience function to allow async code to be
tested, it just creates an asyncio event loop and runs the code under it. If you
already have an asyncio event loop you can just call your async function within
it and dispense with the `run` function.

If running under IPython you can also do awaits from the interactive console::

    In [1]: from aioca import caput

    In [2]: await caput("PV1", 5678)


How do I pronounce aioca?
-------------------------

Good question. The closest we have to a canonical pronounciation is a-o-ka,
as the alternatives are a bit of a mouthful...


.. _environment:

Environment Variables
---------------------

A number of environment variables affect the operation of channel access.  These
can be set using the `os.environ` dictionary -- but note that these need to be
set *before* loading the `aioca` module.  The following are documented in the
`EPICS channel access developers manual
<http://www.aps.anl.gov/epics/EpicsDocumentation/AppDevManuals/ChannelAccess/cadoc_4.htm>`_.


``EPICS_CA_MAX_ARRAY_BYTES``
    Configures the maximum number of bytes that can be transferred in a single
    channel access message.

``EPICS_CA_ADDR_LIST``
    A space separated list of channel access server addresses.

``EPICS_CA_AUTO_ADDR_LIST``
    If set to ``NO`` the automatic scanning of networks is disabled.

``EPICS_CA_CONN_TMO``
    Connection timeout, 30 seconds by default.

``EPICS_CA_BEACON_PERIOD``
    Beacon polling period, 15 seconds by default.

``EPICS_CA_SERVER_PORT``, ``EPICS_CA_REPEATER_PORT``
    Set these to configure the ports used to connect to channel access.  By
    default ports 5064 and 5065 are used respectively.

Example code::

    import os
    os.environ['EPICS_CA_MAX_ARRAY_BYTES'] = '1000000'

    # Note: the first import of aioca must come after the environ is set up.
    from aioca import *


Function Reference
------------------

The `API` consists of the three functions `caput`, `caget` and `camonitor`
together with auxilliary `connect` and `cainfo` functions.  The functions
`caget` and `camonitor` return or deliver "augmented" values which are
documented in more detail in the `Values` section.


Interactions with other CA libraries
------------------------------------

To ensure some level of interoperability, aioca will only create (and destroy)
its own CA context if there is not one set for the asyncio event loop thread.
This means that it is safe to:

- Use aioca and pyepics in different threads
- Use aioca and pyepics in the same thread as long as pyepics is imported before
  aioca is first used
