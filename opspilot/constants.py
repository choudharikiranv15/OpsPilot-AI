"""Constants shared across OpsPilot. User-tunable values live in settings.py."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Version (single source of truth: [project].version in pyproject.toml)
try:
    VERSION = _pkg_version("opspilot-ai")
except PackageNotFoundError:  # running from a source tree without installation
    VERSION = "0.0.0+unknown"

# Default model confidence required before proposing dry-run patches
CONFIDENCE_THRESHOLD = 0.6

# Maximum characters of local log text gathered per run
LOG_TRUNCATE_LIMIT = 10000

# Maximum entries kept in the local diagnosis history
MEMORY_MAX_ENTRIES = 100
