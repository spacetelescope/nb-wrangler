"""Global constants for nb-wrangler package."""

import os
from pathlib import Path

# Version
__version__ = "0.7.8"

WRANGLER_SPEC_VERSION = 2.1

# Path constants
HOME = Path(os.environ.get("HOME", "."))
NBW_ROOT = Path(
    os.environ.get(
        "NBW_ROOT",
        os.environ.get(
            "MAMBA_ROOT_PREFIX", os.environ.get("CONDA_ROOT_PREFIX", HOME / ".nbw-live")
        ),
    )
)
NBW_PANTRY = Path(os.environ.get("NBW_PANTRY", HOME / ".nbw-pantry"))
NBW_CACHE = Path(os.environ.get("NBW_CACHE", NBW_ROOT / "cache"))
NBW_MM = Path(
    os.environ.get("NBW_MM", os.environ.get("MAMBA_ROOT_PREFIX", NBW_ROOT / "mm"))
)

NBW_MAMBA_CMD = str(
    os.environ.get(
        "NBW_MAMBA_CMD", os.environ.get("MAMBA_EXE", NBW_MM / "bin" / "micromamba")
    )
)
NBW_PIP_CMD = str(os.environ.get("NBW_PIP_CMD", "uv pip"))


# Set cache environment variables if not already set, to ensure that tools like pip, npm,
# and yarn use the designated cache directories which may speed up installations and reduce
# redundant downloads.
if "UV_CACHE_DIR" not in os.environ:
    os.environ["UV_CACHE_DIR"] = str(NBW_CACHE / "uv")
if "PIP_CACHE_DIR" not in os.environ:
    os.environ["PIP_CACHE_DIR"] = str(NBW_CACHE / "pip")
if "npm_config_cache" not in os.environ:
    os.environ["npm_config_cache"] = str(NBW_CACHE / "npm")
if "YARN_CACHE_FOLDER" not in os.environ:
    os.environ["YARN_CACHE_FOLDER"] = str(NBW_CACHE / "yarn")


REPOS_DIR = "references"
DATA_DIR = "data"
NBW_URI = "nbw://"

BUILTIN_PACKAGES = ["__future__", "builtins", "sys", "os", "copy"]

DEFAULT_ARCHIVE_FORMAT = ".tar"
VALID_ARCHIVE_FORMATS = [
    ".tar.gz",
    ".tar.xz",
    ".tar",
    ".tar.bz2",
    ".tar.zst",
    ".tar.lzma",
    ".tar.lzo",
    ".tar.lz",
]

# nbw-exports.sh and kernel values will be from refdata_dependencies.yaml vs. relative to pantry shelf
DEFAULT_DATA_ENV_VARS_MODE = "spec"

# Notebook testing constants
NOTEBOOK_TEST_MAX_SECS = int(os.environ.get("NBW_TEST_MAX_SECS", 4 * 60 * 60))  # 60 min
NOTEBOOK_TEST_JOBS = int(os.environ.get("NBW_TEST_JOBS", 4))
NOTEBOOK_TEST_EXCLUDE = "$^"  # nothing?

# Timeout constants (in seconds)
DEFAULT_TIMEOUT = 300
REPO_CLONE_TIMEOUT = 300
DATA_GET_TIMEOUT = 7200
ENV_CREATE_TIMEOUT = 1800
INSTALL_PACKAGES_TIMEOUT = 1800
PIP_COMPILE_TIMEOUT = 600
IMPORT_TEST_TIMEOUT = 60
ARCHIVE_TIMEOUT = 1200
DOCKER_BUILD_TIMEOUT = 90 * 60  # 1.5 hours

# Package lists
TARGET_PACKAGES = [
    "uv",
    "pip",
    "ipykernel",
    "jupyter",
    "cython",
    "setuptools",
    "wheel",
]
CURATOR_PACKAGES = ["papermill"] + TARGET_PACKAGES

# Logger configuration constants
VALID_LOG_TIME_MODES = ["none", "normal", "elapsed", "both"]
DEFAULT_LOG_TIMES_MODE = "elapsed"
VALID_COLOR_MODES = ["auto", "on", "yes", "off", "no"]
DEFAULT_COLOR_MODE = "auto"
LOG_FILE = os.environ.get("NBW_LOG_FILE")

DATA_SPEC_NAME = "refdata_dependencies.yaml"

DEFAULT_CLEANUP_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".ipynb_checkpoints",
]
