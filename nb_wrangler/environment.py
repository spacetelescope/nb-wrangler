"""Environment management for package installation and testing.

The basic model is that micromamba is used to bootstrap and manage
both the curation and target environments.

micromamba is used to install only pre-required mamba packages.
uv is used to manage pip packages in the target environment.

environmentsinstall non-pip Python packages
"""

import os
import json
import shutil
import shlex
import re
import subprocess
from subprocess import CompletedProcess
from pathlib import Path
from typing import Any, Optional
from collections.abc import Callable


from .logger import WranglerLoggable
from .config import WranglerConfigurable

from .constants import (
    NBW_ROOT,
    NBW_PANTRY,
    NBW_MM,
    NBW_CACHE,
)
from .constants import (
    DEFAULT_TIMEOUT,
    ENV_CREATE_TIMEOUT,
    INSTALL_PACKAGES_TIMEOUT,
    IMPORT_TEST_TIMEOUT,
)
from . import utils


class EnvironmentManager(WranglerConfigurable, WranglerLoggable):
    """Manages Python environment setup and package installation."""

    # Currently limited to uv, older build tools for packages not yet
    # updated to pyproject.toml, and jupyter kernel management packages
    # ipykernel and jupyter.
    # Package definitions moved to constants.py

    # IMPORTANT: see also the nb-wrangler bash script used for bootstrapping
    # the basic nbwrangler environment and inlines the above requirements
    # for CURATOR_PACKAGES.
    # Timeout constants moved to constants.py

    # ------------------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self.mamba_command = str(self.config.mamba_command)
        self.pip_command = str(self.config.pip_command)
        self.nbw_pantry_dir.mkdir(exist_ok=True, parents=True)

    @property
    def nbw_root_dir(self) -> Path:
        return NBW_ROOT

    @property
    def nbw_mm_dir(self) -> Path:
        return NBW_MM

    @property
    def nbw_pantry_dir(self) -> Path:
        return NBW_PANTRY

    @property
    def mm_pkgs_dir(self) -> Path:
        return self.nbw_mm_dir / "pkgs"

    @property
    def nbw_temp_dir(self) -> Path:
        return self.nbw_root_dir / "temp"

    @property
    def nbw_cache_dir(self) -> Path:
        return Path(NBW_CACHE)

    def mm_envs_dir(self, env_name: str) -> Path:
        if self.is_base_env_alias(env_name):
            return self.nbw_mm_dir
        else:
            return self.nbw_mm_dir / "envs"

    def env_live_path(self, env_name: str) -> Path:
        if self.is_base_env_alias(env_name):
            return self.mm_envs_dir(env_name)
        else:
            return self.mm_envs_dir(env_name) / env_name

    # ------------------------------------------------------------------------------

    def _condition_cmd(self, cmd: list[str] | tuple[str] | str) -> list[str]:
        """Condition the command into a list of UNIX CLI 'words'.

        If command is already a string,  split it into string "words".
        If it is a list,  make sure every element is a string.
        """
        if isinstance(cmd, (list, tuple)):
            rval = [str(word) for word in cmd]
        elif isinstance(cmd, str):
            rval = shlex.split(cmd)
        else:
            raise TypeError("cmd must be a list or str")
        # self.logger.debug("Conditioning:", repr(cmd), "-->", rval)
        return rval

    def wrangler_run(
        self,
        command: list[str] | tuple[str] | str,
        check=True,
        cwd=None,
        timeout=DEFAULT_TIMEOUT,
        text=True,
        output_mode="separate",
        **extra_parameters,
    ):  # -> str | CompletedProcess[Any] | None:
        """Run a command in the current environment."""
        command = self._condition_cmd(command)
        parameters = dict(
            text=text,
            check=check,
            cwd=str(cwd) if cwd else cwd,
            timeout=timeout,
        )
        if output_mode == "combined":
            parameters.update(
                dict(
                    capture_output=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            )
        elif output_mode == "separate":
            parameters.update(
                dict(
                    capture_output=True,
                )
            )
        elif output_mode == "uncaught":
            parameters.update(
                dict(
                    capture_output=False,
                    stdout=None,
                    stderr=None,
                    stdin=None,
                )
            )
        else:
            raise ValueError(f"Invalid output_mode value: {output_mode}")
        parameters.update(extra_parameters)
        self.logger.debug(f"Running command with no shell: {command} {parameters}")
        # self.logger.debug(f"For trying it this may work anyway: {' '.join(command)}")
        result = subprocess.run(command, **parameters)
        # self.logger.debug(f"Command output: {result.stdout}")
        if check:
            return result.stdout
        else:
            return result

    def env_run(
        self, environment, command: tuple[str] | list[str] | str, **keys
    ):  # -> str | CompletedProcess[Any] | None:
        """Run a command in the specified environment.

        See EnvironmentManager.run for **keys optional settings.
        """
        command = self._condition_cmd(command)
        if not self.is_base_env_alias(environment):
            self.logger.debug(
                f"Running command {command} in environment: {environment}"
            )
            mm_prefix = [self.mamba_command, "run", "-n", environment]
        else:
            self.logger.debug(
                f"Running command {command} in base environment for kernel {environment}"
            )
            mm_prefix = []
        return self.wrangler_run(mm_prefix + command, **keys)

    def handle_result(
        self,
        result: CompletedProcess[Any] | str | None,
        fail: str,
        success: str = "",
        error_func: Optional[Callable] = None,
    ) -> bool:
        """Provide standard handling for the check=False case of the xxx_run methods by
        issuing a success info or fail error and returning True or False respectively
        depending on the return code of a subprocess result.

        If either the success or fail log messages (stripped) end in ":" then append
        result.stdout or result.stderr respectively.
        """
        error_func = error_func or self.logger.error
        if not isinstance(result, CompletedProcess):
            raise RuntimeError(f"Expected CompletedProcess, got {type(result)}")
        if result.returncode != 0:
            if fail.strip().endswith(":"):
                fail += result.stderr.strip() + " ::: " + result.stdout.strip()
            return error_func(fail)
        else:
            if success.strip().endswith(":"):
                success += result.stdout.strip()
            return self.logger.info(success) if success else True

    def create_environment(
        self, env_name: str, micromamba_specfile: Path | None = None
    ) -> bool:
        """Create a new environment."""
        self.logger.info(f"Creating environment: {env_name}")
        mm_prefix = [self.mamba_command, "create", "--yes", "-n", env_name]
        command = mm_prefix + ["-f", str(micromamba_specfile)]
        result = self.wrangler_run(command, check=False, timeout=ENV_CREATE_TIMEOUT)
        return self.handle_result(
            result,
            f"Failed to create environment {env_name}: \n",
            f"Environment {env_name} created. It needs to be registered before JupyterLab will display it as an option.",
        )

    def delete_environment(self, env_name: str) -> bool:
        """Delete an existing environment."""
        if self.environment_exists(env_name):
            self.logger.info(f"Deleting environment: {env_name}")
            command = self.mamba_command + " env remove --yes -n " + env_name
            result = self.wrangler_run(command, check=False, timeout=ENV_CREATE_TIMEOUT)
            return self.handle_result(
                result,
                f"Failed to delete environment {env_name}: \n",
                f"Environment {env_name} deleted. It's totally gone, file storage reclaimed.",
            )
        else:
            return self.logger.warning(
                f"Skipping --delete-environment for {env_name} wrangler does not believe exists."
            )

    def _get_package_file(
        self, env_name: str, pip_packages: list[str]
    ) -> tuple[int, str]:
        """Strip down package list to omit comment lines so we can count packages.
        Write out the stripped down list to a
        """
        stripped_packages = [
            pkg for pkg in pip_packages if not pkg.strip().startswith("#")
        ]
        req_path = utils.writelines(
            stripped_packages, self.nbw_temp_dir / f"package_reqs_{env_name}.txt"
        )
        return len(stripped_packages), req_path

    def install_packages(self, env_name: str, pip_packages: list[str]) -> bool:
        """Install the compiled pip package list."""
        if not pip_packages:
            self.logger.info("No pip packages to install.")
            return True

        n_packages, req_path = self._get_package_file(env_name, pip_packages)
        self.logger.info(f"Installing {n_packages} packages to environment {env_name}.")

        cmd = f"{self.pip_command} install -r {req_path}"
        result = self.env_run(
            env_name, cmd, check=False, timeout=INSTALL_PACKAGES_TIMEOUT
        )
        return self.handle_result(
            result,
            f"Package installation for {env_name} failed:",
            f"Package installation for {env_name} completed successfully.",
        )

    def uninstall_packages(
        self,
        env_name: str,
        pip_packages: list[str],
    ) -> bool:
        """Uninstall the compiled package lists."""
        if not pip_packages:
            self.logger.info("No pip packages to uninstall.")
            return True

        n_packages, req_path = self._get_package_file(env_name, pip_packages)
        self.logger.info(
            f"Uninstalling {n_packages} packages from environment {env_name}."
        )

        # Uninstall packages using uv
        cmd = f"{self.pip_command} uninstall -r {req_path}"
        result = self.env_run(
            env_name, cmd, check=False, timeout=INSTALL_PACKAGES_TIMEOUT
        )
        return self.handle_result(
            result,
            f"Package un-installation of {env_name} failed:",
            f"Package un-installation of {env_name} completed successfully.",
        )

    def register_environment(
        self, env_name: str, display_name: str, env_vars: dict[str, str]
    ) -> bool:
        """Register Jupyter environment for the environment.

        nbwrangler environment should work here since it is modifying
        files under $HOME related to *any* jupyter environment the
        user has.
        """
        env_switches = ""
        for key, value in env_vars.items():
            env_switches += f"--env '{key}' '{value}' "
        cmd = self._condition_cmd(
            f"python -m ipykernel install --user --name '{env_name}' --display-name '{display_name}' {env_switches}"
        )
        result = self.env_run(env_name, cmd, check=False)
        return self.handle_result(
            result,
            f"Failed to register environment {env_name} as a jupyter kernel: ",
            f"Registered environment {env_name} as a jupyter kernel making it visible to JupyterLab as '{display_name}'.",
        )

    def unregister_environment(self, env_name: str) -> bool:
        """Unregister Jupyter environment for the environment."""
        if self.environment_exists(env_name):
            cmd = f"jupyter kernelspec uninstall -y {env_name}"
            result = self.wrangler_run(cmd, check=False)
            return self.handle_result(
                result,
                f"Failed to unregister Jupyter kernel {env_name}: ",
                f"Unregistered Jupyter kernel {env_name}. Environment {env_name} still exists but is no longer offered by JupyterLab.",
            )
        else:
            return self.logger.warning(
                f"Skipping --env-unregister for {env_name} that wrangler does not believe exists."
            )

    def environment_exists(self, env_name: str) -> bool:
        """Return True IFF `env_name` exists."""
        self.logger.debug(f"Checking existence of {env_name}.")
        if self.is_base_env_alias(env_name):
            return True
        envs = self.get_existing_envs()
        for env in envs:
            self.logger.debug(f"Checking existence of {env_name} against {env}.")
            if env.startswith(str(NBW_MM)) and env.endswith(env_name):
                self.logger.debug(f"Environment {env_name} exists.")
                return True
        self.logger.debug(f"Environment {env_name} does not exist.")
        return False

    def get_existing_envs(self) -> list[str]:
        cmd = self.mamba_command + " env list --json"
        try:
            result = self.wrangler_run(cmd, check=True)
        except Exception as e:
            self.logger.exception(
                e,
                "Checking for existence of environment completely failed. See README.md for info on bootstrapping.",
            )
            return []
        if result is None:
            self.logger.error("No result returned from environment check")
            return []
        result_str = result.stdout if hasattr(result, "stdout") else str(result)
        envs = json.loads(result_str)["envs"]
        self.logger.debug(f"Found existing environments: {envs}")
        return envs

    def is_base_env_alias(self, env_name: str) -> bool:
        if env_name in ["base", "python3"]:
            self.logger.debug(
                f"Environment / kernel {env_name} is assumed to be the base environment."
            )
            return True
        return False

    def compact(self) -> bool:
        """Clear cach directories w/o deleting the top level dir, only
        it's contents.
        """
        try:
            if self.mm_pkgs_dir.exists():
                utils.clear_directory(str(self.mm_pkgs_dir))
            if self.nbw_cache_dir.exists():
                utils.clear_directory(str(self.nbw_cache_dir))
            if self.nbw_temp_dir.exists():
                utils.clear_directory(str(self.nbw_temp_dir))
            self.logger.info(
                "Wrangler compacted successfully, removing install caches, etc."
            )
            return True
        except Exception as e:
            return self.logger.exception(e, f"Failed to compact wrangler: {e}")

    def test_nb_imports(
        self, env_name: str, nb_to_imports: dict[str, list[str]]
    ) -> bool:
        """This code is necessary only because some notebook repos permit notebooks to have
        local .py files in the same dir as the notebook.  Hence to run the notebook correctly,
        one needs to be in the notebook's directory or a copy of it for the .py file to import
        correctly.  The alternative of sticking the nb directory on PYTHONPATH has the problem
        where different notebooks might decide to include "my_requirements.py" and one of them
        will get the wrong version.
        """
        self.logger.info(
            f"Testing imports by notebook for {len(nb_to_imports)} notebooks..."
        )
        no_errors = True
        for notebook, imports in nb_to_imports.items():
            here = os.getcwd()
            try:
                notebook_include_regex = (
                    self.config.test_imports or self.config.test_all or ""
                )
                if not re.search(notebook_include_regex, notebook):
                    self.logger.debug(
                        f"Skipping import tests for {notebook} not matching include regex {notebook_include_regex}."
                    )
                    continue
                os.chdir(Path(notebook).parent)
                self.logger.info(f"Testing imports for {notebook}.")
                no_errors = self.test_imports(env_name, imports) and no_errors
            except Exception as e:
                self.logger.exception(f"Failed due to exception: {e}.")
                no_errors = False
            finally:
                os.chdir(here)
        return no_errors

    def test_imports(self, env_name: str, imports: list[str]) -> bool:
        """Test package imports."""
        self.logger.info(f"Testing {len(imports)} imports")
        failed_imports = []
        for import_ in imports:
            self.logger.debug(f"Testing import: {import_}")
            result = self.env_run(
                env_name,
                f"python -c 'import {import_}'",
                check=False,
                timeout=IMPORT_TEST_TIMEOUT,
            )
            succeeded = self.handle_result(
                result,
                f"Failed to import {import_}:",
                f"Import of {import_} succeeded.",
            )
            if not succeeded:
                failed_imports.append(import_)
        if failed_imports:
            return self.logger.error(
                f"Failed to import {len(failed_imports)}: {failed_imports}"
            )
        else:
            return self.logger.info("All imports succeeded.")

    def cleanup_dead_kernels(self) -> bool:
        """Scan for and remove 'dead' jupyter kernels from the user's registry."""
        self.logger.info("Scanning for and removing dead kernels...")
        kernels_dir = Path.home() / ".local" / "share" / "jupyter" / "kernels"
        if not kernels_dir.is_dir():
            self.logger.debug(
                f"Kernel directory not found at '{kernels_dir}'. Nothing to clean up."
            )
            return True

        no_errors = True
        for kernel_dir in kernels_dir.iterdir():
            if not kernel_dir.is_dir():
                continue

            kernel_json_path = kernel_dir / "kernel.json"
            if not kernel_json_path.exists():
                self.logger.debug(f"No kernel.json in '{kernel_dir}', skipping.")
                continue

            try:
                with open(kernel_json_path, "r") as f:
                    data = json.load(f)

                argv = data.get("argv", [])
                if not argv:
                    self.logger.warning(
                        f"Malformed kernel.json in '{kernel_dir}' (no argv), skipping."
                    )
                    continue

                python_executable = Path(argv[0])
                if not python_executable.exists():
                    self.logger.info(
                        f"Found dead kernel '{kernel_dir.name}' pointing to non-existent python '{python_executable}'. Removing."
                    )
                    shutil.rmtree(kernel_dir)

            except json.JSONDecodeError:
                self.logger.warning(
                    f"Could not parse kernel.json in '{kernel_dir}', skipping."
                )
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred while processing '{kernel_dir.name}': {e}"
                )
                no_errors = False

        return no_errors


class WranglerEnvable:
    def __init__(self):
        # print("WranglerEnvable")
        super().__init__()
        self.env_manager = EnvironmentManager()
