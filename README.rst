aioca
=====

|build_status| |coverage| |pypi_version| |readthedocs|

aioca is an asynchronous Channel Access client for asyncio and Python using
libca via ctypes. It exposes a high level interface similar to the commandline
tools::

    caget(pvs, ...)
        Returns a single snapshot of the current value of each PV.

    caput(pvs, values, ...)
        Writes values to one or more PVs.

    camonitor(pvs, callback, ...)
        Receive notification each time any of the listed PVs changes.

    connect(pvs, ...)
        Optionally can be used to establish PV connection before using the PV.


Documentation
-------------

Full documentation is available at http://aioca.readthedocs.org

Source Code
-----------

Available from https://github.com/dls-controls/aioca

Installation
------------

To install the latest release, type::

    pip install aioca

Changelog
---------

See CHANGELOG_

Contributing
------------

See CONTRIBUTING_

License
-------

APACHE License. (see LICENSE_)

.. |build_status| image:: https://travis-ci.org/dls-controls/aioca.svg?branch=master
    :target: https://travis-ci.org/dls-controls/aioca
    :alt: Build Status

.. |coverage| image:: https://coveralls.io/repos/github/dls-controls/aioca/badge.svg?branch=master
    :target: https://coveralls.io/github/dls-controls/aioca?branch=master
    :alt: Test coverage

.. |pypi_version| image:: https://img.shields.io/pypi/p/aioca.svg
    :target: https://pypi.python.org/pypi/aioca
    :alt: Latest PyPI version

.. |readthedocs| image:: https://readthedocs.org/projects/aioca/badge/?version=latest
    :target: http://aioca.readthedocs.org
    :alt: Documentation

.. _CHANGELOG:
    https://github.com/dls-controls/aioca/blob/master/CHANGELOG.rst

.. _CONTRIBUTING:
    https://github.com/dls-controls/aioca/blob/master/CONTRIBUTING.rst

.. _LICENSE:
    https://github.com/dls-controls/aioca/blob/master/LICENSE