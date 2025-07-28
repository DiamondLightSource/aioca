Changelog
=========


**ATTENTION:** This file is deprecated in favour of `Github Releases <https://github.com/DiamondLightSource/aioca/releases>`_

The file is retained for historical reference only but will no longer be updated.


The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.


1.8.1_ - 2024-11-01
-----------

Fixed:

- `Bump supported Python version <../../pull/53>`_

1.8_ - 2024-10-11
-----------------

Removed:

- `Remove support for Python 3.6 and 3.7 <../../pull/52>`_

Fixed:
- `Fix clashing contexts <../../pull/51>`_

1.7_ - 2023-05-05
-----------------

Added:

- `Add methods to allow inspecting Channels <../../pull/38>`_

1.6_ - 2023-04-06
-----------------

Added:

- `Support for existing in the same process as pyepics <../../pull/33>`_

1.5.1_ - 2022-12-05
-----------------

Fixed:

- `Support sync functions that return awaitables like 1.4 did <../../pull/33>`_

1.5_ - 2022-11-02
-----------------

Fixed:

- `Improved performance <../../pull/29>`_

1.4_ - 2022-06-07
-----------------

Fixed:

- `camonitor(all_updates=True) now works <../../pull/24>`_
- `Fixed memory leak in camonitor <../../pull/26>`

1.3_ - 2021-10-15
-----------------

Added:

- `Support for Python3.6 <../../pull/19>`_

1.2_ - 2021-07-08
-----------------

- Defer creation of ca_context until first channel connect #18

1.1_ - 2021-06-24
-----------------

- Update CI and build to latest standard #15
- Add purge_channel_caches() function #16


1.0_ - 2020-07-09
-----------------

- Improve packaging


0.2_ - 2020-06-17
-----------------

- Improve performance of ca*_array functions
- Specify minimum requirements for epicscorelibs


0.1 - 2020-04-09
----------------

- Port of cothread.catools to asyncio

.. _Unreleased: ../../compare/1.8.1...HEAD
.. _1.8.1: ../../compare/1.8...1.8.1
.. _1.8: ../../compare/1.7...1.8
.. _1.7: ../../compare/1.6...1.7
.. _1.6: ../../compare/1.5.1...1.6
.. _1.5.1: ../../compare/1.5...1.5.1
.. _1.5: ../../compare/1.4...1.5
.. _1.4: ../../compare/1.3...1.4
.. _1.3: ../../compare/1.2...1.3
.. _1.2: ../../compare/1.1...1.2
.. _1.1: ../../compare/1.0...1.1
.. _1.0: ../../compare/0.2...1.0
.. _0.2: ../../compare/0.1...0.2
