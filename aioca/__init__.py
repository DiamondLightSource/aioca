try:
    # In a release there will be a static version file written by setup.py
    from ._version_static import __version__  # noqa
except ImportError:
    # Otherwise get the release number from git describe
    from ._version_git import __version__

__all__ = ["__version__"]
