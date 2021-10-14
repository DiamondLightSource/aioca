from datetime import datetime  # noqa
from typing import List, Sized, Tuple, Type, Union

from typing_extensions import Literal, Protocol

#: A timeout is represented by one of the following
#:
#: ======== ============================================================
#: None     A timeout that never expires
#: 0        Timeout immediately if any waiting is required
#: float    A relative timeout interval in seconds
#: (float,) An absolute deadline in seconds past epoch
#: ======== ============================================================
Timeout = Union[None, Tuple[float], float]

#: A bitwise or of DBE event codes from epicscorelibs.ca.dbr
#:
#: ============ ===========================================================
#: DBE_VALUE    Trigger an event when a significant change in the channel's
#:              value occurs. Relies on the monitor deadband field on the
#:              server
#: DBE_LOG      Trigger an event when an archive significant change in the
#:              channel's value occurs. Relies on the archiver monitor
#:              deadband field on the server
#: DBE_ALARM    Trigger an event when the alarm state changes
#: DBE_PROPERTY Trigger an event when a property change (control limit,
#:              graphical limit, status string, enum string ...) occurs.
#: ============ ===========================================================
#:
#: If not specified then the default value depends on the requested `Format`
#:
#: ============ =============================================
#: Format       Default value for events
#: ============ =============================================
#: FORMAT_RAW   DBE_VALUE
#: FORMAT_TIME  DBE_VALUE | DBE_ALARM
#: FORMAT_CTRL  DBE_VALUE | DBE_ALARM | DBE_PROPERTY
#: ============ =============================================
Dbe = Union[None, int]

#: A DBR request code from epicscorelibs.ca.dbr. One of
#:
#: ==================== ================================================
#: DBR_STRING           40 character strings
#: DBR_SHORT            16 bit signed
#: DBR_FLOAT            32 bit float
#: DBR_ENUM             16 bit unsigned
#: DBR_CHAR             8 bit unsigned
#: DBR_LONG             32 bit signed
#: DBR_DOUBLE           64 bit float
#: DBR_PUT_ACKT         Configure global alarm acknowledgement
#: DBR_PUT_ACKS         Acknowledge global alarm
#: DBR_STSACK_STRING    Returns status ack structure
#: DBR_CLASS_NAME       Returns record type (same as .RTYP)
#: DBR_ENUM_STR         Enums as strings, default otherwise
#: DBR_CHAR_BYTES       Long byte strings as char arrays
#: DBR_CHAR_UNICODE     Long unicode strings as char arrays
#: DBR_CHAR_STR         Long strings as char arrays
#: ==================== ================================================
Dbr = Literal[0, 1, 2, 3, 4, 5, 6, 35, 36, 37, 38, 996, 997, 998, 999]

#: The format of the requested data can be one of the following
#:
#: ==================== ================================================
#: None (the default)   In this case the "native" datatype provided
#:                      by the channel will be returned
#: A `Dbr` value        To request this type from the IOC
#: A python type        Compatible with any of the above values,
#:                      such as int, float or str
#: A numpy dtype        Compatible with any of the above values
#: ==================== ================================================
Datatype = Union[None, Dbr, Type]

#: How much auxilliary information will be returned with the retrieved data.
#: From epicscorelibs.ca.dbr, one of the following
#:
#: ============ ===========================================================
#: FORMAT_RAW   The data is returned unaugmented except for the .name field
#: FORMAT_TIME  The data is augmented by the data timestamp together with
#:              .alarm .status and .severity fields.
#: FORMAT_CTRL  The data is augmented by channel access "control" fields.
#:              This set of fields depends on the underlying datatype
#: ============ ===========================================================
Format = Literal[0, 1, 2]

#: How many array elements to retrieve from the server. One of the following
#:
#: ======== ============================================================
#: 0        Server and data dependent waveform length
#: -1       The full data length
#: +ve int  A maximum of this number of elements
#: ======== ============================================================
Count = Union[Literal[0, -1], int]


class AugmentedValue(Protocol, Sized):
    """Protocol representing a value returned from `caget` or `camonitor`

    The value itself depends on the number of values requested for the PV. If
    only one value is requested then the value is returned as a scalar,
    otherwise as a numpy array.

    The value will also be "augmented" with extra fields depending on the
    `Format` and `Datatype` of the pv, and if the operation was successful.

    Every value has the `ok` and `name` fields.

    If `ok` is False then `errorcode` is set to the appropriate ECA error code
    and str(value) will return an appropriate error message.

    If `ok` is True then `datatype` and `element_count` will be present.

    If FORMAT_TIME is requested then `status`, `severity`, `timestamp` and
    `raw_stamp` will be present

    If FORMAT_CTRL is requested then `status` and `severity` will be present,
    along with other `Dbr` specific fields:

    - DBR_SHORT, DBR_CHAR, DBR_LONG will also have `units`, `upper_disp_limit`,
      `lower_disp_limit`, `upper_alarm_limit`, `lower_alarm_limit`,
      `upper_warning_limit`, `lower_warning_limit`, `upper_ctrl_limit`,
      `lower_ctrl_limit`
    - DBR_FLOAT, DBR_DOUBLE will have the DBR_LONG fiels together with a
      `precision` field
    - DBR_ENUM will have `enums`
    - DBR_STRING does not support FORMAT_CTRL, so FORMAT_TIME data is returned
      instead
     """

    #: Name of the PV used to create this value
    name: str
    #: True for normal data, False for error code
    ok: bool
    #: ECA error code
    errorcode: int
    #: Underlying `Dbr` code
    datatype: int
    #: Number of elements in the underlying EPICS value. If this is not 1 then the
    #: value is treated as an array, otherwise up to this many elements may be
    #: present in the value.
    element_count: int
    #: EPICS alarm severity, normally one of the values listed below.
    #:
    #: =  ==================================
    #: 0  No alarm
    #: 1  Alarm condition, minor severity
    #: 2  Alarm condition, major severity.
    #: 3  Invalid value.
    #: =  ==================================
    severity: int
    #: CA status code, the reason for severity
    status: int
    #: Record timestamp in raw format as provided by EPICS (but in the local Unix
    #: epoch, not the EPICS epoch).  Is a tuple of the form ``(secs, nsec)`` with
    #: integer seconds and nanosecond values, provided in case full ns timestamp
    #: precision is required.
    raw_stamp: Tuple[int, int]
    #: Timestamp in seconds in format compatible with ``time.time()`` rounded to
    #: the nearest microsecond: for nanosecond precision use `raw_stamp`
    #: instead.
    timestamp: float
    #: This is a dynamic property which returns `timestamp` as a
    #: `datetime` value, taking local time into account
    datetime: datetime
    units: str  #: Units for display
    upper_disp_limit: float  #: Upper limit for displaying value
    lower_disp_limit: float  #: Lower limit for displaying value
    upper_alarm_limit: float  #: Above this limit value in alarm
    lower_alarm_limit: float  #: Below this limit value in alarm
    upper_warning_limit: float  #: Above this limit is a warning
    lower_warning_limit: float  #: Below this limit is a warning
    upper_ctrl_limit: float  #: Upper limit for puts to this value
    lower_ctrl_limit: float  #: Lower limit for puts to this value
    precision: int  #: Display precision for floating point values
    enums: List[str]  #: Enumeration strings for ENUM type
    #: Used for global alarm acknowledgement. Do transient alarms have
    #: to be acknowledged? (0,1) means (no, yes).
    ackt: int
    #: Used for global alarm acknowledgement. The highest alarm severity to
    #: acknowledge. If the current alarm severity is less then or equal to
    #: this value the alarm is acknowledged.
    acks: int
