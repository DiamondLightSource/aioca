[![CI](https://github.com/DiamondLightSource/aioca/actions/workflows/ci.yml/badge.svg)](https://github.com/DiamondLightSource/aioca/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DiamondLightSource/aioca/branch/main/graph/badge.svg)](https://codecov.io/gh/DiamondLightSource/aioca)
[![PyPI](https://img.shields.io/pypi/v/aioca.svg)](https://pypi.org/project/aioca)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# aioca

aioca is an asynchronous EPICS Channel Access client for asyncio and Python
using libca via ctypes.

|    Source     |     <https://github.com/DiamondLightSource/aioca>      |
| :-----------: | :----------------------------------------------------: |
|     PyPI      |                  `pip install aioca`                   |
| Documentation |      <https://DiamondLightSource.github.io/aioca>      |
|   Releases    | <https://github.com/DiamondLightSource/aioca/releases> |

<<<<<<< before updating
<!-- README only content. Anything below this line won't be included in index.md -->
=======
What            | Where
:---:           | :---:
Source          | <https://github.com/DiamondLightSource/aioca>
PyPI            | `pip install aioca`
Documentation   | <https://diamondlightsource.github.io/aioca>
Releases        | <https://github.com/DiamondLightSource/aioca/releases>

This is where you should put some images or code snippets that illustrate
some relevant examples. If it is a library then you might put some
introductory code here:
>>>>>>> after updating

It exposes a high level interface similar to the commandline tools::

    caget(pvs, ...)
        Returns a single snapshot of the current value of each PV.

    caput(pvs, values, ...)
        Writes values to one or more PVs.

    camonitor(pvs, callback, ...)
        Receive notification each time any of the listed PVs changes.

    connect(pvs, ...)
        Optionally can be used to establish PV connection before using the PV.

See https://DiamondLightSource.github.io/aioca for more detailed documentation.
