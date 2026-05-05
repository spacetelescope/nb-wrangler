"""Requirements compilation and dependency resolution."""

import sys
from pathlib import Path
import httpx
from typing import Any
import re

from .config import WranglerConfigurable
from .logger import WranglerLoggable
from .environment import WranglerEnvable
from .constants import TARGET_PACKAGES, PIP_COMPILE_TIMEOUT
from .repository import RepositoryManager
from .spec_manager import SpecManager
from .injector import SpiInjector
from .utils import get_yaml
from . import utils


class RequirementsCompiler(WranglerConfigurable, WranglerLoggable, WranglerEnvable):
    """Compiles and resolves package requirements."""

    def __init__(
        self,
        spec_manager: SpecManager,
        repo_manager: RepositoryManager,
        python_path: str = sys.executable,
    ):
        super().__init__()
        self.spec_manager = spec_manager
        self.repo_manager = repo_manager
        self.python_path = python_path

    def find_requirements_files(self, notebook_paths: list[str]) -> list[Path]:
        """Find requirements.txt files in notebook directories."""
        requirements_files = []
        notebook_dirs = {Path(nb_path).parent for nb_path in notebook_paths}
        for dir_path in notebook_dirs:
            req_file = dir_path / "requirements.txt"
            if req_file.exists():
                requirements_files.append(req_file)
                self.logger.debug(f"Found requirements file: {req_file}")
        self.logger.info(
            f"Found {len(requirements_files)} notebook requirements.txt files."
        )
        return requirements_files

    def compile_requirements(
        self,
        package_files: list[str],
        output_path: Path,
        override_pip_versions_file: str,
    ) -> bool:
        """Compile requirements files into pinned versions,  outputs
        the result to a file at `output_path` and then loads the
        output and returns a list of package versions for insertion
        into other commands and specs.
        """
        if not package_files:
            return self.logger.warning("No package list to resolve versions for.")

        self.logger.info(
            "Compiling combined pip requirements to determine package versions "
        )

        if "uv pip" in str(self.config.pip_command):
            if not self._run_uv_compile(
                output_path, package_files, override_pip_versions_file
            ):
                return self.logger.error(
                    "========== Failed compiling combined pip requirements with uv =========="
                )
        elif not self._run_pip_compile(
            output_path, package_files, override_pip_versions_file
        ):
            return self.logger.error(
                "========== Failed compiling combined pip requirements with pip =========="
            )
        package_versions = self.read_package_versions([output_path])
        return self.logger.info(
            f"Compiled combined pip requirements to {len(package_versions)} package versions."
        )

    def _run_uv_compile(
        self,
        output_file: Path,
        requirements_files: list[str],
        override_pip_versions_file: str,
    ) -> bool:
        """Run uv pip compile command to resolve pip package constraints."""
        python_ver = (
            f"--python-version {self.spec_manager.python_version}"
            if self.spec_manager.python_version
            else ""
        )
        overrides = (
            f"--overrides {override_pip_versions_file}"
            if override_pip_versions_file
            else ""
        )
        pip_command = re.sub(r"^pip$", r"uv pip ", str(self.config.pip_command))
        cmd = (
            f"{pip_command} compile --quiet --output-file {str(output_file)} --python {self.python_path}"
            + f" --universal {python_ver}"
            + " --no-header --annotate"
            + f" {overrides}"
        )
        for f in requirements_files:
            cmd += " " + f
        result = self.env_manager.wrangler_run(
            cmd, check=False, timeout=PIP_COMPILE_TIMEOUT
        )
        return self.env_manager.handle_result(
            result, f"{self.config.pip_command} compile failed: "
        )

    def _run_pip_compile(
        self,
        output_file: Path,
        requirements_files: list[str],
        override_pip_versions_file: str,
    ) -> bool:
        """Run classic pip compile command to resolve pip package constraints."""

        # Fix: Build args properly to avoid empty arguments

        overrides = f"--overrides {override_pip_versions_file} if override_pip_versions_file else "
        if overrides.strip():
            self.logger.warning(
                "Pip cannot compile with overrides because no --overrides switch exists."
            )
            self.logger.warning("Attemptng to switch compilation to uv pip.")
            return self._run_uv_compile(
                output_file, requirements_files, override_pip_versions_file
            )

        base_cmd_parts = [
            str(self.config.pip_command),
            # f"--python {self.python_path}",
            "install",
            "--quiet",
            "--only-binary=all",
            overrides,
        ]
        cmd_parts = base_cmd_parts.copy()
        for req_file in requirements_files:
            self.logger.debug(f"Added {req_file} to pip compile command.")
            cmd_parts += [f" -r {req_file}"]
        cmd = " ".join(cmd_parts)

        result = self.env_manager.env_run(
            self.spec_manager.kernel_name, cmd, check=False, timeout=PIP_COMPILE_TIMEOUT
        )
        if not self.env_manager.handle_result(
            result, f"{self.config.pip_command} compile failed: "
        ):
            return False

        cmd = f"{str(self.config.pip_command)} freeze --quiet"
        result = self.env_manager.env_run(
            self.spec_manager.kernel_name, cmd, check=False, timeout=PIP_COMPILE_TIMEOUT
        )
        if not self.env_manager.handle_result(
            result, f"{self.config.pip_command} freeze failed: "
        ):
            return False
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        lines = [line for line in lines if "@ file:///" not in line]
        print(lines)
        try:
            with output_file.open("w+") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            return self.logger.exception(
                e, f"Failed writing pip freeze output to '{output_file}'"
            )
        return True

    def read_package_versions(self, requirements_files: list[Path]) -> list[str]:
        """Read package versions from a list of requirements files omitting blank
        and comment lines.
        """
        package_versions = []
        for req_file in sorted(requirements_files):
            lines = self._read_package_lines(req_file)
            package_versions.extend(lines)
        return sorted(list(set(package_versions)))

    def _read_package_lines(self, requirements_file: Path) -> list[str]:
        """Read package lines from requirements file omitting blank and comment lines.
        Should work with most forms of requirements.txt file,
        input or compiled,  and reduce it to a pure list of package versions.
        """
        lines = []
        with open(requirements_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith(("#", "--hash")):
                    lines.append(line)
        return sorted(lines)

    def consolidate_environment(
        self, notebook_paths: list[str], injector: SpiInjector, output_dir: Path
    ) -> tuple[
        Any,
        dict[Any, Any],
        dict[str, Any],
        list[str],
    ]:
        """
        Orchestrates the compilation of the entire environment, including fetching external specs
        and consolidating with other wrangler spec and notebook requirements.

        Returns:
            A tuple containing:
            - Resolved kernel_name
            - final_mamba_spec
            - dict[mamba pkg kind, packages]
            - list[non-mamba-package-files]
        """
        try:
            base_mamba_spec = self._get_base_mamba_spec()
            kernel_name = base_mamba_spec.get("name")
            if not kernel_name:
                raise ValueError("Could not determine kernel name from Mamba spec.")

            # Get SPI requirements now that we have a definitive kernel_name
            spi_mamba_files = injector.find_spi_mamba_files()

            all_mamba_pkg_map = dict(
                base_mamba_deps=base_mamba_spec.get("dependencies", []),
                common_mamba_packages=list(self.spec_manager.common_mamba_packages),
                extra_mamba_packages=list(self.spec_manager.extra_mamba_packages),
                spi_mamba_packages=self.read_package_versions(spi_mamba_files),
                wrangler_target_packages=TARGET_PACKAGES,
            )

            mamba_dep_list = [
                pkg for sublist in sorted(all_mamba_pkg_map.values()) for pkg in sublist
            ]

            final_mamba_spec = dict(base_mamba_spec)
            final_mamba_spec["dependencies"] = mamba_dep_list
            if "channels" not in final_mamba_spec:
                final_mamba_spec["channels"] = ["conda-forge"]
            final_mamba_spec["name"] = kernel_name

            # Pip
            notebook_req_files = self.find_requirements_files(notebook_paths)
            spi_pip_files = injector.find_spi_pip_files()
            extra_pip_packages_file = utils.writelines(
                self.spec_manager.extra_pip_packages, "extra_pip_packages.txt"
            )
            common_pip_packages_file = utils.writelines(
                self.spec_manager.common_pip_packages, "common_pip_packages.txt"
            )
            # These paths should make self-identify where they came from, hence
            # no dictionary needed here.
            non_mamba_pip_req_files = list(notebook_req_files)
            non_mamba_pip_req_files.extend(spi_pip_files)
            non_mamba_pip_req_files.append(Path(extra_pip_packages_file))
            non_mamba_pip_req_files.append(Path(common_pip_packages_file))

            return (
                kernel_name,
                final_mamba_spec,
                all_mamba_pkg_map,
                [str(path) for path in non_mamba_pip_req_files],
            )
        except Exception as e:
            return self.logger.exception(
                e, "Failed to consolidate environment definition."
            )

    def _get_base_mamba_spec(self) -> dict:
        """Determines which of the four methods is used and returns the base mamba spec as a dict."""
        # Method 2: Inline Spec (Concatenated File)
        if self.spec_manager.inline_mamba_spec:
            self.logger.info("Using inline (concatenated) mamba spec.")
            return self.spec_manager.inline_mamba_spec

        # Method 3 & 4: External Spec
        if self.spec_manager.environment_spec:
            spec_def = self.spec_manager.environment_spec
            if "uri" in spec_def:
                uri = spec_def["uri"]
                self.logger.info(f"Using external mamba spec from URI: {uri}")
                return self._load_spec_from_uri(uri)
            if "repo" in spec_def and "path" in spec_def:
                repo = spec_def["repo"]
                path = spec_def["path"]
                self.logger.info(
                    f"Using external mamba spec from repo '{repo}' at path '{path}'."
                )
                # This assumes the repo_manager in the main wrangler class has the repo cloned
                repo_path = self.repo_manager.get_repo_path(repo)
                if not repo_path:
                    raise FileNotFoundError(f"Could not find path for repo '{repo}'.")
                spec_path = repo_path / path
                if not spec_path.exists():
                    raise FileNotFoundError(
                        f"Mamba spec file not found at '{spec_path}'."
                    )
                with spec_path.open("r") as f:
                    return get_yaml().load(f)

        # Method 1: Simple Definition
        if self.spec_manager.python_version:
            self.logger.info(
                f"Using simple definition with python_version={self.spec_manager.python_version}."
            )
            return {
                "name": self.spec_manager.kernel_name,
                "channels": ["conda-forge"],
                "dependencies": [f"python={self.spec_manager.python_version}"],
            }

        raise ValueError("Could not determine base mamba spec. Spec is invalid.")

    def _load_spec_from_uri(self, uri: str) -> dict:
        """Loads a spec from a URI (http, https, or local file path)."""
        if uri.startswith(("http://", "https://")):
            try:
                response = httpx.get(uri, timeout=10)
                response.raise_for_status()
                return get_yaml().load(response.text)
            except Exception as e:
                raise IOError(f"Failed to fetch mamba spec from URL '{uri}': {e}")
        else:
            # Treat as a local file path relative to the main spec file
            spec_path = self.spec_manager.spec_file.parent / uri
            if not spec_path.exists():
                raise FileNotFoundError(f"Mamba spec file not found at '{spec_path}'.")
            with spec_path.open("r") as f:
                return get_yaml().load(f)

    def write_mamba_spec_file(self, filepath: Path, mamba_spec: dict) -> bool:
        """Write mamba spec dictionary to YAML file."""
        try:
            with filepath.open("w+") as f:
                get_yaml().dump(mamba_spec, f)
        except Exception as e:
            return self.logger.exception(e, f"Failed writing mamba spec {filepath}")
        self.logger.debug(f"Wrote mamba spec to '{filepath}'")
        return True

    def write_pip_requirements_file(
        self, filepath: str, package_versions: list
    ) -> bool:
        """Write package versions to pip requirements file."""
        try:
            with Path(filepath).open("w+") as f:
                for package_version in package_versions:
                    f.write(f"{package_version}\n")
        except Exception as e:
            return self.logger.exception(
                e, f"Failed writing pip requirements to '{filepath}'."
            )
        self.logger.debug(f"Wrote pip target env package versions to '{filepath}'")
        return True
