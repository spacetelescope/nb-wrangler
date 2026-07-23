import shutil
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

    def _setup_remote_repo(self, repo_url: str, floating_mode: bool = True, ref: str = None) -> Path:
        return self.repo_path


class DummySpecManager:
    def __init__(self, assets_list: list[dict]):
        self._assets = assets_list
        self.spi = {"repo": "https://github.com/example/spi.git"}
        self.deployment_name = "test-deployment"

    @property
    def assets(self) -> list[dict]:
        return self._assets


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

    assets_sh = environments_dir / "dockerfile-assets.sh"
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

    assets_sh = environments_dir / "dockerfile-assets.sh"
    assert assets_sh.exists()
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

    assets_sh = environments_dir / "dockerfile-assets.sh"
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

    assets_sh = environments_dir / "dockerfile-assets.sh"
    content = assets_sh.read_text()
    assert 'cp "assets/asset_0/a.csv" "/opt/app/csvs/"' in content
    assert 'cp "assets/asset_0/b.csv" "/opt/app/csvs/"' in content
    assert 'ignore.txt' not in content
