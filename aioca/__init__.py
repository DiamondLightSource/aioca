from epicscorelibs.ca.cadef import DBE_ALARM, DBE_LOG, DBE_PROPERTY, DBE_VALUE
from epicscorelibs.ca.dbr import (
    DBR_CHAR,
    DBR_CHAR_BYTES,
    DBR_CHAR_STR,
    DBR_CHAR_UNICODE,
    DBR_CLASS_NAME,
    DBR_DOUBLE,
    DBR_ENUM,
    DBR_ENUM_STR,
    DBR_FLOAT,
    DBR_LONG,
    DBR_PUT_ACKS,
    DBR_PUT_ACKT,
    DBR_SHORT,
    DBR_STRING,
    DBR_STSACK_STRING,
    FORMAT_CTRL,
    FORMAT_RAW,
    FORMAT_TIME,
    ca_extra_fields,
)

from ._catools import (
    CAInfo,
    CANothing,
    Subscription,
    caget,
    cainfo,
    camonitor,
    caput,
    connect,
    purge_channel_caches,
    run,
)
from ._version_git import __version__

__all__ = [
    # The core functions
    "Subscription",  # Returned from camonitor
    "caput",  # Write PVs to channel access
    "caget",  # Read PVs from channel access
    "camonitor",  # Monitor PVs over channel access
    "connect",  # Establish PV connection
    "cainfo",  # Returns ca_info describing PV connection
    "CAInfo",  # Ca info object
    "CANothing",  # No value
    "purge_channel_caches",  # Get rid of old channels
    "run",  # Run one aioca coroutine and clean up
    # The version of aioca
    "__version__",
    # Event type notification codes for camonitor
    "DBE_VALUE",  # Notify normal value changes
    "DBE_LOG",  # Notify archival value changes
    "DBE_ALARM",  # Notify alarm state changes
    "DBE_PROPERTY",  # Notify property change events (3.14.11 and later)
    # Basic DBR request codes: any one of these can be used as part of a
    # datatype request.
    "DBR_STRING",  # 40 character strings
    "DBR_SHORT",  # 16 bit signed
    "DBR_FLOAT",  # 32 bit float
    "DBR_ENUM",  # 16 bit unsigned
    "DBR_CHAR",  # 8 bit unsigned
    "DBR_LONG",  # 32 bit signed
    "DBR_DOUBLE",  # 64 bit float
    "DBR_CHAR_STR",  # Long strings as char arrays
    "DBR_CHAR_UNICODE",  # Long unicode strings as char arrays
    "DBR_ENUM_STR",  # Enums as strings, default otherwise
    "DBR_CHAR_BYTES",  # Long byte strings as char arrays
    "DBR_PUT_ACKT",  # Configure global alarm acknowledgement
    "DBR_PUT_ACKS",  # Acknowledge global alarm
    "DBR_STSACK_STRING",  # Returns status ack structure
    "DBR_CLASS_NAME",  # Returns record type (same as .RTYP?)
    # Data type format requests
    "FORMAT_RAW",  # Request the underlying data only
    "FORMAT_TIME",  # Request alarm status and timestamp
    "FORMAT_CTRL",  # Request graphic and control fields
    "ca_extra_fields",  # List of all possible augmented field names
]
