# Wrangler Spec Format

## Example Spec

Below is a prototype wrangler spec for TIKE in the new format:

```yaml
# Image header information
image_spec_header:
  image_name: TIKE 2025.07-beta
  deployment_name: tike
  kernel_name: tess
  display_name: TESS
  description: |
    This is a beta test of the latest TIKE packages. Use at your own risk!
  valid_on: 2025-07-02
  expires_on: 2025-10-02
  python_version: 3.11.13

# Repositories where notebooks are located
repositories:
  tike_content:
    url: https://github.com/spacetelescope/tike_content
    ref: main
  mast_notebooks:
    url: https://github.com/spacetelescope/mast_notebooks
    ref: main

# Named blocks for selecting notebooks
selected_notebooks:
  tike_lcviz:
    repo: tike_content
    root_directory: content/notebooks/lcviz-tutorial/
    include_subdirs: [ "." ]
    tests:
      papermill: false # This notebook is known to fail papermill tests
  tike_data_access:
    repo: tike_content
    root_directory: content/notebooks/data-access/
    include_subdirs: [ "." ]
  mast_kepler:
    repo: mast_notebooks
    root_directory: notebooks/Kepler
    include_subdirs:
      - identifying_transiting_planet_signals
      - instrumental_noise_4_electronic_noise

extra_mamba_packages:
  - pip
common_mamba_packages:
  - hdf5
extra_pip_packages:
  - boto3
common_pip_packages:
  - requests

system:
  spec_version: 1.0
  archive_format: .tar
  primary_repo: tike_content
  nb-wrangler:
    repo: https://github.com/spacetelescope/nb-wrangler.git
    ref: main
  spi:
    repo: https://github.com/spacetelescope/science-platform-images.git
    ref: main
```

## Sections of the Wrangler Spec

### **image_spec_header**
This section provides metadata about the image and Python environment.
   - **image_name**: A name for your image (e.g., `TIKE 2025.07-beta`).
   - **deployment_name**: The deployment name, which can be `tike`, `roman`, `jwebbinar`, or `wrangler`.
   - **kernel_name**: The kernel name, currently `tess`, `roman-cal`, or `masterclass` for SPI injection,  anything for wrangler.
   - **display_name**: The name as it will appear in the JupyterLab kernel selection list (e.g., `TESS`).
   - **description**: A brief description of the image and its purpose.
   - **valid_on** and **expires_on**: Dates specifying when the image becomes valid and when it expires, respectively.
   - **python_version**: The version of Python supported by the image (e.g., `3.11.13`). This is used for simple definition environments and is mutually exclusive with `environment_spec` or an inline mamba spec.

### **repositories**
This section defines a dictionary of the git repositories that contain notebooks. Each repository is given a short, memorable name that will be used to refer to it in the `selected_notebooks` section.

Each entry in `repositories` has the following fields:
- **url**: The URL of the git repository.
- **ref**: The git branch, tag, or commit hash to use (defaults to `main`).

### **dev_overrides**
This optional top-level section allows developers to temporarily override any top-level sections of the spec for development purposes without modifying the core production-ready configuration.

When the `--dev` CLI flag is used (or implicitly activated for curation workflows), `nb-wrangler` will apply these overrides. When `--finalize-dev-overrides` is used, this section is removed.

The structure of `dev_overrides` mirrors the top-level sections it intends to override. For example, to override `repositories` (including `url` for forked development), `refdata_dependencies`, and `system.spi`:

```yaml
dev_overrides:
  repositories:
    your_repo_name:
      url: https://github.com/your-fork/your_repo_name # Override URL for forked development
      ref: your-dev-branch
    another_repo:
      ref: another-dev-ref
  refdata_dependencies:
    other_variables:
      YOUR_VAR: "dev_value"
  system:
    spi:
      ref: your-spi-dev-branch
```


### **selected_notebooks**

This section is a dictionary of "selection blocks". Each block has a unique name and defines a set of rules for selecting notebooks from the declared repositories. This is the heart of the wrangler spec as it also implies Python package (per-notebook `requirements.txt`) and data requirements (global per-repo `refdata_dependencies.yaml`).

Each selection block has the following fields:

  - **repo**: The name of a repository defined in the `repositories` section.
  - **root_directory**: Defines the root directory within the repository where the notebooks are stored.
  - **include_subdirs**: A list of subdirectories or regex patterns under `root_directory` to include.
  - **exclude_subdirs**: A list of subdirectories or regex patterns under `root_directory` to exclude.
  - **tests**: An optional dictionary to specify test configurations. For example, `tests: { papermill: false }` will disable the default `papermill` test for notebooks in this block.

The combination of `root_directory`, `include_subdirs`, and `exclude_subdirs` is flexible and allows different selection styles:

1. Pick notebook directories directly under `root_directory` as individual `include_subdirs` lines.  This avoids the clutter of repeating `root_directory` with each notebook in an otherwise simple explicit list.
2. To keep things simple, leave `root_directory` as an empty string and just include the full path from the root of the repo to the notebook directory in `include_subdirs`.
3. Use regular expressions in `include_subdirs` and `exclude_subdirs` to select notebooks based on patterns. For example, `include_subdirs: [".*"]` will include all notebooks under the `root_directory`.

### **refdata_dependencies**

This optional section allows for image-wide data dependencies defined directly in the wrangler spec. These dependencies are merged with any `refdata_dependencies.yaml` files discovered at the root of the notebook repositories.

This is useful for decoupling data definitions from specific notebook repositories, or for providing common data needed by all notebooks in the image.

The format follows the same structure as the repository-level `refdata_dependencies.yaml` files:
- **install_files**: A dictionary of data packages to download and unpack.
- **other_variables**: A dictionary of environment variables to set.

See [Reference Data Dependencies](refdata_dependencies.md) for more details on the format.

### **extra_mamba_packages**
A list of additional mamba packages required specifically by your curated kernel environment.

### **common_mamba_packages**
A list of additional mamba packages required by your curated kernel environment that are *also* required by the science platform's base environment. When using SPI injection (`--inject-spi`), these packages are written to `common-hints.mamba` to ensure they are available across all environments in the image.

### **extra_pip_packages**
A list of additional pip packages required specifically by your curated kernel environment.

### **common_pip_packages**
A list of additional pip packages required by your curated kernel environment that are *also* required by the science platform's base environment. When using SPI injection (`--inject-spi`), these packages are written to `common-hints.pip` to ensure they are available across all environments in the image.

### **system**
This section contains specifications for the system environment. It is updated by nb-wrangler automatically and should rarely need curator updates.

   - **spec_version**: The version of the specification being used (e.g., `1.0`).
   - **archive_format**: The format used for archiving environments (e.g., `.tar`).
   - **primary_repo**: The name of the primary repository (must match a key in the `repositories` section). This repository is treated as the "owner" of the spec and is used to drive automated workflows.
   - **nb-wrangler**: A dictionary specifying the `nb-wrangler` repository to use for the curation process.
     - **repo**: The URL of the git repository.
     - **ref**: (Optional) The branch, tag, or commit hash to use.
   - **spi**: A dictionary specifying the Science Platform Images (SPI) repository to use.
     - **repo**: The URL of the git repository.
     - **ref**: (Optional) The branch, tag, or commit hash to use. Defaults to the repository's default branch.
   - **spec_sha256**: An sha256 hash of the spec when it was last saved, for integrity checking. It is added by `nb-wrangler`.
   - **date_updated**: The timestamp when the spec was last updated.


   