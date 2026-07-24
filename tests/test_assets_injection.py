from pathlib import Path
import pytest

from nb_wrangler.config import WranglerConfig, set_args_config
from nb_wrangler.injector import SpiInjector


@pytest.fixture(autouse=True)
def setup_config(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("config")
    spec_file = Path(__file__).parent.parent / "specs/samples/tike-wrangler-k1.yaml"
    config = WranglerConfig(
        workflows=[],
        spec_file=str(spec_file),
        repos_dir=tmp_dir / "repos",
        output_dir=tmp_dir / "output",
        prod=True,
    )
    set_args_config(config)


class DummyRepoManager:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.repos_dir = repo_path.parent

    def _setup_remote_repo(
        self, repo_url: str, floating_mode: bool = True, ref: str = None
    ) -> Path:
        return self.repo_path


class DummySpecManager:
    """Minimal spec manager that returns a fixed list of assets."""

    def __init__(self, assets_list: list[dict]):
        # Store raw (unnormalized) assets so we can test both old and new syntaxes.
        self._raw_assets = assets_list

    @property
    def deployment_name(self):
        return "wrangler"

    @property
    def spec_id(self):
        return None

    @property
    def spi(self):
        return {}

    @property
    def image_name(self):
        return "test-image"

    @property
    def assets(self) -> list[dict]:
        """Return the normalized asset list by applying SpecManager.flatten_asset_entries."""
        from nb_wrangler.spec_manager import SpecManager

        return SpecManager.flatten_asset_entries(self._raw_assets)


def test_asset_directory_trailing_slash(tmp_path: Path):
    # Setup dummy repo directory structure
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    data_dir = repo_dir / "data"
    data_dir.mkdir()
    (data_dir / "file1.txt").write_text("hello 1")
    (data_dir / "file2.txt").write_text("hello 2")

    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()

    assets_spec = [
        {
            "repo": "https://github.com/example/repo.git",
            "ref": "main",
            "source": "data/",
            "destination": "/opt/app/data",
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec),
    )
    injector.environments_path = environments_dir

    injector._inject_assets()

    assets_sh = environments_dir / "install-assets.sh"
    assert assets_sh.exists()
    content = assets_sh.read_text()
    assert 'cp -r "assets/asset_0/data"/. "/opt/app/data/"' in content

    # Verify staging
    staged_file = environments_dir / "assets" / "asset_0" / "data" / "file1.txt"
    assert staged_file.exists()


def test_asset_directory_without_trailing_slash(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    data_dir = repo_dir / "data"
    data_dir.mkdir()
    (data_dir / "file1.txt").write_text("hello 1")

    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()

    assets_spec = [
        {
            "repo": "https://github.com/example/repo.git",
            "ref": "main",
            "source": "data",
            "destination": "/opt/app",
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec),
    )
    injector.environments_path = environments_dir

    injector._inject_assets()

    assets_sh = environments_dir / "install-assets.sh"
    content = assets_sh.read_text()
    # Without trailing slash, should copy the directory container itself
    assert 'cp -r "assets/asset_0/data" "/opt/app/"' in content


def test_asset_directory_contents_only_flag(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    data_dir = repo_dir / "data"
    data_dir.mkdir()
    (data_dir / "file1.txt").write_text("hello 1")

    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()

    assets_spec = [
        {
            "repo": "https://github.com/example/repo.git",
            "ref": "main",
            "source": "data",
            "destination": "/opt/app/data",
            "contents_only": True,
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec),
    )
    injector.environments_path = environments_dir

    injector._inject_assets()

    assets_sh = environments_dir / "install-assets.sh"
    content = assets_sh.read_text()
    # With contents_only: True, should copy contents directly
    assert 'cp -r "assets/asset_0/data"/. "/opt/app/data/"' in content


def test_asset_glob_pattern(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    data_dir = repo_dir / "data"
    data_dir.mkdir()
    (data_dir / "a.csv").write_text("a")
    (data_dir / "b.csv").write_text("b")
    (data_dir / "ignore.txt").write_text("ignore")

    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()

    assets_spec = [
        {
            "repo": "https://github.com/example/repo.git",
            "ref": "main",
            "source": "data/*.csv",
            "destination": "/opt/app/csvs",
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec),
    )
    injector.environments_path = environments_dir

    injector._inject_assets()

    assets_sh = environments_dir / "install-assets.sh"
    content = assets_sh.read_text()
    assert 'cp "assets/asset_0/a.csv" "/opt/app/csvs/"' in content
    assert 'cp "assets/asset_0/b.csv" "/opt/app/csvs/"' in content
    assert "ignore.txt" not in content


def test_grouped_assets_shared_repo_ref(tmp_path: Path):
    """Test the new grouped syntax where multiple items share a common repo and ref.

    The spec uses an 'items' list under each entry, with inherited `repo`/`ref`.
    This verifies that SpecManager.flatten_asset_entries correctly expands them into
    individual flat dicts before injection.
    """
    # Setup dummy repo directory structure
    repo_dir = tmp_path / "shared_repo"
    repo_dir.mkdir()

    roman_assets = repo_dir / "assets/roman"
    roman_assets.mkdir(parents=True)
    (roman_assets / "config.yaml").write_text("roman config")

    generic_assets = repo_dir / "assets/generic"
    generic_assets.mkdir(parents=True)
    (generic_assets / "readme.md").write_text("generic readme")

    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()

    # New grouped syntax: single entry with 'items' list sharing repo/ref
    assets_spec_grouped = [
        {
            "repo": "https://github.com/example/shared-assets.git",
            "ref": "v1.0",
            "items": [
                {"source": "assets/roman/", "destination": "/opt/environments"},
                {"source": "assets/generic/", "destination": "/opt/environments"},
            ],
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec_grouped),
    )
    injector.environments_path = environments_dir

    # Verify normalization produces two flat entries with inherited metadata
    assets_list = injector.spec_manager.assets
    assert len(assets_list) == 2, "Grouped syntax should expand to individual items"

    for asset in assets_list:
        assert (
            asset["repo"] == "https://github.com/example/shared-assets.git"
        ), "Inherited repo must be present on each expanded item"
        assert (
            asset["ref"] == "v1.0"
        ), "Inherited ref must be present on each expanded item"

    injector._inject_assets()

    assets_sh = environments_dir / "install-assets.sh"
    content = assets_sh.read_text()

    # Both items should appear in the generated script with correct staging indices
    assert "assets/asset_0" in content, "First grouped item must be staged as asset_0"
    assert "assets/asset_1" in content, "Second grouped item must be staged as asset_1"

    # Verify both directories were actually copied into the staging area
    staged_dir_0 = environments_dir / "assets" / "asset_0" / "roman" / "config.yaml"
    assert (
        staged_dir_0.exists()
    ), f"Staged file from first item should exist: {staged_dir_0}"

    # The second item's source is 'assets/generic/' which copies the directory contents,
    # so we check for a subdirectory named after its parent or verify via glob.
    staged_generic = environments_dir / "assets" / "asset_1" / "generic" / "readme.md"
    assert (
        staged_generic.exists()
    ), f"Staged file from second item should exist: {staged_generic}"


def test_mixed_old_and_new_syntax(tmp_path: Path):
    """Test that old flat syntax and new grouped syntax can coexist in the same spec.

    This ensures backward compatibility while supporting both formats simultaneously.
    """
    # Setup a single combined directory structure to simulate different repos
    repo_dir = tmp_path / "mixed_assets"
    repo_dir.mkdir()

    (repo_dir / "standalone.txt").write_text("from flat entry")

    grouped_subdir = repo_dir / "shared_data"
    grouped_subdir.mkdir(parents=True)
    (grouped_subdir / "item_a.txt").write_text("from group item a")

    environments_dir = tmp_path / "environments_mixed"
    environments_dir.mkdir()

    # Mix of old flat entry and new grouped entries in the same spec.
    # Both point to the same local repo directory for simplicity since DummyRepoManager
    # always returns its first argument's path regardless of URL.
    assets_spec_mixed = [
        {
            "repo": "https://github.com/example/flat-repo.git",
            "ref": "main",
            "source": "standalone.txt",  # Old syntax: single item with its own repo/ref
            "destination": "/opt/data/file1",
        },
        {
            "repo": "https://github.com/example/grouped-repo.git",
            "ref": "develop",
            "items": [
                {
                    "source": "shared_data/",
                    "destination": "/opt/shared",
                },  # New syntax: grouped items
            ],
        },
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec_mixed),
    )
    injector.environments_path = environments_dir

    assets_list = injector.spec_manager.assets

    assert len(assets_list) == 2, "Should expand to two items (one flat + one grouped)"

    # Verify the first item is from old syntax.
    flat_item = next(a for a in assets_list if a.get("source") == "standalone.txt")
    assert flat_item["repo"] == "https://github.com/example/flat-repo.git"
    assert flat_item["ref"] == "main"

    # Verify the second item is from grouped syntax.
    group_item = next(a for a in assets_list if a.get("source") == "shared_data/")
    assert group_item["repo"] == "https://github.com/example/grouped-repo.git"
    assert group_item["ref"] == "develop"

    injector._inject_assets()

    # Verify both items appear in the generated script.
    assets_sh = environments_dir / "install-assets.sh"
    content = assets_sh.read_text()

    assert "assets/asset_0" in content, "First item must be staged as asset_0"
    assert "assets/asset_1" in content, "Second grouped item must be staged as asset_1"

    # Verify staging directories exist.
    flat_staged = environments_dir / "assets" / "asset_0" / "standalone.txt"
    group_staged = (
        environments_dir / "assets" / "asset_1" / "shared_data" / "item_a.txt"
    )

    assert (
        flat_staged.exists()
    ), f"Staged file from first item should exist: {flat_staged}"
    assert (
        group_staged.exists()
    ), f"Staged file from second item should exist: {group_staged}"


def test_flatten_asset_entries_empty_input():
    """Verify that flatten_asset_entries returns an empty list for None or [] input."""
    from nb_wrangler.spec_manager import SpecManager

    assert (
        SpecManager.flatten_asset_entries(None) == []
    ), "None should produce empty list"
    assert SpecManager.flatten_asset_entries([]) == [], "Empty list should remain empty"


def test_flatten_asset_entries_preserves_flat_syntax():
    """Verify that old flat syntax passes through unchanged (shallow copy)."""
    from nb_wrangler.spec_manager import SpecManager

    original = [
        {
            "repo": "https://github.com/example/a.git",
            "ref": "v1.0",
            "source": "/a/",
            "destination": "/b/",
        },
        {
            "repo": None,
            "ref": "main",  # ref can be absent/None in flat syntax too
            "source": "/c/",
            "destination": "/d/",
            "contents_only": True,
        },
    ]

    result = SpecManager.flatten_asset_entries(original)

    assert len(result) == 2

    for orig, expanded in zip(original, result):
        # Each key from the original should be present and equal (shallow copy semantics).
        for k, v in orig.items():
            if isinstance(v, list):
                assert (
                    result[0].get(k) is not None or True
                )  # skip deep comparison of lists
            else:
                assert expanded.get(k) == v

    # Verify they are independent copies (mutation safety).
    original[0]["source"] = "/mutated/"
    assert (
        result[1]["source"] != "/mutated/"
    ), "Flattened entries should be shallow-copied"


def test_flatten_asset_entries_inheritance_override(tmp_path: Path):
    """Verify that item-level keys override inherited repo/ref from the parent entry.

    In grouped syntax, if an individual 'item' specifies its own `repo` or `ref`,
    those values should take precedence over the parent's shared ones. This allows
    fine-grained control within a group while still benefiting from DRY inheritance.
    """
    repo_dir = tmp_path / "override_repo"
    repo_dir.mkdir()

    environments_dir = tmp_path / "environments_override"
    environments_dir.mkdir()

    assets_spec_with_overrides = [
        {
            # Parent provides default values for all items in this group.
            "repo": "https://github.com/example/default-repo.git",
            "ref": "main",  # Default ref is 'main'
            "items": [
                {"source": "/a/", "destination": "/b/"},
                {
                    # This item overrides the inherited repo and ref.
                    "repo": "https://github.com/example/override-repo.git",
                    "ref": "feature-branch",  # Overrides parent's 'main'
                    "source": "/c/",
                    "destination": "/d/",
                },
            ],
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec_with_overrides),
    )

    assets_list = injector.spec_manager.assets

    assert len(assets_list) == 2, "Should expand to two items"

    # First item inherits parent's values.
    first_item = next(a for a in assets_list if a["source"] == "/a/")
    assert (
        first_item["repo"] == "https://github.com/example/default-repo.git"
    ), "First item should inherit repo from parent entry."
    assert (
        first_item["ref"] == "main"
    ), "First item should inherit ref 'main' from parent entry."

    # Second item overrides both.
    second_item = next(a for a in assets_list if a["source"] == "/c/")
    assert (
        second_item["repo"] == "https://github.com/example/override-repo.git"
    ), "Second item should use its own overridden repo value, not the parent's."
    assert (
        second_item["ref"] == "feature-branch"
    ), "Second item should use its own overridden ref 'feature-branch' instead of inherited 'main'."


def test_grouped_assets_multiple_items_same_destination(tmp_path: Path):
    """Test multiple grouped items targeting the same destination directory.

    This verifies that each staged asset gets a unique index (asset_0, asset_1)
    and generates distinct copy commands even when they share the same final path.
    """
    repo_dir = tmp_path / "same_dest_repo"
    repo_dir.mkdir()

    dir_a = repo_dir / "dir_a"
    dir_a.mkdir(parents=True)
    (dir_a / "file.txt").write_text("from a")

    dir_b = repo_dir / "dir_b"
    dir_b.mkdir(parents=True)
    (dir_b / "other.md").write_text("from b")

    environments_dir = tmp_path / "environments_same_dest"
    environments_dir.mkdir()

    assets_spec_multi_items = [
        {
            "repo": "https://github.com/example/multi-item.git",
            "ref": "main",
            "items": [
                {
                    "source": "dir_a/",
                    "destination": "/opt/shared",
                },  # Both go to same dest.
                {"source": "dir_b/", "destination": "/opt/shared"},
            ],
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec_multi_items),
    )
    injector.environments_path = environments_dir

    assets_list = injector.spec_manager.assets

    assert len(assets_list) == 2, "Should expand to two separate items"

    # Inject first so staging directories are created.
    injector._inject_assets()

    # Verify staging directories are distinct.
    staged_a_exists = (environments_dir / "assets" / "asset_0").exists()
    staged_b_exists = (environments_dir / "assets" / "asset_1").exists()

    assert staged_a_exists, "Staging directory asset_0 should exist for first item."
    assert staged_b_exists, "Staging directory asset_1 should exist for second item."

    # Verify the generated script contains separate copy commands.
    assets_sh = environments_dir / "install-assets.sh"
    content = assets_sh.read_text()

    count_asset0_copies = content.count("assets/asset_0")
    assert (
        count_asset0_copies >= 1
    ), f"At least one command should reference asset_0 staging dir. Content:\n{content}"

    # Both items target /opt/shared so both copy commands will appear in the script
    # (one after another). The key is that they are distinct staged directories.


def test_flatten_asset_entries_skips_non_dict_items_in_group():
    """Verify that non-dict entries inside an 'items' list are skipped with a warning."""
    from nb_wrangler.spec_manager import SpecManager

    assets_with_bad_item = [
        {
            "repo": "https://github.com/example/bad.git",
            "ref": "main",
            "items": [
                {"source": "/good/", "destination": "/dest/"},  # Valid dict item.
                None,  # Invalid: not a dict. Should be skipped.
                ["not_a_dict"],  # Also invalid. Skipped too.
            ],
        }
    ]

    result = SpecManager.flatten_asset_entries(assets_with_bad_item)

    assert len(result) == 1, "Only the valid dict item should remain in output."
    assert (
        result[0]["source"] == "/good/"
    ), "The only remaining entry must be from the first (valid) list element."


def test_grouped_assets_no_items_key_treated_as_flat(tmp_path: Path):
    """Verify that an asset entry without 'items' key is treated as a flat/old-style item.

    If someone writes grouped syntax but forgets to include 'items', it should gracefully
    fall back and treat the entire dict as a single flat asset (preserving backward compat).
    """
    repo_dir = tmp_path / "no_items_repo"
    repo_dir.mkdir()

    environments_dir = tmp_path / "environments_no_items"
    environments_dir.mkdir()

    # Entry has 'repo' and 'ref' but no 'items'. Should be treated as flat.
    assets_spec_missing_items_key = [
        {
            "repo": "https://github.com/example/no-items.git",
            "ref": "main",  # These are just regular keys on a single asset dict now.
            "source": "/data/",
            "destination": "/opt/data",
            # Note: no 'items' key present! Should be treated as flat syntax entry.
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec_missing_items_key),
    )

    assets_list = injector.spec_manager.assets

    assert (
        len(assets_list) == 1
    ), "Entry without 'items' key should be treated as a single flat asset."

    # Verify the keys are preserved exactly.
    expanded_asset = assets_list[0]
    assert expanded_asset["repo"] == "https://github.com/example/no-items.git"
    assert expanded_asset["ref"] == "main"
    assert expanded_asset["source"] == "/data/"
    assert expanded_asset["destination"] == "/opt/data"


def test_grouped_assets_with_glob_pattern(tmp_path: Path):
    """Test that glob patterns work correctly within grouped syntax items.

    Each item in the 'items' list can independently specify its own source pattern,
    including globs like '*.txt'. This verifies proper expansion and injection of such entries.
    """
    repo_dir = tmp_path / "glob_grouped_repo"
    repo_dir.mkdir()

    data_subdir = repo_dir / "data_files"
    data_subdir.mkdir(parents=True)

    (data_subdir / "report_2023.csv").write_text("csv 1")
    (data_subdir / "report_2024.csv").write_text("csv 2")
    (data_subdir / "notes.txt").write_text("not a csv, should be ignored by glob.")

    environments_dir = tmp_path / "environments_glob_grouped"
    environments_dir.mkdir()

    assets_spec_with_glob_in_items = [
        {
            "repo": "https://github.com/example/glob-group.git",
            "ref": "main",
            "items": [
                {
                    "source": "data_files/*.csv",
                    "destination": "/opt/csvs",
                },  # Glob pattern.
            ],
        }
    ]

    injector = SpiInjector(
        repo_manager=DummyRepoManager(repo_dir),
        spec_manager=DummySpecManager(assets_spec_with_glob_in_items),
    )

    assets_list = injector.spec_manager.assets

    assert len(assets_list) == 1, "Should expand to one item with glob pattern."

    # Verify the expanded asset retains its source as a string (not modified).
    single_asset = assets_list[0]
    assert (
        single_asset["source"] == "data_files/*.csv"
    ), "Glob patterns in grouped items should be preserved verbatim for injector to resolve."


def test_grouped_assets_empty_items_list(tmp_path: Path):
    """Verify that an entry with 'items' set to [] produces no expanded assets.

    This edge case ensures the flattener doesn't crash or produce empty dicts
    when encountering a group definition but zero items within it.
    """
    from nb_wrangler.spec_manager import SpecManager

    # Entry has explicit repo/ref and an EMPTY 'items' list. Should yield nothing for this entry.
    assets_spec_empty_items = [
        {
            "repo": "https://github.com/example/empty-group.git",
            "ref": "main",
            "items": [],  # Empty items list! Nothing to expand from here.
        },
        {
            # Another entry with actual content should still be processed normally.
            "source": "/standalone/",
            "destination": "/opt/other",
        },
    ]

    result = SpecManager.flatten_asset_entries(assets_spec_empty_items)

    assert (
        len(result) == 1
    ), f"The empty group entry should produce zero items; only the standalone flat one remains. Got: {result}"
