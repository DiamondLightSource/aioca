from epicscorelibs.ca import cadef, dbr
from epicscorelibs.ca.cadef import *  # noqa
from epicscorelibs.ca.dbr import *  # noqa

from ._catools import (
    ca_nothing,
    caget,
    cainfo,
    camonitor,
    caput,
    connect,
    run,
    run_forever,
)

try:
    # In a release there will be a static version file written by setup.py
    from ._version_static import __version__  # noqa
except ImportError:
    # Otherwise get the release number from git describe
    from ._version_git import __version__


__all__ = [
    # The core functions
    "caput",  # Write PVs to channel access
    "caget",  # Read PVs from channel access
    "camonitor",  # Monitor PVs over channel access
    "connect",  # Establish PV connection
    "cainfo",  # Returns ca_info describing PV connection
    "ca_nothing",  # No value
    "run",  # Run one aioca coroutine and clean up
    "run_forever",  # Run one aioca coroutine indefinitely
    # The version of aioca
    "__version__",
]

# Add in the dbr and cadef namespaces for ease of use
__all__ += dbr.__all__ + cadef.__all__
