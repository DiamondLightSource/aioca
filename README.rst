aioca
=====

|code_ci| |docs_ci| |coverage| |pypi_version| |license|

aioca is an asynchronous EPICS Channel Access client for asyncio and Python
using libca via ctypes.

============== ==============================================================
PyPI           ``pip install aioca``
Source code    https://github.com/dls-controls/aioca
Documentation  https://dls-controls.github.io/aioca
Changelog      https://github.com/dls-controls/aioca/blob/master/CHANGELOG.rst
============== ==============================================================

.. |code_ci| image:: https://github.com/dls-controls/aioca/workflows/Code%20CI/badge.svg?branch=master
    :target: https://github.com/dls-controls/aioca/actions?query=workflow%3A%22Code+CI%22
    :alt: Code CI

.. |docs_ci| image:: https://github.com/dls-controls/aioca/workflows/Docs%20CI/badge.svg?branch=master
    :target: https://github.com/dls-controls/aioca/actions?query=workflow%3A%22Docs+CI%22
    :alt: Docs CI

.. |coverage| image:: https://codecov.io/gh/dls-controls/aioca/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/dls-controls/aioca
    :alt: Test Coverage

.. |pypi_version| image:: https://img.shields.io/pypi/v/aioca.svg
    :target: https://pypi.org/project/aioca
    :alt: Latest PyPI version

.. |license| image:: https://img.shields.io/badge/License-Apache%202.0-blue.svg
    :target: https://opensource.org/licenses/Apache-2.0
    :alt: Apache License

..
    These definitions are used when viewing README.rst and will be replaced
    when included in index.rst

It exposes a high level interface similar to the commandline tools::

    caget(pvs, ...)
        Returns a single snapshot of the current value of each PV.

    caput(pvs, values, ...)
        Writes values to one or more PVs.

    camonitor(pvs, callback, ...)
        Receive notification each time any of the listed PVs changes.

    connect(pvs, ...)
        Optionally can be used to establish PV connection before using the PV.

See https://dls-controls.github.io/aioca for more detailed documentation.
