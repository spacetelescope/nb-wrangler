"""Repository management for cloning and updating notebook repositories."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict

from .config import WranglerConfigurable
from .logger import WranglerLoggable
from .environment import WranglerEnvable
from .constants import REPO_CLONE_TIMEOUT, DEFAULT_CLEANUP_PATTERNS


class RepositoryManager(WranglerConfigurable, WranglerLoggable, WranglerEnvable):
    """Manages git repository operations for notebook collections."""

    def __init__(self, repos_dir: Path):
        super().__init__()
        self.repos_dir = repos_dir

    def run(self, *args, **keys):
        return self.env_manager.wrangler_run(*args, **keys)

    def handle_result(self, *args, **keys):
        return self.env_manager.handle_result(*args, **keys)

    def setup_repos(
        self,
        repo_urls: list[str],
        floating_mode: bool = True,
        repo_refs: Optional[dict[str, str | None]] = None,
    ) -> dict[str, str]:
        """set up all specified repositories."""
        self.logger.debug(f"Setting up repos. urls={repo_urls}.")
        repo_states = {}
        for repo_url in repo_urls:
            ref = repo_refs.get(repo_url) if repo_refs else None
            repo_path = self._setup_remote_repo(
                repo_url,
                floating_mode=floating_mode,
                ref=ref,
            )
            if not repo_path:
                raise RuntimeError(f"Failed to setup repository {repo_url}")
            current_hash = self.get_hash(repo_path)
            if not current_hash:
                raise RuntimeError(f"Failed to get hash for repository {repo_url}")
            repo_states[repo_url] = current_hash
        return repo_states

    def _repo_path(self, repo_url: str) -> Path:
        """Get the path for a repository."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_name = repo_name.split("@")[0]
        return self.repos_dir / repo_name

    get_repo_path = _repo_path

    def _setup_remote_repo(
        self,
        repo_url: str,
        floating_mode: bool,
        ref: Optional[str] = None,
    ) -> Optional[Path]:
        """Set up a remote repository by cloning or updating."""
        repo_path = self._repo_path(repo_url)
        if repo_path.exists():
            self.logger.debug(f"Using existing local clone at {repo_path}")
            repo_name = repo_path.name
            try:
                if floating_mode:
                    self.logger.debug(f"Floating mode: updating repo {repo_url}")
                    self.run("git fetch --tags", check=True, cwd=repo_path)

                    # Determine default branch from origin
                    result = self.run(
                        "git symbolic-ref refs/remotes/origin/HEAD",
                        check=False,
                        capture_output=True,
                        cwd=repo_path,
                    )
                    if result.returncode != 0:
                        return self.logger.error(
                            f"Failed to determine default branch for {repo_url}."
                        )
                    default_branch = (
                        result.stdout.strip()
                        .replace("refs/remotes/origin/", "")
                        .replace("\n", "")
                    )
                    ref_to_checkout = ref or f"origin/{default_branch}"

                    # Attempt direct checkout first (exact branch or tag)
                    checkout_success = self.git_checkout(repo_name, ref_to_checkout)

                    # For tag‑prefix refs (e.g., "2026.2"), fall back to prefix matching
                    if not checkout_success and ref:
                        resolved_sha = self.resolve_ref_to_sha(repo_name, ref)
                        if resolved_sha:
                            checkout_success = self.git_checkout(
                                repo_name, resolved_sha
                            )

                    if checkout_success:
                        if ref:
                            self.run(
                                "git pull", check=True, cwd=repo_path
                            )  # Pull updates
                    else:
                        raise ValueError(
                            f"Could not find ref '{ref_to_checkout}' in {repo_url}."
                        )
                else:  # locked mode
                    if ref:
                        self.logger.info(
                            f"Locked mode: checking out ref {ref} for repo {repo_url}"
                        )
                        self.run(f"git checkout {ref}", check=True, cwd=repo_path)
                    else:
                        self.logger.warning(
                            f"Locked mode enabled, but no ref provided for {repo_url}. Using existing state."
                        )
            except Exception as e:
                return self.logger.exception(
                    e, f"Failed to update repository {repo_url}."
                )
        else:
            try:
                # In floating mode we clone without a specific ref; we'll resolve and checkout later.
                # In locked (non‑floating) mode we may need to clone a particular branch/tag directly.
                branch_to_clone = None if floating_mode else ref
                self.git_clone(repo_url, repo_path, ref=branch_to_clone)

                # Ensure the checkout happens only after successful clone for locked mode
                if not floating_mode and ref:
                    self.logger.info(
                        f"Locked mode: checking out ref {ref} for repo {repo_url}"
                    )
                    self.run(f"git checkout {ref}", check=True, cwd=repo_path)
            except Exception as e:
                return self.logger.exception(
                    e,
                    f"Failed to setup repository {repo_url}.",
                )

        return repo_path

    def git_clone(
        self,
        repo_url: str,
        repo_dir: Path,
        ref: Optional[str] = None,
    ) -> bool:
        """Clone a new repository."""
        # Clone the main branch first
        clone_args = ""
        self.logger.info(f"Cloning repository {repo_url} to {repo_dir}.")
        if self.env_manager is None:
            raise RuntimeError("Environment manager not available")
        self.run(
            f"git clone {clone_args} {repo_url} {str(repo_dir)}",
            check=True,
            timeout=REPO_CLONE_TIMEOUT,
        )
        # Check out the specific ref if provided
        if ref:
            self.logger.info(f"Checking out reference {ref}.")
            repo_name = Path(repo_url).name.replace(".git", "")
            return self.git_checkout(repo_name, ref)
        return True

    def get_hash(self, repo_path: str | Path) -> Optional[str]:
        """Get the current commit hash of a repository."""
        if not self.is_clean(repo_path):
            self.logger.warning(
                f"Repo '{repo_path}' is dirty, hash may not be accurate."
            )
        result = self.run("git rev-parse HEAD", check=False, cwd=repo_path)
        if result.returncode == 0:
            return result.stdout.strip()
        self.logger.error(f"Failed to get git hash for repo {repo_path}")
        return None

    def delete_repos(self, urls: list[str]) -> bool:
        """Clean up cloned repositories."""
        try:
            for url in urls:
                path = self._repo_path(url)
                if path.exists():
                    self.logger.debug("Removing repo directory:", str(path))
                    shutil.rmtree(path)
                else:
                    self.logger.debug("Skipping delete for nonexistent:", str(path))
            remaining_contents = [str(obj) for obj in self.repos_dir.glob("*")]
            if not remaining_contents:
                self.logger.debug(
                    "Removing empty repos directory:", str(self.repos_dir)
                )
                self.repos_dir.rmdir()
            else:
                self.logger.debug(
                    "Skipping removal of non-empty repos directory:",
                    str(self.repos_dir),
                    "due remaining contents:",
                    remaining_contents,
                )
            return True
        except Exception as e:
            return self.logger.exception(e, "Error during repository deletion:")

    def is_clean(self, repo_root: str | Path) -> bool:
        stats: str = self.run("git status --porcelain", check=True, cwd=repo_root)
        stats = "clean" if stats == "" else "dirty"
        self.logger.debug(f"Repo '{repo_root}' status is: {stats}.")
        return stats == "clean"

    def branch_repo(
        self, repo_name: str, new_branch: str, ingest_branch: str = "origin/main"
    ) -> bool:
        repo_root = self.repos_dir / repo_name
        if not repo_root.exists():
            return self.logger.error(f"Can't branch non-existent repo {repo_name}.")
        if not self.is_clean(repo_root):
            return self.logger.error(f"Won't branch dirty repo {repo_name}.")
        self.logger.debug(
            f"Branching {repo_name} from {ingest_branch} to {new_branch}."
        )
        if not self.git_checkout(repo_name, ingest_branch):
            return False
        if not self.git_create_branch(repo_name, new_branch):
            return False
        return True

    def git_checkout(self, repo_name: str, branch: str) -> bool:
        repo_root = self.repos_dir / repo_name
        result = self.run(f"git checkout {branch}", check=False, cwd=repo_root)
        if result.returncode == 0:
            self.logger.debug(f"Checked out repo {repo_name} existing branch {branch}.")
            return True
        else:
            self.logger.warning(
                f"Failed checking out repo {repo_name} existing branch {branch}."
            )
            self.logger.warning(
                "This is normal for abstract tags that do not exist but patch tags do exist."
            )
            self.logger.debug(f"returncode was: {result.returncode}")
            self.logger.debug(f"stdout was: {result.stdout}")
            self.logger.debug(f"stderr was: {result.stderr}")
            return False

    def git_create_branch(self, repo_name, new_branch):
        repo_root = self.repos_dir / repo_name
        result = self.run(f"git checkout -b {new_branch}", check=False, cwd=repo_root)
        return self.handle_result(
            result,
            f"Failed creating new branch {new_branch} of repo {repo_name}: ",
            f"Created new branch {new_branch} of repo {repo_name}.",
        )

    def git_add(self, repo_name: str, path_to_add: str | Path) -> bool:
        path_to_add = str(path_to_add)
        repo_root = self.repos_dir / repo_name
        result = self.run(f"git add {path_to_add}", check=False, cwd=repo_root)
        return self.handle_result(
            result,
            f"Failed adding {path_to_add} from {repo_name}: ",
            f"Added {path_to_add} to {repo_name}.",
        )

    def git_commit(self, repo_name: str, commit_msg: str) -> bool:
        repo_root = self.repos_dir / repo_name
        with tempfile.NamedTemporaryFile(mode="w+") as temp:
            temp.write(commit_msg)
            temp.flush()
            result = self.run(f"git commit -F {temp.name}", check=False, cwd=repo_root)
            return self.handle_result(
                result,
                f"Failed commiting {repo_name}: ",
                f"Commited {repo_name}.",
            )

    def git_push(self, repo_name: str, branch_name: str) -> bool:
        repo_root = self.repos_dir / repo_name
        if branch_name == "main":
            return self.logger.error(
                f"As a safety measure, refusing to push to main branch of {repo_name}."
            )
        result = self.run(f"git push origin {branch_name}", check=False, cwd=repo_root)
        return self.handle_result(
            result,
            f"Failed pushing repo {repo_name} branch {branch_name}: ",
            f"Pushed repo {repo_name} branch {branch_name}.",
        )

    def git_remote_add(self, remote_name: str, remote_url: str) -> bool:
        repo_path = self._repo_path(remote_url)
        result = self.run(
            f"git remote add {remote_name} {remote_url}", check=False, cwd=repo_path
        )
        return self.handle_result(
            result,
            f"Failed adding remote {remote_name} = {remote_url} to {repo_path}: ",
            f"Added remote {remote_name} to {repo_path}.",
            error_func=self.logger.debug,
        )

    def github_create_pr(
        self, repo_name: str, merge_to: str, title: str, body_msg: str
    ) -> bool:
        repo_root = self.repos_dir / repo_name
        with tempfile.NamedTemporaryFile(mode="w+") as temp:
            temp.write(body_msg)
            temp.flush()
            result = self.run(
                (
                    "gh",
                    "pr",
                    "create",
                    # "--base",
                    # merge_to,
                    "--no-maintainer-edit",
                    "--title",
                    "'" + title + "'",
                    "--body-file",
                    temp.name,
                ),
                check=False,
                cwd=repo_root,
            )
            return self.handle_result(
                result,
                f"Failed creating PR {title} for {repo_name}: ",
                f"Created PR {title} to {merge_to} for {repo_name}.",
            )

    def github_merge_pr(
        self, repo_name: str, merge_from: str, title: str, body_msg: str
    ) -> bool:
        repo_root = self.repos_dir / repo_name
        with tempfile.NamedTemporaryFile(mode="w+") as temp:
            temp.write(body_msg)
            temp.flush()
            result = self.run(
                (
                    "gh",
                    "pr",
                    "merge",
                    merge_from,
                    "--rebase",
                    "-t",
                    "'" + title + "'",
                    "--body-file",
                    temp.name,
                ),
                check=False,
                cwd=repo_root,
            )
            return self.handle_result(
                result,
                f"Failed merging PR {title} to {repo_name}: ",
                f"Merged PR {title} to {repo_name}.",
            )

    def _clone_and_checkout(
        self, repo_url: str, repo_path: Path, desired_ref: str
    ) -> bool:
        """Clone the repository and check out the desired reference."""
        self.logger.info(f"Repository {repo_path.name} not found locally. Cloning...")
        repo_name = repo_path.name

        # Determine if the ref is a commit hash
        is_commit_hash = self._is_commit_hash(desired_ref)

        # Clone repository without specifying a ref; we'll handle checkout afterwards.
        if not self.git_clone(repo_url, repo_path):
            return False

        # If the desired reference is a raw commit SHA, check it out directly.
        if is_commit_hash:
            return self.git_checkout(repo_name, desired_ref)

        # Attempt to checkout the ref directly (branch or tag). This works for branches and exact tags.
        if self.git_checkout(repo_name, desired_ref):
            return True

        # For tag‑prefix refs (or ambiguous cases), resolve to a SHA then checkout.
        resolved = self.resolve_ref_to_sha(repo_name, desired_ref)
        if resolved:
            self.logger.info(f"Resolved ref '{desired_ref}' to SHA {resolved}")
            return self.git_checkout(repo_name, resolved)

        return False

    def _handle_dirty_repository(self, repo_name: str) -> bool:
        """
        Handles a dirty repository by stashing, resetting, or prompting the user.
        Returns True if the repository becomes clean, False otherwise.
        """
        self.logger.warning(f"Repository '{repo_name}' has uncommitted local changes.")
        if self.config.overwrite_local_changes:
            self.logger.info(
                f"Overwriting local changes in {repo_name} due to --overwrite-local-changes flag."
            )
            return self.git_reset_hard(repo_name)

        if self.config.stash_local_changes:
            self.logger.info(
                f"Stashing local changes in {repo_name} due to --stash-local-changes flag."
            )
            return self.git_stash(repo_name)

        if self.config.use_dirty_repos:
            return self.logger.info(f"Using dirty repository {repo_name} as-is.")

        while True:
            prompt = f"Repo '{repo_name}' is dirty. [S]tash changes, [D]iscard changes, [I]gnore (use as-is), or [A]bort? (S/D/I/A): "
            choice = input(prompt).upper()
            if choice == "A":
                return self.logger.error("Operation aborted by user.")
            elif choice == "S":
                return self.git_stash(repo_name)
            elif choice == "D":
                return self.git_reset_hard(repo_name)
            elif choice == "I":
                return self.logger.info(f"Using dirty repository {repo_name} as-is.")

    def prepare_repository(self, repo_url: str, desired_ref: str) -> bool:
        """Ensure a repository is cloned and at the correct, clean ref."""
        self.logger.info(f"Preparing repository {repo_url} at ref {desired_ref}")
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = self._repo_path(repo_url)

        if not repo_path.exists():
            return self._clone_and_checkout(repo_url, repo_path, desired_ref)
        elif (repo_path / ".git").exists():
            backup_dir = str(repo_path) + ".bak"
            if os.path.exists(backup_dir):
                self.logger.warning(
                    f"Backup directory {backup_dir} already exists; removing it before new backup."
                )
                try:
                    shutil.rmtree(backup_dir)
                except Exception as e:
                    return self.logger.error(
                        f"Failed to remove existing backup {backup_dir}: {e}"
                    )

            # Move the current repo into the backup location, then reclone fresh.
            try:
                shutil.move(str(repo_path), backup_dir, copy_function=shutil.copytree)
            except Exception as e:
                return self.logger.error(
                    f"Failed to backup existing repository {repo_name}: {e}"
                )
            return self._clone_and_checkout(repo_url, repo_path, desired_ref)

        # Additional safeguard: if the repository has no commits (unborn HEAD), force a fresh clone.
        if self.get_hash(repo_path) is None:
            self.logger.warning(
                f"Repository {repo_name} appears to be empty or unborn; recloning."
            )
            # Remove the broken directory before recloning
            try:
                shutil.rmtree(repo_path)
            except Exception as e:
                return self.logger.error(
                    f"Failed to delete corrupted repository {repo_name}: {e}"
                )
            return self._clone_and_checkout(repo_url, repo_path, desired_ref)

        if self.config.use_dirty_repos:
            return self.logger.info(
                f"Using existing repository {repo_name} as-is due to --use-dirty-repos."
            )

        if not self.is_clean(repo_path):
            self.logger.info(
                f"Repository {repo_name} is dirty. Attempting auto-clean of default patterns."
            )
            self.clean_repo(repo_path, DEFAULT_CLEANUP_PATTERNS)
            if not self.is_clean(repo_path):
                if not self._handle_dirty_repository(repo_name):
                    return False  # Operation failed or was aborted
                if not self.is_clean(repo_path):
                    return True  # User chose to ignore (as-is)

        # Now the repo is clean, check if it's on the correct commit
        current_sha = self.get_hash(repo_path)
        if current_sha is None:
            return False
        target_sha = self.resolve_ref_to_sha(repo_name, desired_ref)
        if target_sha is None:
            return False

        if current_sha == target_sha:
            sha_info = f" ({target_sha[:7]})" if target_sha else ""
            return self.logger.info(
                f"Repository {repo_name} is already at the desired ref {desired_ref}{sha_info}."
            )

        self.logger.info(f"Updating repository {repo_name} to ref {desired_ref}.")
        return self.git_checkout(repo_name, target_sha)

    def git_stash(self, repo_name: str) -> bool:
        """Stash local changes in the given repository."""
        repo_root = self.repos_dir / repo_name
        self.logger.info(f"Stashing local changes in {repo_root}")
        result = self.run("git stash", check=False, cwd=repo_root)
        return self.handle_result(
            result,
            f"Failed to stash changes in {repo_name}: ",
            f"Stashed local changes in {repo_name}.",
        )

    def git_reset_hard(self, repo_name: str) -> bool:
        """Reset the repository, discarding all local changes."""
        repo_root = self.repos_dir / repo_name
        self.logger.warning(
            f"Discarding local changes in {repo_root} with 'git reset --hard HEAD'"
        )
        result = self.run("git reset --hard HEAD", check=False, cwd=repo_root)
        return self.handle_result(
            result,
            f"Failed to reset repository {repo_name}: ",
            f"Successfully reset {repo_name}, discarding local changes.",
        )

    def resolve_ref_to_sha(self, repo_name: str, ref: str) -> Optional[str]:
        """Resolve a git ref (branch, tag prefix, or hash) to its commit SHA.
        If multiple tags share the given prefix, the highest semver tag is used.
        """
        repo_root = self.repos_dir / repo_name
        self.logger.info(f"Resolving ref '{ref}' to SHA in {repo_root}")
        # Fetch latest tags and refs
        self.run("git fetch --tags", check=False, cwd=repo_root)
        # Get sorted tags (highest semver first)
        all_tags = self.fetch_sorted_tags(repo_root)
        # Filter tags that start with the provided ref as a prefix
        matching_tags = [t for t in all_tags if t.startswith(ref)]
        if matching_tags:
            best_tag = matching_tags[0]  # already highest due to sorting
            self.logger.info(f"Selected patch tag '{best_tag}' for ref prefix '{ref}'.")
            result = self.run(f"git rev-parse {best_tag}", check=False, cwd=repo_root)
            if result.returncode == 0:
                return result.stdout.strip()
            self.logger.error(
                f"Failed to resolve selected tag '{best_tag}' in repo {repo_name}."
            )
        # Fallback: try resolving ref directly (branch name or commit hash)
        result = self.run(f"git rev-parse {ref}", check=False, cwd=repo_root)
        if result.returncode == 0:
            return result.stdout.strip()
        self.logger.error(f"Failed to resolve ref '{ref}' in repo {repo_name}")
        return None

    def fetch_sorted_tags(self, repo_path: Path) -> list[str]:
        """Fetch all tags from the remote and return them sorted lexicographically descending.
        Tags are treated as plain strings; no semantic version parsing is performed.
        """
        # Ensure we have latest tags
        self.run("git fetch --tags", check=False, cwd=repo_path)
        result = self.run("git tag -l", check=False, cwd=repo_path)
        if result.returncode != 0:
            self.logger.error(f"Failed to list tags in {repo_path}")
            return []
        tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        # Sort strings descending (highest lexical order first)
        tags.sort(reverse=True)
        return tags

    def _is_commit_hash(self, ref: str) -> bool:
        """Check if a string looks like a commit hash (40-char hex)."""
        return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)

    def resolve_ref_to_entry(
        self, repo_name: str, ref: str
    ) -> Optional[tuple[Optional[str], str]]:
        """Resolve a git ref (branch, tag prefix, or hash) to the matched entry.

        Returns a tuple of (matched_tag_or_ref, sha), or None if resolution fails.
        For prefix-tag matching, matched is the specific tag name that was chosen.
        For direct branch/tag names, matched is the input ref itself.
        """
        repo_root = self.repos_dir / repo_name
        # Fetch latest tags and refs
        self.run("git fetch --tags", check=False, cwd=repo_root)
        # Get sorted tags (highest lexicographic first)
        all_tags = self.fetch_sorted_tags(repo_root)
        # Filter tags that start with the provided ref as a prefix
        matching_tags = [t for t in all_tags if t.startswith(ref)]
        if matching_tags:
            best_tag = matching_tags[0]  # already highest due to sorting
            result = self.run(f"git rev-parse {best_tag}", check=False, cwd=repo_root)
            if result.returncode == 0:
                return (best_tag, result.stdout.strip())
        # Fallback: try resolving ref directly (branch name or commit hash)
        result = self.run(f"git rev-parse {ref}", check=False, cwd=repo_root)
        if result.returncode == 0:
            return (ref, result.stdout.strip())
        self.logger.error(f"Failed to resolve ref '{ref}' in repo {repo_name}")
        return None

    def prepare_repositories(
        self, repos_to_prepare: Dict[str, str], floating_mode: bool = True
    ) -> tuple[Dict[str, str], Dict[str, Optional[str]]]:
        """
        Prepare multiple repositories and return their resolved states.

        Args:
            repos_to_prepare: Dictionary mapping repo URLs to desired refs
            floating_mode: Whether to use floating mode (update to latest)

        Returns:
            Tuple of (resolved_shas, resolved_refs) where:
                - resolved_shas maps repo URLs to their resolved commit SHAs
                - resolved_refs maps repo URLs to the resolved tag/branch name that was matched
                  (captured via tag-prefix resolution logic; None for commit-hash refs)
        """
        resolved_repo_states = {}
        resolved_ref_names: Dict[str, Optional[str]] = {}
        for repo_url, desired_ref in repos_to_prepare.items():
            if not self.prepare_repository(repo_url, desired_ref):
                raise RuntimeError(f"Failed to prepare repository {repo_url}")

            # Get the actual hash after preparation
            repo_path = self._repo_path(repo_url)
            current_sha = self.get_hash(repo_path)
            if not current_sha:
                raise RuntimeError(
                    f"Could not get current SHA for {repo_url} after preparation."
                )
            resolved_repo_states[repo_url] = current_sha

            # Capture the matched ref name using the same logic as resolve_ref_to_sha
            is_hash = self._is_commit_hash(desired_ref)
            if is_hash:
                resolved_ref_names[repo_url] = None
            else:
                repo_name = repo_path.name
                matched_entry = self.resolve_ref_to_entry(repo_name, desired_ref)
                if matched_entry:
                    resolved_ref_names[repo_url] = matched_entry[0]

        return resolved_repo_states, resolved_ref_names

    def clean_repo(self, repo_path: Path, patterns: list[str]) -> bool:
        """Clean up specified patterns in a cloned repository."""
        self.logger.debug(f"Cleaning patterns {patterns} in repository {repo_path}.")
        try:
            if not repo_path.exists():
                self.logger.debug(f"Skipping clean for nonexistent: {repo_path}")
                return True

            for pattern in patterns:
                for path in repo_path.rglob(pattern):
                    if path.is_dir():
                        self.logger.debug(f"Deleting directory: {path}")
                        shutil.rmtree(path)
                    else:
                        self.logger.debug(f"Deleting file: {path}")
                        path.unlink()
            return True
        except Exception as e:
            return self.logger.exception(e, f"Error during cleaning of {repo_path}:")

    def clean_repos(self, urls: list[str], patterns: list[str]) -> bool:
        """Clean up specified patterns in cloned repositories."""
        self.logger.info(f"Cleaning patterns {patterns} in cloned repositories.")
        success = True
        for url in urls:
            repo_path = self._repo_path(url)
            if not self.clean_repo(repo_path, patterns):
                success = False
        return success
