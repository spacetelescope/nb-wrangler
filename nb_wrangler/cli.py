# nb_wrangler/cli.py
"""Command line interface for nb-wrangler."""

import os
import sys
import argparse
import cProfile
import pstats

from . import wrangler
from . import utils
from . import logger
from . import config as config_mod
from . import constants
from .constants import (
    VALID_LOG_TIME_MODES,
    DEFAULT_LOG_TIMES_MODE,
    VALID_COLOR_MODES,
    DEFAULT_COLOR_MODE,
    REPOS_DIR,
    DEFAULT_DATA_ENV_VARS_MODE,
    NOTEBOOK_TEST_MAX_SECS,
    NOTEBOOK_TEST_JOBS,
    NOTEBOOK_TEST_EXCLUDE,
    VALID_ARCHIVE_FORMATS,
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process notebook image specification YAML and prepare notebook environment, data, and tests."
    )
    parser.add_argument(
        "spec_uri",
        nargs="?",
        default=None,
        type=str,
        help="URI to the YAML specification file:  simple path, file:// path, https://, http://, or s3://",
    )

    workflows_group = parser.add_argument_group(
        "Workflows", "Multi-step high level work flows for nb-wrangler tasks."
    )
    workflow_flags = [
        (
            "--curate",
            "curation",
            "Execute the curation workflow for spec development to add compiled requirements and build environments.",
        ),
        (
            "--reinstall",
            "reinstall",
            "Install requirements defined by a pre-compiled spec.",
        ),
        (
            "--reset-curation",
            "reset_curation",
            "Reset the environment, spec to force re-evuation of all inputs (env-delete, env-compact, spec-reset). NOTE: excludes deleting current repos;  can add --repos-delete",
        ),
        (
            "--data-curate",
            "data_curation",
            "Execute multi-step workflow to import data specs from notebook repos and collect metadata.",
        ),
        (
            "--data-reinstall",
            "data_reinstall",
            "Execute multi-step workflow to install and validate data, and define env vars, based on the wrangler spec.",
        ),
        (
            "--submit-for-build",
            "submit_for_build",
            "Submit fully elaborated requirements/spec for automatic image building.",
        ),
        (
            "--inject-spi",
            "inject_spi",
            "Inject curation products into the Science Platform Images repo clone at the specified existing 'deployment' to jump start 'classic builds'.",
        ),
    ]
    for flag, workflow_const, help in workflow_flags:
        workflows_group.add_argument(
            flag,
            dest=workflow_const,
            action="store_true",
            help=help,
        )
    # See below for setup of args.workflows after parsing

    spi_group = parser.add_argument_group(
        "SPI Automation",
        "Flags to automate Docker builds and git operations for --inject-spi.",
    )
    spi_group.add_argument(
        "--spi-branch",
        type=str,
        default="",
        # help=argparse.SUPPRESS,  # "Create a new branch in the SPI repo with this name."
    )
    spi_group.add_argument(
        "--spi-commit-message",
        nargs="+",
        default=[],
        # help=argparse.SUPPRESS,  # "Commit message for the new branch. If not provided, a default message will be used."
    )
    spi_group.add_argument(
        "--spi-prune",
        action="store_true",
        # help=argparse.SUPPRESS,  # "Prune old Docker images before a build."
    )
    spi_group.add_argument(
        "--spi-build",
        action="store_true",
        # help=argparse.SUPPRESS,  # "Trigger a Docker build in the SPI repo."
    )
    spi_group.add_argument(
        "--spi-push",
        action="store_true",
        help="Push the new branch to the remote SPI repo.",
    )
    spi_group.add_argument(
        "--spi-pr",
        action="store_true",
        help="Create a pull request for the new branch in the SPI repo.",
    )

    dev_group = parser.add_argument_group(
        "Development Overrides",
        "Flags for managing development-specific overrides in the spec.",
    )
    dev_group.add_argument(
        "--dev",
        action="store_true",
        help="Enable development overrides defined in the spec. (Implicit for some workflows).",
    )

    env_group = parser.add_argument_group(
        "Environment",
        "Setup and management of spec'ed base environment managed by mamba.",
    )
    env_group.add_argument(
        "--env-init",
        action="store_true",
        dest="env_init",
        help="Create and kernelize the target environment before curation run. See also --env-delete.",
    )
    env_group.add_argument(
        "--env-delete",
        action="store_true",
        dest="env_delete",
        help="Completely delete the target environment after processing.",
    )
    env_group.add_argument(
        "--env-pack",
        action="store_true",
        dest="env_pack",
        help="Pack the target environment into an archive file for distribution or archival.",
    )
    env_group.add_argument(
        "--env-unpack",
        action="store_true",
        dest="env_unpack",
        help="Unpack a previously packed archive file into the target environment directory.",
    )
    env_group.add_argument(
        "--env-register",
        action="store_true",
        dest="env_register",
        help="Register the target environment with Jupyter as a kernel.",
    )
    env_group.add_argument(
        "--env-unregister",
        action="store_true",
        dest="env_unregister",
        help="Unregister the target environment from Jupyter.",
    )
    env_group.add_argument(
        "--env-kernel-cleanup",
        action="store_true",
        help="Scans the user's kernel registry for 'dead' kernels (kernels pointing to non-existent environments) and removes them.",
    )
    env_group.add_argument(
        "--env-compact",
        action="store_true",
        dest="env_compact",
        help="Compact the wrangler installation by deleting package caches, etc.",
    )
    env_group.add_argument(
        "--env-archive-format",
        default="",
        type=str,
        dest="env_archive_format",
        help="Override format for environment pack/unpack, nominally one of: "
        + str(VALID_ARCHIVE_FORMATS),
    )
    env_group.add_argument(
        "--env-print-name",
        action="store_true",
        help="Print the environment name associated with this spec to stdout.",
    )
    packages_group = parser.add_argument_group(
        "Packages", "Setup and management of spec'ed Python packages managed by pip."
    )
    packages_group.add_argument(
        "--packages-compile",
        action="store_true",
        dest="packages_compile",
        help="Compile spec and input package lists to generate pinned requirements and other metadata for target environment.",
    )
    packages_group.add_argument(
        "--packages-omit-spi",
        action="store_true",
        dest="packages_omit_spi",
        help="Don't include the 'common' packages used by all missions in all current SPI based mission environments, may affect GUI capabilty.",
    )
    packages_group.add_argument(
        "--packages-install",
        action="store_true",
        dest="packages_install",
        help="Install compiled base and pip requirements into target/test environment.",
    )
    packages_group.add_argument(
        "--packages-uninstall",
        action="store_true",
        dest="packages_uninstall",
        help="Remove the compiled packages from the target environment after processing.",
    )

    testing_group = parser.add_argument_group("Testing", "Wrangler test commands.")
    testing_group.add_argument(
        "-t",
        "--test-all",
        default=None,
        const=".*",
        nargs="?",
        type=str,
        help="Run both --test-imports and --test-notebooks.",
    )
    testing_group.add_argument(
        "--test-imports",
        default=None,
        const=".*",
        nargs="?",
        type=str,
        help="Attempt to import every package explicitly imported by one of the spec'd notebooks.",
    )
    testing_group.add_argument(
        "--test-notebooks",
        "--test-notebooks-include",
        default=None,
        const=".*",
        nargs="?",
        type=str,
        help="Test spec'ed notebooks matching patterns (comma-separated regexes) in target environment. Default regex: .*",
    )
    testing_group.add_argument(
        "--test-notebooks-exclude",
        default=NOTEBOOK_TEST_EXCLUDE,
        type=str,
        help="Exclude notebooks from notebook test, defaulting to none,  otherwise comma-separated-regex str,  e.g. pat1,pat2",
    )
    testing_group.add_argument(
        "--jobs",
        default=NOTEBOOK_TEST_JOBS,
        type=int,
        help="Number of parallel jobs for notebook testing.",
    )
    testing_group.add_argument(
        "--timeout",
        default=NOTEBOOK_TEST_MAX_SECS,
        type=int,
        help="Timeout in seconds for notebook tests.",
    )

    data_group = parser.add_argument_group(
        "Data", "Setup and management of spec'ed application data."
    )
    data_group.add_argument(
        "--data-collect",
        action="store_true",
        help="Collect data archive and installation info and add to spec.",
    )
    data_group.add_argument(
        "--data-list",
        action="store_true",
        help="List out data archives which can be downloaded, stored, installed, etc.  Helps identify selection strings to operate on subsets of data.",
    )
    data_group.add_argument(
        "--data-download",
        action="store_true",
        help="Download data archive files to the pantry.",
    )
    data_group.add_argument(
        "--data-update",
        action="store_true",
        help="""Update metadata for data archives, e.g. length and hash.""",
    )
    data_group.add_argument(
        "--data-validate",
        action="store_true",
        help="""Validate the archive files stored in pantry against metadata from the wrangler spec.""",
    )
    data_group.add_argument(
        "--data-unpack",
        action="store_true",
        help="""Unpack the data archive files stored in pantry to the directory spec'd in --data-dir.""",
    )
    data_group.add_argument(
        "--data-pack",
        action="store_true",
        help="""Pack the live data directories in the pantry into their corresponding archive files, must be in spec.""",
    )
    data_group.add_argument(
        "--data-reset-spec",
        action="store_true",
        help="""Clear the 'data' sub-section of the 'out' section of the active nb-wrangler spec.""",
    )
    data_group.add_argument(
        "--data-delete",
        type=str,
        default="",
        choices=["archived", "unpacked", "both", ""],
        help="Delete data archive and/or unpacked files.",
    )
    data_group.add_argument(
        "--data-env-vars-mode",
        choices=["pantry", "spec"],
        default=DEFAULT_DATA_ENV_VARS_MODE,
        type=str,
        help="Define whether to locate unpacked data within the pantry or at locations from the refdata specs.",
    )
    data_group.add_argument(
        "--data-print-exports",
        action="store_true",
        help="Print sh/bash/zsh exports for data environment variables so they can be sourced or stored.",
    )
    data_group.add_argument(
        "--data-env-vars-no-auto-add",
        action="store_true",
        help="Do not automatically add data environment variables to nb-wrangler runtime os.environ.",
    )
    data_group.add_argument(
        "--data-select",
        default=".*",
        metavar="REGEXP",
        help="Regular expression to select specific data archives to operate on.",
    )
    data_group.add_argument(
        "--data-no-validation",
        action="store_true",
        help="""Skip data validatation metadata collection and verification.""",
    )
    data_group.add_argument(
        "--data-no-unpack-existing",
        action="store_true",
        help="""Skip data archive unpack if the target directory already exists indicating already unpacked.""",
    )
    data_group.add_argument(
        "--data-no-symlinks",
        action="store_true",
        help="""Do not create symlinks from install_data locations to the pantry data directory for the current spec during --data-unpack.""",
    )
    data_group.add_argument(
        "--data-symlinks",
        action="store_true",
        help="""Create symlinks from install_data locations to the pantry data directory for the current spec (standalone action, data not required).""",
    )
    notebook_group = parser.add_argument_group(
        "Notebook Clones",
        "Setup and management of local clones of spec'ed notebook repos.",
    )
    notebook_group.add_argument(
        "--clone-repos",
        action="store_true",
        help="Clone notebook repos to the directory indicated by --repos-dir.",
    )
    notebook_group.add_argument(
        "--repos-dir",
        type=str,
        default=REPOS_DIR,
        help="Directory where notebook and other repos will be cloned.",
    )
    notebook_group.add_argument(
        "--delete-repos",
        action="store_true",
        help="Delete --repo-dir and clones after processing.",
    )

    repo_update_group = notebook_group.add_mutually_exclusive_group()
    repo_update_group.add_argument(
        "--overwrite-local-changes",
        action="store_true",
        dest="overwrite_local_changes",
        help="In any cloned repo, overwrite any local, uncommitted changes to match the requested ref.",
    )
    repo_update_group.add_argument(
        "--stash-local-changes",
        action="store_true",
        dest="stash_local_changes",
        help="In any cloned repo, stash any local, uncommitted changes before matching the requested ref.",
    )

    spec_group = parser.add_argument_group(
        "Spec (nb-wrangler)", "Setup and management of wrangler spec itself."
    )
    spec_group.add_argument(
        "--spec-reset",
        action="store_true",
        dest="spec_reset",
        help="Reset spec to its original state by deleting output fields.  out.data section is preserved.",
    )
    spec_group.add_argument(
        "--spec-add",
        action="store_true",
        help="""Add the active spec to the pantry.  This creates a 'shelf' for one complete environment.""",
    )
    spec_group.add_argument(
        "--spec-list",
        action="store_true",
        help="""List all the available specs in the pantry.""",
    )
    spec_group.add_argument(
        "--spec-select",
        type=str,
        metavar="SPEC_REGEX",
        help="Select a stored spec by regex to use as the context for this wrangler run.",
    )

    spec_group.add_argument(
        "--spec-validate",
        action="store_true",
        dest="spec_validate",
        help="Validate the specification file without performing any curation actions.",
    )
    spec_group.add_argument(
        "--spec-update-hash",
        action="store_true",
        dest="spec_update_hash",
        help="Update spec SHA256 hash even if validation fails and continue processing.",
    )
    spec_group.add_argument(
        "--spec-ignore-hash",
        action="store_true",
        dest="spec_ignore_hash",
        help="Spec SHA256 hashes will not be added or verified upon re-installation.  Modifier to --validate and validation in general.",
    )
    spec_group.add_argument(
        "--spec-add-pip-hashes",
        action="store_true",
        dest="spec_add_pip_hashes",
        help="Record PyPi hashes of requested packages for more robust verification during later installs. Modifier to --compile only.",
    )
    spec_group.add_argument(
        "--finalize-dev-overrides",
        action="store_true",
        help="Remove the 'dev_overrides' section from the spec file.",
    )

    misc_group = parser.add_argument_group("Miscellaneous", "Global wrangler settings.")
    misc_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG log output",
    )
    misc_group.add_argument(
        "--debug",
        action="store_true",
        help="Drop into debugging with pdb on exceptions.",
    )
    misc_group.add_argument(
        "--profile",
        action="store_true",
        help="Run with cProfile and output profiling results to console.",
    )
    misc_group.add_argument(
        "--reset-log", action="store_true", help="Delete nb-wrangler.log file."
    )
    misc_group.add_argument(
        "--log-times",
        type=str,
        choices=VALID_LOG_TIME_MODES,
        default=DEFAULT_LOG_TIMES_MODE,
        help="Include timestamps in log messages, either as absolute/normal or elapsed times, both, or none.",
    )
    misc_group.add_argument(
        "--color",
        choices=VALID_COLOR_MODES,
        default=DEFAULT_COLOR_MODE,
        help="Colorize the log.",
    )
    misc_group.add_argument(
        "--version",
        action="store_true",
        help="Print the version of nb-wrangler to stdout and stop.",
    )

    parsed = parser.parse_args()

    workflows = [
        workflow[1] for workflow in workflow_flags if getattr(parsed, workflow[1], None)
    ]
    setattr(parsed, "workflows", workflows)

    return parsed


def main() -> int:
    """Main entry point for the CLI."""
    args = parse_args()
    if args.version:
        print(constants.__version__)
        return 0
    if args.spec_uri is None:
        log = logger.WranglerLogger()
        if os.environ.get("NBW_SPEC") is None:
            log.error("No wrangler spec given and NBW_SPEC is not set, quitting...")
            return 1
        else:
            spec = os.environ["NBW_SPEC"]
            log.info(f"Using spec defined by NBW_SPEC = {spec}")
            args.spec_uri = spec
    if args.profile:
        with cProfile.Profile() as pr:
            success = _main(args)
            pstats.Stats(pr).sort_stats("cumulative").print_stats(50)
    else:
        success = _main(args)

    return success


def _main(args) -> int:
    """Main entry point for the CLI."""
    config = config_mod.WranglerConfig.from_args(args)
    config_mod.set_args_config(config)
    log = logger.get_configured_logger()
    try:
        # Create configuration using simplified factory method
        if not config:
            log.error("Unable to initialize nb-wrangler. Stopping...")
            return 1
        config.spec_file = spec = utils.uri_to_local_path(args.spec_uri)
        if not spec:
            log.error("Failed reading URI:", args.spec_uri)
            exit_code = 1
        else:
            notebook_wrangler = wrangler.NotebookWrangler()
            exit_code = notebook_wrangler.main()
            notebook_wrangler.logger.print_log_counters()
    except KeyboardInterrupt:
        return log.error("Operation cancelled by user")
    except Exception as e:
        exit_code = log.exception(e, "Failed:")
    return 1 if not exit_code else 0


if __name__ == "__main__":
    sys.exit(int(main()))
