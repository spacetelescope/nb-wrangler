"""Main NotebookWrangler class orchestrating the curation process."""

import os
from pathlib import Path
from typing import Any, Optional
from collections.abc import Callable
import copy

from .constants import NBW_URI, LOG_FILE
from .config import WranglerConfigurable
from .logger import WranglerLoggable
from .spec_manager import SpecManager
from .repository import RepositoryManager
from .nb_processor import NotebookImportProcessor
from .environment import WranglerEnvable
from .compiler import RequirementsCompiler
from .notebook_tester import NotebookTester
from .injector import get_injector
from .data_manager import RefdataValidator
from .pantry import NbwPantry
from . import utils


class NotebookWrangler(WranglerConfigurable, WranglerLoggable, WranglerEnvable):
    """Main wrangler class for processing notebooks."""

    def __init__(self):
        super().__init__()
        self.logger.info("Loading and validating spec", self.config.spec_file)
        self.spec_manager = SpecManager.load_and_validate(self.config.spec_file)
        if self.spec_manager is None:
            raise RuntimeError("SpecManager is not initialized.  Cannot continue.")
        self.pantry = NbwPantry()
        self.pantry_shelf = self.pantry.get_shelf(self.spec_manager.shelf_name)
        if self.config.repos_dir == NBW_URI:
            self.config.repos_dir = self.pantry_shelf.notebook_repos_path
        else:
            self.config.repos_dir = Path(self.config.repos_dir)
        self.repo_manager = RepositoryManager(self.config.repos_dir)
        self.notebook_import_processor = NotebookImportProcessor()
        self.tester = NotebookTester(self.spec_manager)
        self.compiler = RequirementsCompiler(
            spec_manager=self.spec_manager, repo_manager=self.repo_manager
        )
        self.injector = get_injector(self.repo_manager, self.spec_manager)
        # Store compiled artifacts
        self.compiled_kernel_name: str | None = None
        # Create output directories
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.repos_dir.mkdir(parents=True, exist_ok=True)

    @property
    def resolved_kname(self) -> str | None:
        """
        Gets the definitive kernel name from the most reliable source available.

        The kernel name can come from three places, in order of priority:
        1. self.compiled_kernel_name: Set after the compile step. The most accurate.
        2. spec output: For pre-compiled specs (`--reinstall` workflow).
        3. self.env_name: From the initial spec load (for simple mode or early steps).
        """
        return (
            self.compiled_kernel_name
            or self.spec_manager.get_output_data("kernel_name")
            or self.env_name
        )

    @property
    def deployment_name(self):
        """Nominally the branch of science-platform-images this build will target."""
        return self.spec_manager.deployment_name if self.spec_manager else None

    @property
    def env_name(self):
        """Strictly speaking,  kernel name,  but nominally also environment name.
        The worst/only exception I know of is "base" environment == "python3" kernel.
        """
        return self.spec_manager.kernel_name if self.spec_manager else None

    @property
    def kernel_display_name(self) -> str:
        """More readable version of kernel name visible in JupyterLab menu."""
        return self.spec_manager.display_name if self.spec_manager else self.env_name

    @property
    def pip_packages(self) -> list[str]:
        """Use compiled packages if available, otherwise from spec output."""
        return (
            self.spec_manager.get_output_data("pip_compiler_output").splitlines() or []
        )

    @property
    def mamba_spec_file(self):
        return self.config.output_dir / f"{self.spec_manager.moniker}-mamba.yml"

    @property
    def pip_output_file(self):
        return self.config.output_dir / f"{self.spec_manager.moniker}-pip.txt"

    @property
    def extra_pip_output_file(self):
        return self.config.output_dir / f"{self.spec_manager.moniker}-extra-pip.txt"

    @property
    def shelf_name(self) -> str:
        return self.spec_manager.shelf_name

    @property
    def archive_format(self):
        """Combines default + optional spec value + optional cli override into final format."""
        if self.config.env_archive_format:
            self.logger.warning(
                "Overriding spec'ed and/or default archive file format to",
                self.config.env_archive_format,
                "nominally to experiment, may not automatically unpack correctly.",
            )
            return self.config.env_archive_format
        else:
            return self.spec_manager.archive_format

    def main(self) -> bool:
        """Main processing method."""
        self.logger.debug(f"Starting wrangler configuration: {self.config}")
        try:
            return self._main_uncaught_core()
        except Exception as e:
            return self.logger.exception(e, f"Error during curation: {e}")

    def _main_uncaught_core(self) -> bool:
        """Execute the complete curation workflow based on configured workflow type."""
        if not self._setup_environment():
            return self.logger.error(
                "Failed to set up internal Python environment from spec."
            )

        self._apply_dev_mode_defaults()  # New call here

        if self.config.workflows:
            self.logger.info(f"Running workflows {self.config.workflows}.")

        # Define workflow mappings
        workflow_map = {
            "curation": self._run_development_workflow,
            "submit_for_build": self._run_submit_build_workflow,
            "inject_spi": self._inject_spi_workflow,
            "reinstall": self._run_reinstall_spec_workflow,
            "data_curation": self._run_data_curation_workflow,
            "data_reinstall": self._run_data_reinstall_workflow,
            "reset_curation": self._run_reset_curation,
        }
        for workflow in self.config.workflows:
            if workflow not in workflow_map:
                return self.logger.error(f"Undefined workflow {workflow}.")
            elif not workflow_map[workflow]():
                return self.logger.error(f"Workflow {workflow} failed.  Exiting...")

        # Return True only if all workflows AND explicit steps succeeded
        return self._run_explicit_steps()

    def _apply_dev_mode_defaults(self):
        """
        Applies implicit --dev settings based on the active workflow.
        Explicit --dev/--no-dev flags will always override these defaults.
        """
        # Determine if dev_overrides exist in the spec
        dev_overrides_exist = self.spec_manager.dev_overrides_exist()

        # Get the explicit --dev setting from CLI
        explicit_dev_cli = (
            self.config.dev
        )  # 'dev' is True if --dev was provided, False otherwise

        if (
            "curation" in self.config.workflows
            or "data_curation" in self.config.workflows
        ):
            if not explicit_dev_cli:  # If --dev was not explicitly set to True
                if dev_overrides_exist:
                    self.config.dev = True
                    self.logger.info(
                        "Implicitly activating --dev for curation workflow as dev_overrides exist."
                    )
                else:
                    self.config.dev = False  # Default behavior if no overrides exist
                    self.logger.warning(
                        "No dev_overrides found. Curation will proceed without development overrides."
                    )

        elif (
            "reinstall" in self.config.workflows
            or "data_reinstall" in self.config.workflows
        ):
            if not explicit_dev_cli:  # If --dev was not explicitly set to True
                self.config.dev = (
                    False  # Implicitly deactivate --dev for reinstall workflows
                )
            else:  # --dev was explicitly set by CLI
                if not dev_overrides_exist:
                    self.logger.error(
                        "Explicit --dev used for reinstall workflow but no dev_overrides found in spec. This may lead to unexpected behavior."
                    )
        else:
            # For other workflows or isolated steps, default --dev to False unless explicitly set.
            if not explicit_dev_cli:
                self.config.dev = False

    def _finalize_dev_overrides(self) -> bool:
        """Remove the 'dev_overrides' section from the spec file."""
        return self.spec_manager.remove_dev_overrides()

    def run_workflow(self, name: str, steps: list) -> bool:
        self.logger.info("Running", name, "workflow")
        for step in steps:
            self.logger.info(f"Step {step.__name__} of Workflow {name}.")
            if not step():
                return self.logger.error(
                    f"FAILED Workflow {name} Step {step.__name__}."
                )
        return self.logger.info("Workflow", name, "completed.")

    def _run_development_workflow(self) -> bool:
        """Execute steps for spec/notebook development workflow."""
        return self.run_workflow(
            "--curate",
            [
                self._prepare_all_repositories,
                self._compile_requirements,
                self._initialize_environment,
                self._install_packages,
                self._save_final_spec,
            ],
        )

    def _run_data_curation_workflow(self) -> bool:
        """Execute steps for data curation workflow, defining spec for data."""
        return self.run_workflow(
            "--data-curate",
            [
                self._prepare_all_repositories,
                self._spec_add,
                self._data_collect,
                self._data_download,
                self._data_update,
                self._data_validate,
                self._data_unpack,
                self._save_final_spec,
            ],
        )

    def _run_submit_build_workflow(self) -> bool:
        """Execute steps for the build submission workflow."""
        return self.run_workflow(
            "--submit-for-build",
            [
                self._validate_spec,
                self._prepare_all_repositories,
                self._submit_for_build,
            ],
        )

    def _inject_spi_workflow(self) -> bool:
        """Execute steps for the build submission workflow."""
        if not self.run_workflow(
            "--inject-spi",
            [
                self._validate_spec,
                self._prepare_all_repositories,
                self._inject_spi,
            ],
        ):
            return False
        requires_branch_name = (
            self.config.spi_prune
            or self.config.spi_build
            or self.config.spi_commit_message
            or self.config.spi_push
            or self.config.spi_pr
        )
        if requires_branch_name:
            if not self._spi_cm_and_optional_build():
                return False
            return self._spi_commit_push_pr()
        else:  # No followon steps, limited worflow successful.
            return True

    def _spi_cm_and_optional_build(self) -> bool:
        if not self.config.spi_branch:
            self.config.spi_branch = self.injector.spi_injection_branch_name
        if not self.injector.branch(self.config.spi_branch):
            return False
        if not self.injector.add_injected_files():
            return False
        if self.config.spi_prune and not self.injector.prune():
            return False
        if self.config.spi_build and not self.injector.build():
            return False
        return True

    def _spi_commit_push_pr(self) -> bool:
        """Optionally commit, push, and PR the injected SPI changes."""
        commit_message = self.config.spi_commit_message
        if not commit_message:
            commit_message = f"nb-wrangler: Automated SPI injection for spec {self.spec_manager.spec_file.name}"
        if not self.injector.commit(commit_message):
            return False
        if self.config.spi_push:
            if not self.injector.push(self.config.spi_branch):
                return False
        else:
            return self.logger.info(
                "Skipping SPI push and PR as per configuration.  Branch changes are local only."
            )
        if self.config.spi_pr and not self.injector.create_pr(
            self.config.spi_branch, commit_message
        ):
            return False
        return True

    def _run_reinstall_spec_workflow(self) -> bool:
        """Execute steps for environment recreation from spec workflow."""
        required_outputs = (
            "mamba_spec",
            "pip_compiler_output",
        )
        assert self.spec_manager is not None  # guaranteed by __init__
        if not self.spec_manager.outputs_exist(*required_outputs):
            return self.logger.error(
                "This workflow requires a precompiled spec with outputs",
                required_outputs,
            )
        return self.run_workflow(
            "--reinstall",
            [
                self._prepare_all_repositories_locked,
                self._validate_spec,
                self._spec_add,
                self._initialize_environment,
                self._install_packages,
            ],
        )

    def _run_data_reinstall_workflow(self) -> bool:
        """Execute steps for data curation workflow, defining spec for data."""
        return self.run_workflow(
            "--data-reinstall",
            [
                self._validate_spec,
                self._spec_add,
                self._data_download,
                self._data_validate,
                self._data_unpack,
            ],
        )

    def _run_reset_curation(self) -> bool:
        return self.run_workflow(
            "--data-reset-curation",
            [
                self._delete_environment,
                # self._env_compact,
                self._reset_spec,
                self._save_final_spec,
                self._reset_log,
            ],
        )

    def _run_explicit_steps(self) -> bool:
        """Execute steps for spec/notebook development workflow."""
        flags_and_steps: list[tuple[bool, Callable]] = [
            (self.config.clone_repos, self._prepare_all_repositories),
            (self.config.packages_compile, self._compile_requirements),
            (self.config.env_init, self._initialize_environment),
            (self.config.packages_install, self._install_packages),
            (self.config.test_all or self.config.test_imports, self._test_imports),
            (self.config.test_all or self.config.test_notebooks, self._test_notebooks),
            (self.config.spec_update_hash, self._update_spec_sha256),
            (self.config.spec_validate, self._validate_spec),
            (self.config.env_pack, self._pack_environment),
            (self.config.env_unpack, self._unpack_environment),
            (self.config.env_register, self._register_environment),
            (self.config.env_unregister, self._unregister_environment),
            (self.config.env_print_name, self._env_print_name),
            (self.config.spec_add, self._spec_add),
            (self.config.spec_list, self._spec_list),
            (self.config.finalize_dev_overrides, self._finalize_dev_overrides),
            (self.config.data_collect, self._data_collect),
            (self.config.data_list, self._data_list),
            (self.config.data_download, self._data_download),
            (self.config.data_delete, self._data_delete),
            (self.config.data_update, self._data_update),
            (self.config.data_validate, self._data_validate),
            (self.config.data_unpack, self._data_unpack),
            (self.config.data_pack, self._data_pack),
            (self.config.data_print_exports, self._data_print_exports),
            (self.config.data_symlinks, self._data_symlink_install_data),
            (self.config.delete_repos, self._delete_repos),
            (self.config.packages_uninstall, self._uninstall_packages),
            (self.config.env_delete, self._delete_environment),
            (self.config.env_kernel_cleanup, self._cleanup_kernels),
            (self.config.env_compact, self._env_compact),
            (self.config.spec_reset, self._reset_spec),
            (self.config.data_reset_spec, self._data_reset_spec),
            (self.config.reset_log, self._reset_log),
        ]
        if any(item[0] for item in flags_and_steps):
            self.logger.info("Running any explicitly selected steps.")
        for flag, step in flags_and_steps:
            if flag:
                self.logger.info("Explicit Step", step.__name__)
                if not step():
                    self.logger.error("FAILED Step", step.__name__, "... stopping...")
                    return False
        return True

    def _cleanup_kernels(self) -> bool:
        """Clean up dead kernels from the user's Jupyter registry."""
        return self.env_manager.cleanup_dead_kernels()

    def _reset_log(self):
        """Reset the log file."""
        self.logger.info(
            f"Resetting / deleting log file.  No {LOG_FILE} will be created for this wrangler run."
        )
        return self.logger._close_and_remove_logfile()

    def _prepare_all_repositories(self, floating_mode=True) -> bool:
        """
        Prepares all repositories (SPI and notebook repos) by cloning,
        updating, and cleaning them according to the spec and CLI flags.
        """
        self.logger.info("Preparing all repositories.")

        # Collect repositories to prepare
        all_repos_to_prepare = self._collect_repositories_to_prepare(floating_mode)

        # Prepare each repository and get resolved states
        try:
            resolved_repo_states = self.repo_manager.prepare_repositories(
                all_repos_to_prepare, floating_mode
            )
        except RuntimeError as e:
            return self.logger.error(f"Failed to prepare repositories: {e}")

        # Collect notebook paths and imports
        notebook_paths = self.spec_manager.collect_notebook_paths(self.config.repos_dir)
        test_imports, nb_to_imports = self.notebook_import_processor.extract_imports(
            list(notebook_paths.keys())
        )

        # Update spec with resolved repository states
        output_repos_for_spec = self.spec_manager.to_dict().get("repositories", {})
        self._update_spec_with_repo_states(output_repos_for_spec, resolved_repo_states)

        # Update SPI ref with resolved hash
        spi_output = copy.deepcopy(self.spec_manager.spi)
        spi_url = spi_output.get("repo")
        if spi_url and spi_url in resolved_repo_states:
            spi_output["ref"] = resolved_repo_states[spi_url]

        # Save updated spec
        return self.spec_manager.revise_and_save(
            self.config.output_dir,
            add_sha256=not self.config.spec_ignore_hash,
            repositories=copy.deepcopy(output_repos_for_spec),
            spi=spi_output,
            test_notebooks=notebook_paths,
            test_imports=test_imports,
            nb_to_imports=nb_to_imports,
        )

    def _collect_repositories_to_prepare(self, floating_mode=True):
        """Collect all repositories that need to be prepared."""
        all_repos_to_prepare = {}

        # Add SPI repo if applicable
        if not (
            self.config.packages_omit_spi
            and not self.config.inject_spi
            and not self.config.submit_for_build
        ):
            if floating_mode:
                spi_info = self.spec_manager.spi
            else:  # locked mode
                spi_info = self.spec_manager.get_output_data(
                    "spi", self.spec_manager.spi
                )
            spi_url = spi_info.get("repo")
            spi_ref = spi_info.get("ref")
            if spi_url:
                all_repos_to_prepare[spi_url] = spi_ref or "main"

        # Add notebook repos
        notebook_repo_urls = self.spec_manager.get_repository_urls()
        if floating_mode:
            notebook_repo_refs = self.spec_manager.get_repository_refs()
        else:  # Locked mode
            notebook_repo_refs = self.spec_manager.get_output_repository_refs()
            if not notebook_repo_refs:
                self.logger.warning(
                    "Locked mode is on, but no refs found in spec output for notebook repos. Falling back to input spec refs."
                )
                notebook_repo_refs = self.spec_manager.get_repository_refs()

        for url in notebook_repo_urls:
            all_repos_to_prepare[url] = notebook_repo_refs.get(url, "main")

        return all_repos_to_prepare

    def _update_spec_with_repo_states(
        self, output_repos_for_spec, resolved_repo_states
    ):
        """Update the spec with resolved repository states."""
        for name, repo_data in output_repos_for_spec.items():
            if repo_data["url"] in resolved_repo_states:
                repo_data["ref"] = resolved_repo_states[repo_data["url"]]
            repo_data.pop("branch", None)
            repo_data.pop("hash", None)

    def _prepare_all_repositories_locked(self) -> bool:
        return self._prepare_all_repositories(floating_mode=False)

    def _spec_add(self) -> bool:
        """Add a new spec to the pantry."""
        self.pantry_shelf.set_wrangler_spec(self.config.spec_file)
        return True

    def _spec_list(self) -> bool:
        """List the available shelves/specs in the pantry."""
        self.logger.info("Listing available shelves/specs in pantry.")
        return self.pantry.list_shelves()

    def _data_collect(self) -> bool:
        """Collect data from notebook repos."""
        self.logger.info("Collecing data information from notebook repo data specs.")
        output_repos = self.spec_manager.get_output_data("repositories")
        repo_urls = [repo["url"] for repo in output_repos.values()]
        data_validator = RefdataValidator.from_repo_urls(
            self.config.repos_dir, repo_urls
        )

        spec_exports = data_validator.get_spec_exports()
        self.pantry_shelf.save_exports_file("nbw-spec-exports.sh", spec_exports)
        pantry_exports = data_validator.get_pantry_exports(
            self.pantry_shelf.abstract_data_path
        )
        self.pantry_shelf.save_exports_file("nbw-pantry-exports.sh", pantry_exports)

        if not self._register_environment():
            self.logger.warning(
                "Failed registering environment.  Env vars in JupyterLab may note be set."
            )

        return self.spec_manager.revise_and_save(
            Path(self.config.spec_file).parent,
            data=dict(
                spec_inputs=data_validator.todict(),
                spec_exports=spec_exports,
                pantry_exports=pantry_exports,
            ),
        )

    def _data_get_exports(self) -> Optional[str]:
        """Print out the data environment variables on stdout according to the selected data
        storage mode.  Since this can get called before data has ever been collected, let it
        succeed normally even if no env vars are defined in the spec yet.
        """
        data = self.spec_manager.get_output_data("data")
        if data is None:
            self.logger.warning(
                "No 'data' section in spec for defining environment variables."
            )
            return ""
        mode = self.config.data_env_vars_mode
        exports = data.get(mode + "_exports")
        exports_str = ""
        if exports is None:
            self.logger.debug(
                "Data environment for mode '{mode}' is not defined yet.  No environment variables to list."
            )
        else:
            for var, value in exports.items():
                exports_str += f'export {var}="{value}"\n'
        return exports_str

    def _data_print_exports(self) -> bool:
        """Print out the data environment variables on stdout according to the selected data
        storage mode.  Since this can get called before data has ever been collected, let it
        succeed normally even if no env vars are defined in the spec yet.
        """
        print(self._data_get_exports())
        return True

    def _get_data_url_tuples(
        self,
    ) -> tuple[dict[str, Any], list[tuple[str, str, str, str, str]]]:
        data = self.spec_manager.get_output_data("data")
        spec_inputs = data["spec_inputs"]
        data_validator = RefdataValidator.from_dict(spec_inputs)
        urls = data_validator.get_data_urls(self.config.data_select)
        return data, urls

    def _data_list(self) -> bool:
        self.logger.info("Listing selected data archives.")
        _data, urls = self._get_data_url_tuples()
        for url in urls[:-1]:
            print(url)
        return True

    def _data_download(self) -> bool:
        self.logger.info("Downloading selected data archives.")
        _data, urls = self._get_data_url_tuples()
        if not self.pantry_shelf.download_all_data(urls):
            return self.logger.error("One or more data archive downloads failed.")
        return self.logger.info("Selected data downloaded successfully.")

    def _data_delete(self) -> bool:
        self.logger.info(
            f"Deleting selected data files of types {self.config.data_delete}."
        )
        _data, urls = self._get_data_url_tuples()
        if not self.pantry_shelf.delete_archives(self.config.data_delete, urls):
            return self.logger.error("One or more data archive deletes failed.")
        return self.logger.info(
            f"All selected data files of types {self.config.data_delete} removed successfully."
        )

    def _data_update(self) -> bool:
        if self.config.data_no_validation:
            return self.logger.info(
                "Skipping data validation due to --data-no-validation."
            )
        self.logger.info("Collecting metadata for downloaded data archives.")
        data, urls = self._get_data_url_tuples()
        self.logger.debug(f"Collecting metadata for {urls}.")
        data["metadata"] = self.pantry_shelf.collect_all_metadata(urls)
        return self.spec_manager.revise_and_save(
            Path(self.config.spec_file).parent,
            data=data,
        )

    def _data_validate(self) -> bool:
        if self.config.data_no_validation:
            return self.logger.info(
                "Skipping data validation due to --data-no-validation."
            )
        self.logger.info("Validating all downloaded data archives.")
        data, urls = self._get_data_url_tuples()
        metadata = data.get("metadata")
        if metadata is not None:
            if not self.pantry_shelf.validate_all_data(urls, metadata):
                return self.logger.error("Some data archives did not validate.")
            else:
                return self.logger.info("All data archives validated.")
        else:
            return self.logger.error(
                "Before it can be validated, data metadata must be updated."
            )

    def _data_unpack(self) -> bool:
        self.logger.info("Unpacking downloaded data archives to live locations.")
        if not self.config.data_no_symlinks:
            self._data_symlink_install_data()
        data, archive_tuples = self._get_data_url_tuples()
        for archive_tuple in archive_tuples:
            self.logger.debug(f"Unpacking data: {archive_tuple}")
            src_archive = self.pantry_shelf.archive_filepath(archive_tuple)
            if self.config.data_env_vars_mode == "pantry":
                dest_path = self.pantry_shelf.data_path
            else:
                resolved = utils.resolve_vars(archive_tuple[4], dict(os.environ))
                dest_path = Path(resolved)
            final_path = dest_path / archive_tuple[3]
            if final_path.exists() and self.config.data_no_unpack_existing:
                self.logger.info(
                    f"Skipping unpack for existing directory {final_path}."
                )
                continue
            if not self.pantry_shelf.unarchive(src_archive, dest_path, ""):
                return self.logger.error(
                    f"Failed unpacking '{src_archive}' to '{dest_path}'."
                )
        if not self.pantry_shelf.save_exports_file(
            "nbw-spec-exports.sh", data["spec_exports"]
        ):
            return self.logger.error("Failed exporting nbw-spec-exports.sh")
        if not self.pantry_shelf.save_exports_file(
            "nbw-pantry-exports.sh", data["pantry_exports"]
        ):
            return self.logger.error("Failed exporting nbw-spec-exports.sh")
        if not self._register_environment():
            self.logger.warning(
                "Failed registering environment.  Env vars in JupyterLab may note be set."
            )
        return True

    def _data_symlink_install_data(self) -> bool:
        """Create symlinks from install_data locations to the pantry data directory."""
        _data, archive_tuples = self._get_data_url_tuples()
        self.pantry_shelf.symlink_install_data(archive_tuples)
        return True

    def _data_pack(self) -> bool:
        self.logger.info("Packing downloaded data archives from live locations.")
        no_errors = True
        for archive_tuple in self._get_data_url_tuples()[1]:
            dest_archive = self.pantry_shelf.archive_filepath(archive_tuple)
            src_path = self.pantry_shelf.data_path
            no_errors = (
                self.pantry_shelf.archive(dest_archive, src_path, "") and no_errors
            )
        return no_errors

    def _delete_repos(self) -> bool:
        """Delete notebook and SPI repo clones."""
        output_repos = self.spec_manager.get_output_data("repositories", {})
        urls = [repo["url"] for repo in output_repos.values()]
        if spi_info := self.spec_manager.get_output_data("spi"):
            if spi_url := spi_info.get("repo"):
                urls.append(spi_url)
        return self.repo_manager.delete_repos(urls)

    def _compile_requirements(self) -> bool:
        """
        Compiles the full environment, stores artifacts, and saves them to the spec.
        """
        self.logger.info("Compiling full environment definition.")
        notebook_paths_dict = self.spec_manager.get_outputs("test_notebooks") or {}

        # The compiler now handles all logic for the 4 methods
        (
            self.compiled_kernel_name,
            final_mamba_spec_dict,
            mamba_package_map,
            non_mamba_pip_pkg_files,
        ) = self.compiler.consolidate_environment(
            list(notebook_paths_dict.keys()), self.injector, self.config.output_dir
        )

        compiled_mamba_spec_str = utils.yaml_block(
            utils.yaml_dumps(final_mamba_spec_dict)
        )

        # Save artifacts to the spec's output section
        if not self.spec_manager.revise_and_save(
            self.config.output_dir,
            add_sha256=not self.config.spec_ignore_hash,
            kernel_name=self.resolved_kname,
            mamba_spec=compiled_mamba_spec_str,
            mamba_package_map=mamba_package_map,
            non_mamba_pip_package_files=non_mamba_pip_pkg_files,
        ):
            return False

        if not self.compiler.compile_requirements(
            non_mamba_pip_pkg_files,
            self.config.spec_add_pip_hashes,
            self.pip_output_file,
        ):
            return self.logger.error("Failed to compile pip package versions.")
        try:
            Path("extra_pip_packages.txt").unlink()
        except FileNotFoundError:
            pass

        compiled_pip_packages_str = utils.yaml_block(self.pip_output_file.open().read())

        # Save artifacts to the spec's output section
        return self.spec_manager.revise_and_save(
            self.config.output_dir,
            add_sha256=not self.config.spec_ignore_hash,
            pip_compiler_output=compiled_pip_packages_str,
        )

    def _initialize_environment(self) -> bool:
        """Unconditionally initialize the target environment."""
        compiled_mamba_spec_str = self.spec_manager.get_output_data("mamba_spec", {})

        if not self.resolved_kname or not compiled_mamba_spec_str:
            return self.logger.error(
                "No compiled kernel name or mamba spec found. Run --packages-compile first."
            )

        if self.env_manager.environment_exists(self.resolved_kname):
            return self.logger.info(
                f"Environment {self.resolved_kname} already exists, skipping re-install. Use --env-delete to remove."
            )

        # Write the compiled mamba spec to a temporary file
        temp_mamba_spec_file = (
            self.config.output_dir / f"{self.resolved_kname}-mamba.yml"
        )
        with open(temp_mamba_spec_file, "w") as f:
            f.write(compiled_mamba_spec_str)

        if not self.env_manager.create_environment(
            self.resolved_kname, temp_mamba_spec_file
        ):
            return False
        if not self._register_environment():
            return False
        return self._copy_spec_to_env()

    def _install_packages(self) -> bool:
        """Unconditionally install packages and test imports."""
        if not self.resolved_kname:
            return self.logger.error(
                "No compiled kernel name found. Run --packages-compile first."
            )

        if self.pip_packages:
            if not self.env_manager.install_packages(
                self.resolved_kname,
                self.pip_packages,
            ):
                return False
        else:
            self.logger.warning("Found no pip requirements to install.")
        return self._copy_spec_to_env()

    def _uninstall_packages(self) -> bool:
        """Unconditionally uninstall pip packages from target environment."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to uninstall from.")
        return self.env_manager.uninstall_packages(
            self.resolved_kname, self.pip_packages
        )

    def _copy_spec_to_env(self) -> bool:
        self.logger.debug("Copying spec to target environment.")
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to copy spec to.")
        return self.spec_manager.save_spec(
            self.env_manager.env_live_path(self.resolved_kname),
            add_sha256=not self.config.spec_ignore_hash,
        )

    def _save_final_spec(self) -> bool:
        """Overwrite the original spec with the updated spec."""
        self.logger.debug("Updating spec with final results.")
        no_errors = self.spec_manager.save_spec(
            Path(self.config.spec_file).parent,
            add_sha256=not self.config.spec_ignore_hash,
        )
        if self.pantry_shelf.spec_path.exists():
            if not self.spec_manager.save_spec_as(
                self.pantry_shelf.spec_path, add_sha256=not self.config.spec_ignore_hash
            ):
                self.logger.warning("Failed to save spec to pantry shelf.")
        return no_errors

    def _update_spec_sha256(self) -> bool:
        return self.spec_manager.save_spec(
            Path(self.config.spec_file).parent, add_sha256=True
        )

    def _validate_spec_sha256(self) -> bool:
        if self.config.spec_ignore_hash:
            return self.logger.warning(
                "Ignoring spec_sha256 checksum validation. Spec integrity unknown."
            )
        else:
            return self.spec_manager.validate_sha256()

    def _validate_spec(self) -> bool:
        if not self.spec_manager.validate():
            return False
        return self._validate_spec_sha256()

    def _test_imports(self) -> bool:
        """Unconditionally run import checks if test_imports are defined."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to test imports on.")

        if nb_to_imports := self.spec_manager.get_outputs("nb_to_imports"):
            return self.env_manager.test_nb_imports(self.resolved_kname, nb_to_imports)
        else:
            return self.logger.warning("Found no imports to check in spec'd notebooks.")

    def _test_notebooks(self) -> bool:
        """Unconditionally test notebooks matching the configured pattern."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to test notebooks on.")
        notebook_configs = self.spec_manager.get_outputs("test_notebooks")
        if filtered_notebook_configs := self.tester.filter_notebooks(
            notebook_configs,
            self.config.test_notebooks or self.config.test_all or "",
            self.config.test_notebooks_exclude,
        ):
            return self.tester.test_notebooks(
                self.resolved_kname, filtered_notebook_configs
            )
        else:
            return self.logger.warning(
                "Found no notebooks to test matching inclusion patterns but not exclusion patterns."
            )

    def _reset_spec(self) -> bool:
        return self.spec_manager.reset_spec()

    def _data_reset_spec(self) -> bool:
        return self.spec_manager.data_reset_spec()

    def _unpack_environment(self) -> bool:
        """Unpack a pre-built environment from the pantry."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name defined in spec to unpack.")

        if self.pantry_shelf.unpack_environment(
            self.resolved_kname, self.spec_manager.moniker, self.archive_format
        ):
            return self._register_environment()
        return False

    def _pack_environment(self) -> bool:
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to pack.")
        return self.pantry_shelf.pack_environment(
            self.resolved_kname, self.spec_manager.moniker, self.archive_format
        )

    def _delete_environment(self) -> bool:
        """Unregister its kernel and delete the test environment."""
        if not self.resolved_kname:
            return self.logger.warning("No kernel name found to delete. Skipping.")

        if not self.env_manager.unregister_environment(self.resolved_kname):
            self.logger.warning(
                f"Failed to unregister environment {self.resolved_kname}. This can be normal if it was never registered."
            )
        if not self.env_manager.delete_environment(self.resolved_kname):
            self.logger.warning(
                f"Failed to delete environment {self.resolved_kname}. This can be normal if it never existed."
            )
        return True

    def _env_compact(self) -> bool:
        return self.env_manager.compact()

    def _env_print_name(self) -> bool:
        if self.resolved_kname:
            print(self.resolved_kname)
            return True
        return self.logger.error("Could not determine kernel name.")

    def _get_environment(self) -> dict:
        data = self.spec_manager.get_output_data("data")
        if data is not None and not self.config.data_env_vars_no_auto_add:
            env_vars = data.get(self.config.data_env_vars_mode + "_exports", {})
            return env_vars
        else:
            return {}

    def _setup_environment(self) -> bool:
        env_vars = self._get_environment()
        env_vars = utils.resolve_env(env_vars)
        for key, value in env_vars.items():
            os.environ[key] = value
            self.logger.debug(
                f"Setting environment '{key}' = '{value}' for wrangler and and notebooks."
            )
        return True

    def _register_environment(self) -> bool:  # post-start-hook / user support
        """Register the target environment with Jupyter as a kernel."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to register.")
        env_vars = self._get_environment()
        display_name = self.spec_manager.display_name or self.resolved_kname
        self.logger.debug(
            f"The resolved env vars for environment '{self.resolved_kname}' are '{env_vars}'."
        )
        if not self.env_manager.register_environment(
            self.resolved_kname, display_name, env_vars
        ):
            return False
        return True

    def _unregister_environment(self) -> bool:
        """Unregister the target environment from Jupyter."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name found to unregister.")
        return self.env_manager.unregister_environment(self.resolved_kname)

    def _submit_for_build(self) -> bool:
        """PR the spec and trigger a wrangler image build."""
        return self.injector.submit_for_build()

    def _inject_spi(self) -> bool:
        """Populat the local SPI clone with requirements and info from the spec."""
        if not self.resolved_kname:
            return self.logger.error("No kernel name found for SPI injection.")
        exports_str = self._data_get_exports()
        return self.injector.inject(self.resolved_kname, exports_str)
