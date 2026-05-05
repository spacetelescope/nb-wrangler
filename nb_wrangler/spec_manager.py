import os.path
import re
import datetime
from typing import Any, Optional
from pathlib import Path
import copy

from . import utils
from .logger import WranglerLoggable
from .config import WranglerConfigurable  # Import WranglerConfigurable
from .constants import DEFAULT_ARCHIVE_FORMAT, VALID_ARCHIVE_FORMATS
from .constants import WRANGLER_SPEC_VERSION


class SpecManager(
    WranglerLoggable, WranglerConfigurable
):  # Inherit from WranglerConfigurable
    """Manages specification loading, validation, access, and persistence."""

    def __init__(self):
        super().__init__()
        self._spec = {}
        self._is_validated = False
        self._source_file = Path("")
        self._initial_spec_sha256 = None
        self._source_file: Path = Path()  # Explicitly typed

    # ---------------------------- Property-based read/write access to spec data -------------------
    @property
    def header(self):
        return self._spec["image_spec_header"]

    @property
    def deployment_name(self) -> str:
        """If omitted in image_header, deployment_name defaults to 'wrangler'
        which is the universal deployment for modern wrangler builds where the
        wrangler spec defines more-or-less everything.
        """
        return self.header.get("deployment_name", "wrangler")

    @property
    def kernel_name(self) -> str | None:  # also environment_name / env_name
        if "kernel_name" in self.header:
            return self.header.get("kernel_name")
        elif self.inline_mamba_spec:
            return self.inline_mamba_spec.get("name")
        elif self.environment_spec:
            # Check if already compiled and stored in output
            if output_kernel_name := self.get_output_data("kernel_name"):
                return output_kernel_name
            raise AttributeError(
                "`kernel_name` cannot be determined from an external spec until it has been fetched and parsed by the compiler."
            )
        return None

    @property
    def display_name(self) -> str:  # readable name in lab menu
        return self.header.get("display_name", self.kernel_name)

    @property
    def image_name(self) -> str:
        return self.header["image_name"]

    @property
    def spec_id(self) -> str | None:
        return self.sha256[:6] if self.sha256 is not None else None

    @property
    def description(self) -> str:
        return self.header["description"]

    @property
    def python_version(self) -> str | None:
        # This property is only valid in "simple" mode.
        if self.inline_mamba_spec or self.environment_spec:
            return None
        return self.header.get("python_version")

    @property
    def repositories(self) -> dict[str, Any]:
        """Return repositories, applying dev_overrides if enabled."""
        base_repos = self._spec.get("repositories") or {}
        if self.config.dev and "dev_overrides" in self._spec:
            dev_repos = self._spec["dev_overrides"].get("repositories") or {}
            # Merge dev_repos into base_repos, overwriting if keys conflict
            merged_repos = copy.deepcopy(base_repos)
            for repo_name, dev_repo_config in dev_repos.items():
                if repo_name in merged_repos:
                    # Merge individual fields, dev_repo_config takes precedence
                    merged_repos[repo_name].update(dev_repo_config)
                else:
                    # Add new dev_override repositories
                    merged_repos[repo_name] = dev_repo_config
            return merged_repos
        return base_repos

    def dev_overrides_exist(self) -> bool:
        """Check if the 'dev_overrides' section exists in the spec."""
        return "dev_overrides" in self._spec

    @property
    def notebook_selections(self) -> dict[str, Any]:
        return self._spec.get("selected_notebooks") or {}

    @property
    def refdata_dependencies(self) -> dict[str, Any] | None:
        """Return refdata_dependencies, applying dev_overrides if enabled."""
        base_refdata = self._spec.get("refdata_dependencies")
        if self.config.dev and "dev_overrides" in self._spec:
            dev_refdata = self._spec["dev_overrides"].get("refdata_dependencies")
            if dev_refdata:
                merged = copy.deepcopy(base_refdata) if base_refdata else {}
                for key in ["install_files", "other_variables"]:
                    if key in dev_refdata:
                        if key not in merged or not isinstance(merged[key], dict):
                            merged[key] = {}
                        merged[key].update(dev_refdata[key])
                return merged
        return base_refdata

    @property
    def system(self) -> dict[str, Any]:
        return self._spec["system"]

    @property
    def extra_mamba_packages(self) -> list[str]:
        return list(self._spec.get("extra_mamba_packages") or [])

    @property
    def common_mamba_packages(self) -> list[str]:
        return list(self._spec.get("common_mamba_packages") or [])

    @property
    def extra_pip_packages(self) -> list[str]:
        return list(self._spec.get("extra_pip_packages") or [])

    @property
    def common_pip_packages(self) -> list[str]:
        return list(self._spec.get("common_pip_packages") or [])

    @property
    def override_pip_versions(self) -> list[str]:
        return list(self._spec.get("override_pip_versions") or [])

    @property
    def environment_spec(self) -> dict[str, Any] | None:
        return self._spec.get("environment_spec")

    @property
    def spi(self) -> dict[str, str]:
        base_spi = self.system.get("spi") or {}
        if self.config.dev and "dev_overrides" in self._spec:
            if "system" in self._spec["dev_overrides"]:
                dev_spi = self._spec["dev_overrides"]["system"].get("spi") or {}
                if dev_spi:
                    merged_spi = copy.deepcopy(base_spi)
                    merged_spi.update(dev_spi)
                    return merged_spi
        return base_spi

    @property
    def nb_wrangler(self) -> dict[str, str]:
        base_nbw = self.system.get("nb-wrangler") or {}
        if self.config.dev and "dev_overrides" in self._spec:
            if "system" in self._spec["dev_overrides"]:
                dev_nbw = self._spec["dev_overrides"]["system"].get("nb-wrangler") or {}
                if dev_nbw:
                    merged_nbw = copy.deepcopy(base_nbw)
                    merged_nbw.update(dev_nbw)
                    return merged_nbw
        return base_nbw

    @property
    def primary_repo(self) -> str | None:
        """Get the primary repository for this spec, if defined."""
        base_primary = self.system.get("primary_repo")
        if self.config.dev and "dev_overrides" in self._spec:
            if "system" in self._spec["dev_overrides"]:
                dev_primary = self._spec["dev_overrides"]["system"].get("primary_repo")
                if dev_primary:
                    return dev_primary
        return base_primary

    @property
    def moniker(self) -> str:
        """Get a filesystem-safe version of the image name."""
        assert re.match(
            r"[a-zA-Z0-9\-_][a-zA-Z0-9\-_\.]{1,128}", self.image_name
        ), "Invalid characters in image_name,  onlow letters, numbers, dashes, underscores, and dots are allowed, and it must be 1-255 characters long.  No leading dots."
        return self.image_name.replace(" ", "-").lower()  # + "-" + self.kernel_name

    @property
    def spec_iteration(self) -> str:
        """Determine the spec iteration (dev or prod) based on the presence of dev_overrides and the config."""
        iteration = self._spec.get("dev_overrides", {}).get("repositories") or {}
        return "dev" if iteration else "prod"

    @property
    def valid_range(self) -> str:
        """Get a human-readable valid date range string based on the spec header."""
        if valid_on := self.header.get("valid_on"):
            valid_on = valid_on.isoformat()
        else:
            valid_on = "undef"
        if expires_on := self.header.get("expires_on"):
            expires_on = expires_on.isoformat()
        else:
            expires_on = "undef"
        return valid_on.replace("-", "") + "-" + expires_on.replace("-", "")

    @property
    def artifact_name(self) -> str:
        """Generate a name suitable for referring to an archived spec or image given additional descorators."""
        name_parts = [self.moniker, self.spec_iteration, self.valid_range]
        return "_".join(name_parts)

    @property
    def spec_name(self) -> str:
        """Generate a name (Notebook Spec) for the spec archive Docker export file."""
        return "nbs_" + self.artifact_name

    @property
    def spi_image_name(self) -> str:
        """Generate a name for the SPI Docker image built from this spec."""
        return "nbw_" + self.artifact_name

    @property
    def spec_file(self) -> Path:
        return self._source_file

    @property
    def shelf_name(self) -> str:
        return self.moniker  # + "-" + self.spec_id

    @property
    def archive_format(self) -> str:
        """Get the default archival format for the environment's binaries."""
        # Return default if not specified
        arch_format = self.system.get("archive_format")
        if arch_format:
            self.logger.debug("Using spec'ed archive format", arch_format)
        else:
            arch_format = DEFAULT_ARCHIVE_FORMAT
            self.logger.debug(
                "No archive format in spec, assuming default format", arch_format
            )
        return arch_format

    # ----------------- functional access to output section ----------------

    def get_output_data(self, key: str, default: Any = None) -> Any:
        """Get data from the output section of the spec."""
        return self._spec.get("out", {}).get(key, default)

    def get_outputs(self, *output_names) -> list[Any] | Any:
        """Get the named fields from the spec output section and
        return a tuple in order of `output_names`.
        """
        self.logger.debug("Retrieving prior outputs from spec:", output_names)
        if "out" not in self._spec:
            raise RuntimeError(
                f"No output section found.   Output values for {output_names} must already be in the spec."
            )
        output_values = []
        for output_name in output_names:
            output_value = self.get_output_data(output_name)
            if output_value is not None:
                output_values.append(output_value)
            else:
                raise RuntimeError(
                    f"Missing output field '{output_name}' needs to be computed earlier or already in the spec."
                )
        if len(output_values) > 1:
            return output_values
        elif len(output_values) == 1:
            return output_values[0]
        else:
            raise RuntimeError(f"No output values were found for '{output_names}'.")

    def outputs_exist(self, *output_names: str) -> bool:
        """Check if all specified outputs exist in the spec already."""
        return "out" in self._spec and all(
            name in self._spec["out"] for name in output_names
        )

    def files_exist(self, *filepaths: str | Path) -> bool:
        """Check if all specified files exist in the filesystem."""
        return all(Path(filepath).exists() for filepath in filepaths)

    # Raw read/write access for backward compatibility or special cases
    def to_dict(self) -> dict[str, Any]:
        """Return the raw spec dictionary."""
        return copy.deepcopy(self._spec)

    def to_string(self) -> str:
        output_str = utils.yaml_dumps(self._spec)
        if hasattr(self, "inline_mamba_spec") and self.inline_mamba_spec is not None:
            output_str += "\n---\n" + utils.yaml_dumps(self.inline_mamba_spec)
        return output_str

    # ----------------------------- load, save, outputs  ---------------------------

    @classmethod
    def load_and_validate(
        cls,
        spec_file: str,
    ) -> Optional["SpecManager"]:
        """Factory method to load and validate a spec file."""
        manager = cls()
        if manager.load_spec(spec_file) and manager.validate():
            # stash the unchecked initial checksum to check later
            # to ensure readonly workflows do not change it.
            # if the unchecked value starts out bad, that should
            # be detected or ignored before it is used.
            manager._initial_spec_sha256 = manager.sha256
            return manager
        else:
            manager.logger.error("Failed to load and validate", spec_file)
            return None

    def load_spec(self, spec_file: str | Path) -> bool:
        """Load YAML specification file. Handles multi-document YAML for inline mamba specs."""
        try:
            self._source_file = Path(spec_file)
            with self._source_file.open("r") as f:
                docs = list(utils.get_yaml().load_all(f))
            self._spec = docs[0]
            if len(docs) > 1:
                self.inline_mamba_spec = docs[1]
                self.logger.debug("Found inline mamba spec (second YAML document).")
            else:
                self.inline_mamba_spec = None
            self.logger.debug(f"Loaded spec from {str(spec_file)}.")
            return True
        except Exception as e:
            return self.logger.exception(e, f"Failed to load YAML spec: {e}")

    def set_output_data(self, key: str, value: Any) -> None:
        """set data in the output section."""
        if "out" not in self._spec:
            self._spec["out"] = dict()
        self._spec["out"][key] = value
        self.logger.debug(f"setting output data: {key} -> {value}")

    # -------------------------------- saving & resetting spec -------------------------------

    def output_spec(self, output_dir: Path | str) -> Path:
        """The output path for the spec file."""
        if self._source_file is None:
            raise RuntimeError("No source file loaded")
        return Path(output_dir) / self._source_file.name

    def save_spec(self, output_dir: Path | str, add_sha256: bool = False) -> bool:
        """Keeping the original name,  save the spec at a new location, optionally
        updating the sha256 sum.
        """
        output_filepath = self.output_spec(output_dir)
        return self.save_spec_as(output_filepath, add_sha256=add_sha256)

    def save_spec_as(
        self, output_filepath: Path | str, add_sha256: bool = False
    ) -> bool:
        """Save the current YAML spec to a file."""
        self.logger.debug(f"Saving spec file to {output_filepath}.")
        try:
            output_path = Path(output_filepath)
            self.refresh_date_updated()
            if add_sha256:
                hash = self.add_sha256()
                self.logger.debug(f"Setting spec_sha256 to {hash}.")
            else:
                self.system.pop("spec_sha256", None)
                self.logger.debug(
                    "Not updating spec_sha256 sum; Removing potentially outdated sum."
                )
            if output_path.exists():
                self.logger.debug(
                    f"Output file {output_filepath} already exists and will be removed and overwritten."
                )
                output_path.unlink()  # Remove existing file if it
            self.logger.debug(f"Writing spec to {output_filepath}.")
            with output_path.open("w+") as f:
                f.write(self.to_string())
            self.logger.debug(f"Spec file saved to {output_filepath}.")
            return True
        except Exception as e:
            return self.logger.exception(
                e, f"Error saving YAML spec file to {output_filepath}: {e}"
            )

    def revise_and_save(
        self,
        output_dir: Path | str,
        add_sha256: bool = False,
        **additional_outputs,
    ) -> bool:
        """Update spec with computed outputs and save to file."""
        try:
            self.logger.info(f"Revising spec file {self._source_file}.")
            for key, value in additional_outputs.items():
                self.set_output_data(key, value)
            return self.save_spec(output_dir, add_sha256=add_sha256)
        except Exception as e:
            return self.logger.exception(e, f"Error revising spec file: {e}")

    def reset_spec(self) -> bool:
        """Delete the output field of the spec and make sure the source file reflects it."""
        self.logger.debug("Resetting spec file.")
        out = self._spec.pop("out", None)
        if not out:
            return True
        data = out.pop("data", None)
        if data:
            self._spec["out"] = dict(data=data)
        self.system.pop("spec_sha256", None)
        if not self.validate():
            return self.logger.error("Spec did not validate follwing reset.")
        if not self.save_spec_as(self._source_file):
            return self.logger.error("Spec save to", self._source_file, "failed...")
        return True

    def data_reset_spec(self) -> bool:
        """Delete only the 'data' output field of the spec and make sure the source file reflects it."""
        self.logger.debug("Resetting data section spec file.")
        out = self._spec.get("out", None)
        if not out:
            return True
        out.pop("data", None)
        self.system.pop("spec_sha256", None)
        if not self.validate():
            return self.logger.error("Spec did not validate follwing data reset.")
        if not self.save_spec_as(self._source_file):
            return self.logger.error("Spec save to", self._source_file, "failed...")
        return True

    def finalize_dev_overrides(self) -> bool:
        """Remove the 'dev_overrides' section from the spec file."""
        if "dev_overrides" in self._spec:
            self.logger.info("Deactivating 'dev_overrides' section of spec.")
            overrides = self._spec.pop("dev_overrides")
            self._spec["deactivated_dev_overrides"] = overrides
            return self.save_spec_as(self._source_file, add_sha256=True)
        return self.logger.info("No 'dev_overrides' section found to remove.")

    # ---------------------------- hashes, crypto ----------------------------------

    def refresh_date_updated(self) -> None:
        """Update the date_updated field with the current time (adds it if missing)."""
        self.system["date_updated"] = datetime.datetime.now().isoformat()
        self.logger.debug(
            f"Updated system.date_updated to {self.system['date_updated']}."
        )

    @property
    def sha256(self) -> str | None:
        hash = self.system.get("spec_sha256", None)
        if hash is None:
            self.logger.debug("Spec has no_spec_sha256 hash for verifying integrity.")
            return None
        if len(hash) != 64 or not re.match("[a-z0-9]{64}", hash):
            self.logger.warning(f"System spec_sha256 hash '{hash}' is malformed.")
        return hash

    def add_sha256(self) -> str:
        self.system["spec_sha256"] = ""
        self.system["spec_sha256"] = utils.sha256_str(self.to_string())
        return self.system["spec_sha256"]

    def validate_sha256(self) -> bool:
        """Validate the sha256 hash of the spec which proves integrity unless we've been hacked."""
        expected_hash = self.system.get("spec_sha256")
        if not expected_hash:
            return self.logger.error("Spec has no spec_sha256 hash to validate.")
        self.logger.debug(f"Validating spec_sha256 checksum {expected_hash}.")
        actual_hash = self.add_sha256()
        if expected_hash == actual_hash:
            self.logger.debug(f"Spec-sha256 {expected_hash} validated.")
            return True
        else:
            self.logger.error(
                f"Spec-sha256 {expected_hash} did not match actual hash {actual_hash}."
            )
            return False

    # ---------------------------- validation ----------------------------------

    ALLOWED_KEYWORDS: dict[str, Any] = {
        "dev_overrides": {
            "repositories": ["url", "ref"],
            "refdata_dependencies": ["install_files", "other_variables"],
            "override_pip_versions": [],
            "system": {
                "spi": {
                    "repo": None,
                    "ref": None,
                },
                "nb-wrangler": {
                    "repo": None,
                    "ref": None,
                },
                "primary_repo": None,
                "date_updated": None,
            },
        },
        "deactivated_dev_overrides": {
            "repositories": ["url", "ref"],
            "refdata_dependencies": ["install_files", "other_variables"],
            "override_pip_versions": [],
            "system": {
                "spi": {
                    "repo": None,
                    "ref": None,
                },
                "nb-wrangler": {
                    "repo": None,
                    "ref": None,
                },
                "primary_repo": None,
                "date_updated": None,
            },
        },
        "image_spec_header": [
            "image_name",
            "description",
            "valid_on",
            "expires_on",
            "python_version",
            "deployment_name",
            "kernel_name",
            "display_name",
            "manager",
        ],
        "repositories": ["url", "ref"],
        "refdata_dependencies": ["install_files", "other_variables"],
        "environment_spec": ["uri", "repo", "path"],
        "extra_mamba_packages": [],
        "common_mamba_packages": [],
        "extra_pip_packages": [],
        "common_pip_packages": [],
        "override_pip_versions": [],
        "selected_notebooks": [
            "repo",
            "root_directory",
            "include_subdirs",
            "exclude_subdirs",
            "tests",
        ],
        "out": [
            "repositories",
            "test_notebooks",
            "spi_packages",
            "mamba_spec",
            "pip_requirement_files",
            "pip_map",
            "package_versions",
            "data",
        ],
        "system": {
            "spec_version": None,
            "spec_sha256": None,
            "archive_format": None,
            "spi": {
                "repo": None,
                "ref": None,
            },
            "nb-wrangler": {
                "repo": None,
                "ref": None,
            },
            "primary_repo": None,
            "date_updated": None,
        },
    }

    REQUIRED_KEYWORDS: dict[str, Any] = {
        "image_spec_header": [
            "image_name",
            "kernel_name",
            "deployment_name",
            "python_version",
            "valid_on",
            "expires_on",
        ],
        "repositories": [],
        "system": {
            "spec_version": None,
            "spi": ["repo"],
            "nb-wrangler": ["repo"],
            "date_updated": None,
        },
    }

    def validate(self) -> bool:
        """Perform comprehensive validation on the loaded specification."""
        self._is_validated = False
        if not self._spec:
            return self.logger.error("Spec did not loaded / defined, cannot validate.")
        validated = (
            self._validate_top_level_structure()
            and self._validate_environment_spec()  # New comprehensive validation
            and self._validate_repositories_section()
            and self._validate_refdata_dependencies_section()
            and self._validate_notebook_selections_section()
            and self._validate_system()
            and self._validate_spi_section()
            and self._validate_nb_wrangler_section()
        )
        if not validated:
            return self.logger.error("Spec validation failed.")
        self._is_validated = True
        self.logger.debug("Spec validated.")
        return True

    def _ensure_validated(self) -> None:
        """Ensure the spec has been validated before access."""
        if not self._is_validated:
            raise RuntimeError("Spec must be validated before accessing data")

    # Validation methods
    def _validate_top_level_structure(self) -> bool:
        """Validate top-level structure."""
        no_errors = True
        for field in self.REQUIRED_KEYWORDS:
            if field not in self._spec:
                no_errors = self.logger.error(f"Missing required field: {field}")

        for key in self._spec:
            if key not in self.ALLOWED_KEYWORDS:
                # The concatenated mamba spec can add top-level keys like 'name', 'channels', etc.
                # We allow these only if an inline spec is detected.
                if self.inline_mamba_spec is None:
                    no_errors = self.logger.error(f"Unknown top-level keyword: {key}")

        return no_errors

    def _validate_environment_spec(self) -> bool:
        """
        Validates the environment definition, enforcing one of four mutually exclusive methods.
        """
        no_errors = True

        # Check which environment definition method is used
        has_python_version = "python_version" in self.header
        has_inline_mamba_spec = self.inline_mamba_spec is not None
        has_environment_spec = self.environment_spec is not None

        # Count defined methods
        methods_defined = sum(
            [has_python_version, has_inline_mamba_spec, has_environment_spec]
        )

        # Validate exactly one method is used
        if methods_defined == 0:
            return self.logger.error(
                "No environment definition found. Specify `python_version`, an inline mamba spec, or an external `environment_spec`."
            )
        if methods_defined > 1:
            return self.logger.error(
                "Multiple environment definitions found. `python_version`, inline mamba spec, and `environment_spec` are mutually exclusive."
            )

        # Validate the specific method used
        if has_python_version:
            no_errors = self._validate_simple_definition() and no_errors
        elif has_inline_mamba_spec:
            no_errors = self._validate_inline_spec() and no_errors
        elif has_environment_spec:
            no_errors = self._validate_external_spec() and no_errors

        # Validate header fields
        no_errors = (
            self._validate_header_fields(
                has_python_version, has_inline_mamba_spec, has_environment_spec
            )
            and no_errors
        )

        return no_errors

    def _validate_simple_definition(self) -> bool:
        """Validate simple definition (python_version in header)."""
        no_errors = True
        if "kernel_name" not in self.header:
            no_errors = (
                self.logger.error(
                    "Missing `kernel_name` in `image_spec_header` for simple definition mode."
                )
                and no_errors
            )
        if "display_name" not in self.header:
            self.logger.warning(
                "Missing `display_name` in `image_spec_header`. It will default to `kernel_name`."
            )
        return no_errors

    def _validate_inline_spec(self) -> bool:
        """Validate inline mamba spec."""
        no_errors = True
        if "python_version" in self.header:
            no_errors = (
                self.logger.error(
                    "`python_version` must not be in the header when using an inline spec."
                )
                and no_errors
            )
        if "kernel_name" in self.header:
            no_errors = (
                self.logger.error(
                    "`kernel_name` must not be in the header when using an inline spec."
                )
                and no_errors
            )
        if (
            not isinstance(self.inline_mamba_spec, dict)
            or "name" not in self.inline_mamba_spec
        ):
            no_errors = (
                self.logger.error(
                    "The inline mamba spec (second YAML document) must be a dictionary and have a `name` field."
                )
                and no_errors
            )
        return no_errors

    def _validate_external_spec(self) -> bool:
        """Validate external environment spec."""
        no_errors = True
        if "python_version" in self.header:
            no_errors = (
                self.logger.error(
                    "`python_version` must not be in the header when using an external spec."
                )
                and no_errors
            )
        if "kernel_name" in self.header:
            no_errors = (
                self.logger.error(
                    "`kernel_name` must not be in the header when using an external spec."
                )
                and no_errors
            )
        if not isinstance(self.environment_spec, dict):
            no_errors = (
                self.logger.error("`environment_spec` must be a dictionary.")
                and no_errors
            )
        else:
            has_uri = "uri" in self.environment_spec
            has_repo = "repo" in self.environment_spec
            has_path = "path" in self.environment_spec

            if not (has_uri or (has_repo and has_path)):
                no_errors = (
                    self.logger.error(
                        "`environment_spec` must contain either a `uri` key or both `repo` and `path` keys."
                    )
                    and no_errors
                )
            if has_uri and (has_repo or has_path):
                no_errors = (
                    self.logger.error(
                        "In `environment_spec`, `uri` cannot be mixed with `repo` or `path`."
                    )
                    and no_errors
                )
            if has_repo and self.environment_spec["repo"] not in self.repositories:
                no_errors = (
                    self.logger.error(
                        f"Unknown repository '{self.environment_spec['repo']}' referenced in `environment_spec`."
                    )
                    and no_errors
                )
        return no_errors

    def _validate_header_fields(
        self, has_python_version, has_inline_mamba_spec, has_environment_spec
    ) -> bool:
        """Validate header fields based on which environment method is used."""
        no_errors = True
        for field in self.REQUIRED_KEYWORDS["image_spec_header"]:
            # Skip validation for fields that are optional when using other methods
            if field == "kernel_name" and (
                has_inline_mamba_spec or has_environment_spec
            ):
                continue
            if field == "python_version" and (
                has_inline_mamba_spec or has_environment_spec
            ):
                continue

            if field not in self.header:
                no_errors = (
                    self.logger.error(
                        f"Missing required field in image_spec_header: {field}"
                    )
                    and no_errors
                )

        for key in self.header:
            if key not in self.ALLOWED_KEYWORDS["image_spec_header"]:
                no_errors = (
                    self.logger.error(f"Unknown keyword in image_spec_header: {key}")
                    and no_errors
                )
        return no_errors

    def _validate_repositories_section(self) -> bool:
        """Validate repositories section."""
        no_errors = True
        if not self.repositories:
            self.logger.debug("No repositories specified.")
        for name, repo in self.repositories.items():
            for key in repo:
                if key not in self.ALLOWED_KEYWORDS["repositories"]:
                    no_errors = self.logger.error(
                        f"Unknown keyword '{key}' in repository '{name}'."
                    )
            if "url" not in repo:
                no_errors = self.logger.error(
                    f"Missing required 'url' field in repository '{name}'."
                )
        return no_errors

    def _validate_refdata_dependencies_section(self) -> bool:
        """Validate refdata_dependencies section."""
        if "refdata_dependencies" not in self._spec:
            return True

        from .data_manager import RefdataSpec

        try:
            RefdataSpec.from_dict("wrangler_spec", self._spec["refdata_dependencies"])
            return True
        except ValueError as e:
            return self.logger.error(f"Invalid 'refdata_dependencies' in spec: {e}")

    def _validate_notebook_selections_section(self) -> bool:
        """Validate selected_notebooks section."""
        no_errors = True
        if not self.notebook_selections:
            self.logger.debug("selected_notebooks is not specified.")
        for name, selection in self.notebook_selections.items():
            for key in selection:
                if key not in self.ALLOWED_KEYWORDS["selected_notebooks"]:
                    no_errors = self.logger.error(
                        f"Unknown keyword '{key}' in notebook selection '{name}'."
                    )
            if "repo" not in selection:
                no_errors = self.logger.error(
                    f"Missing required 'repo' field in notebook selection '{name}'."
                )
            elif selection["repo"] not in self.repositories:
                no_errors = self.logger.error(
                    f"Unknown repo '{selection['repo']}' in notebook selection '{name}'."
                )
            if "include_subdirs" not in selection:
                no_errors = self.logger.error(
                    f"Missing required 'include_subdirs' field in notebook selection '{name}'."
                )
        return no_errors

    def _validate_system(self) -> bool:
        no_errors = True
        if "spec_version" not in self.system:
            no_errors = self.logger.error(
                "Required field 'spec_version' of section 'system' is missing."
            )
        else:
            try:
                version = float(self.system["spec_version"])
                if version < int(WRANGLER_SPEC_VERSION):
                    self.logger.warning(
                        f"Spec version {version} is deprecated. Consider updating to {WRANGLER_SPEC_VERSION}."
                    )
            except (ValueError, TypeError):
                no_errors = self.logger.error("spec_version must be a float or number.")

        if "date_updated" not in self.system:
            self.logger.debug(
                "Field 'date_updated' is missing from section 'system'. It will be added automatically on the next spec update."
            )

        if self.archive_format not in VALID_ARCHIVE_FORMATS:
            self.logger.warning(
                f"Invalid .system.archive_format '{self.archive_format}'. Possibly unsupported if not one of: {VALID_ARCHIVE_FORMATS}"
            )
        for key in self.system:
            if key not in self.ALLOWED_KEYWORDS["system"]:
                no_errors = self.logger.error(
                    f"Undefined keyword '{key}' in section 'system'."
                )
        return no_errors

    def _validate_spi_section(self) -> bool:
        """Validate spi section."""
        no_errors = True
        if "spi" not in self._spec["system"]:
            return self.logger.error("Missing required section: spi")

        spi = self._spec["system"]["spi"]
        for key in spi:
            if key not in self.ALLOWED_KEYWORDS["system"]["spi"]:
                no_errors = self.logger.error(
                    f"Unknown keyword '{key}' in spi section."
                )
        for field in self.REQUIRED_KEYWORDS["system"]["spi"]:
            if field not in spi:
                no_errors = self.logger.error(
                    f"Missing required field in spi section: {field}"
                )
        return no_errors

    def _validate_nb_wrangler_section(self) -> bool:
        """Validate nb-wrangler section."""
        no_errors = True
        if "nb-wrangler" not in self._spec["system"]:
            return True

        nbw = self._spec["system"]["nb-wrangler"]
        for key in nbw:
            if key not in self.ALLOWED_KEYWORDS["system"]["nb-wrangler"]:
                no_errors = self.logger.error(
                    f"Unknown keyword '{key}' in nb-wrangler section."
                )
        for field in self.REQUIRED_KEYWORDS["system"]["nb-wrangler"]:
            if field not in nbw:
                no_errors = self.logger.error(
                    f"Missing required field in nb-wrangler section: {field}"
                )
        return no_errors

    # -------------------------------- notebook and repository collection --------------------------------------

    def get_repository_urls(self) -> list[str]:
        """Get all unique repository URLs from the spec."""
        self._ensure_validated()
        return [repo["url"] for repo in self.repositories.values()]

    def get_repository_refs(self) -> dict[str, str | None]:
        """Get repository URLs mapped to their refs from the spec."""
        self._ensure_validated()
        return {
            repo["url"]: repo.get("ref", "main") for repo in self.repositories.values()
        }

    def get_output_repository_refs(self) -> dict[str, str | None]:
        """Get repository URLs mapped to their refs from the spec output section."""
        self._ensure_validated()
        output_repos = self.get_output_data("repositories", {})
        return {
            repo_info.get("url"): repo_info.get("ref")
            for repo_info in output_repos.values()
            if repo_info
        }

    def collect_notebook_paths(self, repos_dir: Path) -> dict[str, str]:
        """Collect paths to all notebooks specified by the spec."""
        self._ensure_validated()
        notebook_paths: dict[str, str] = {}
        for name, selection in self.notebook_selections.items():
            repo_name = selection["repo"]
            if repo_name not in self.repositories:
                raise RuntimeError(
                    f"Unknown repository '{repo_name}' in selection block '{name}'"
                )
            repo_url = self.repositories[repo_name]["url"]
            clone_dir = self._get_repo_dir(repos_dir, repo_url)
            if not clone_dir.exists():
                self.logger.error(
                    f"Repository '{repo_name}' not set up at: {clone_dir}"
                )
                continue
            root_dir = selection.get("root_directory", "")
            found_notebooks = self._process_directory_entry(
                selection, clone_dir, root_dir
            )

            for notebook_path in found_notebooks:
                if notebook_path in notebook_paths:
                    self.logger.warning(
                        f"Notebook {notebook_path} included in multiple selections. Using first one found: '{notebook_paths[notebook_path]}'."
                    )
                else:
                    notebook_paths[notebook_path] = name

        if notebook_paths:
            self.logger.info(
                f"Found {len(notebook_paths)} notebooks in all notebook repositories."
            )
        else:
            self.logger.debug("No notebooks found in any selection.")
        return dict(sorted(notebook_paths.items()))

    def _get_repo_dir(self, repos_dir: Path, repo_url: str) -> Path:
        """Get the path to the repository directory."""
        basename = os.path.basename(repo_url).replace(".git", "")
        return repos_dir / basename

    def _process_directory_entry(
        self, entry: dict, repo_dir: Path, root_directory: str
    ) -> set[str]:
        """Process a directory entry from the spec file."""
        base_path = repo_dir
        if root_directory:
            base_path = base_path / root_directory

        possible_notebooks = [str(path) for path in base_path.glob("**/*.ipynb")]

        include_subdirs = list(entry.get("include_subdirs", [r"."]))
        included_notebooks = self._matching_files(
            "Including", possible_notebooks, include_subdirs
        )

        exclude_subdirs = list(entry.get("exclude_subdirs", []))
        exclude_subdirs.append(r"(^|/)\.ipynb_checkpoints(/|/.*-checkpoint\.ipynb$)")
        excluded_notebooks = self._matching_files(
            "Excluding", possible_notebooks, exclude_subdirs
        )

        remaining_notebooks = included_notebooks - excluded_notebooks
        self.logger.info(
            f"Selected {len(remaining_notebooks)} notebooks under {base_path} for selection block."
        )

        return remaining_notebooks

    def _matching_files(
        self, verb: str, possible_notebooks: list[str], regexes: list[str]
    ) -> set[str]:
        self.logger.debug(
            f"{verb} notebooks {list(possible_notebooks)} against regexes {regexes}"
        )
        notebooks = set()
        for nb_path in possible_notebooks:
            if not Path(nb_path).is_file():
                self.logger.debug(f"Skipping {verb} non-file: {nb_path}")
                continue
            for regex in regexes:
                if re.search(regex, str(nb_path)):
                    self.logger.debug(
                        f"{verb} notebook {nb_path} based on regex: '{regex}'"
                    )
                    notebooks.add(str(nb_path))
                    break
        return notebooks
