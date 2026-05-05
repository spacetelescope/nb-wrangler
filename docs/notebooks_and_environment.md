# Managing Notebook Selection and Environments with nb-wrangler

The "wrangler half" of notebook curation revolves around the creation of a fully populated and tested
wrangler spec that catches the repos, notebooks, Python environment, and data associated with a single
Science Platform environment.
 
 The current process is to *define the spec*:

- Bootstrap and/or install nb-wrangler
- Copy an existing wrangler spec from the same project. See sample-specs.
- Update the header section of the spec.
- Add repo and notebook selection information to the selected_notebooks section.
- Add any extra mamba packages or mamba version constraints;  minimize these to those not available by pip
- Add any extra pip packages or pip version constraints not defined in requirements.txt files

## Notebook and Environment Curation

Once the curator's inputs are specified,  *run nb-wrangler* like this:

```bash
./nb-wrangler sample-specs/roman-20.0.0.yaml --curate
INFO: 00:00:00.000 Loading and validating spec /home/ai/nb-wrangler/sample-specs/roman-20.0.0.yaml
INFO: 00:00:00.017 Running workflows ['curation'].
INFO: 00:00:00.000 Running spec development / curation workflow
INFO: 00:00:00.000 Running step _clone_repos.
INFO: 00:00:00.000 Setting up repository clones.
INFO: 00:00:00.000 Using existing local clone at references/science-platform-images
INFO: 00:00:00.000 Using existing local clone at references/roman_notebooks
INFO: 00:00:00.001 Selected 7 notebooks under references/roman_notebooks/notebooks repository:
INFO: 00:00:00.000 Found stpsf.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found romanisim.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found roman_cutouts.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found pandeia.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found rist.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found synphot.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found time_domain_simulations.ipynb under references/roman_notebooks/notebooks.
INFO: 00:00:00.000 Found 7 notebooks in all notebook repositories.
INFO: 00:00:00.000 Processing 7 unique notebooks for imports.
INFO: 00:00:00.002 Extracted 27 package imports from 7 notebooks.
INFO: 00:00:00.000 Revising spec file /home/ai/nb-wrangler/sample-specs/roman-20.0.0.yaml.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/temps/roman-20.0.0.yaml.
INFO: 00:00:00.025 Running step _compile_requirements.
INFO: 00:00:00.000 Generating mamba spec for target environment /home/ai/.nbw-live/temps/roman-20.0.0-roman-cal-mamba.yml.
INFO: 00:00:00.000 Found SPI extra 1 mamba requirements files.
INFO: 00:00:00.001 Revising spec file /home/ai/nb-wrangler/sample-specs/roman-20.0.0.yaml.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/temps/roman-20.0.0.yaml.
INFO: 00:00:00.028 Found 7 notebook requirements.txt files.
INFO: 00:00:00.000 Found SPI extra 6 pip requirements files.
INFO: 00:00:00.000 w/o hashes.
INFO: 00:00:02.325 Compiled combined pip requirements to 366 package versions.
INFO: 00:00:00.000 Revising spec file /home/ai/nb-wrangler/sample-specs/roman-20.0.0.yaml.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/temps/roman-20.0.0.yaml.
INFO: 00:00:00.063 Running step _initialize_environment.
INFO: 00:00:00.009 Creating environment: roman-cal
INFO: 00:00:19.356 Environment roman-cal created. It needs to be registered before JupyterLab will display it as an option.
INFO: 00:00:00.379 Registered environment roman-cal as a jupyter kernel making it visible to JupyterLab as 'Roman Research Nexus'.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/mm/envs/roman-cal/roman-20.0.0.yaml.
INFO: 00:00:00.066 Running step _install_packages.
INFO: 00:00:00.000 Installing packages from: ['/home/ai/.nbw-live/temps/roman-20.0.0-roman-cal-pip.txt']
INFO: 00:00:21.266 Package installation for roman-cal completed successfully.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/mm/envs/roman-cal/roman-20.0.0.yaml.
INFO: 00:00:00.057 Running step _save_final_spec.
INFO: 00:00:00.000 Saving spec file to /home/ai/nb-wrangler/sample-specs/roman-20.0.0.yaml.
INFO: 00:00:00.058 Saving spec file to /home/ai/.nbw-pantry/shelves/roman-20.0.0-roman-cal/nbw-wranger-spec.yaml.
INFO: 00:00:00.063 Workflow spec development / curation completed.
INFO: 00:00:00.000 Running any explicitly selected steps.
INFO: 00:00:00.000 Exceptions: 0
INFO: 00:00:00.000 Errors: 0
INFO: 00:00:00.000 Warnings: 0
INFO: 00:00:00.000 Elapsed: 00:00:43
```

to download repos, scrape requirements, and build the corresponding environment. As part of this
curation run, nb-wrangler adds or updates the `out` section of the wrangler spec with the results
of the curation such as the notebooks found, imports to be tested, complete list of pip dependencies,
etc.  This extra information can then be used to re-install exactly the same environment later
without the risk of recomputing something different.


As a quick check on the built environment you can try out the notebook imports with `--test-imports`:

```sh
./nb-wrangler sample-specs/roman-20.0.0.yaml --test-imports

INFO: 00:00:00.000 Loading and validating spec sample-specs/roman-20.0.0.yaml
INFO: 00:00:00.037 Running any explicitly selected steps.
INFO: 00:00:00.000 Running step _test_imports
INFO: 00:00:00.000 Testing imports by notebook for 7 notebooks...
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/pandeia/pandeia.ipynb.
INFO: 00:00:00.000 Testing 3 imports
INFO: 00:00:00.245 Import of numpy succeeded.
INFO: 00:00:00.061 Import of pandeia succeeded.
INFO: 00:00:00.147 Import of scipy succeeded.
INFO: 00:00:00.000 All imports succeeded.
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/rist/rist.ipynb.
INFO: 00:00:00.000 Testing 1 imports
INFO: 00:00:01.883 Import of plot_rist succeeded.
INFO: 00:00:00.000 All imports succeeded.
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/roman_cutouts/roman_cutouts.ipynb.
INFO: 00:00:00.000 Testing 8 imports
INFO: 00:00:00.317 Import of asdf succeeded.
INFO: 00:00:02.777 Import of astrocut succeeded.
INFO: 00:00:00.185 Import of astropy succeeded.
INFO: 00:00:00.211 Import of matplotlib succeeded.
INFO: 00:00:00.121 Import of numpy succeeded.
INFO: 00:00:01.304 Import of roman_datamodels succeeded.
INFO: 00:00:00.355 Import of s3fs succeeded.
INFO: 00:00:00.049 Import of warnings succeeded.
INFO: 00:00:00.000 All imports succeeded.
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/romanisim/romanisim.ipynb.
INFO: 00:00:00.000 Testing 15 imports
INFO: 00:00:00.057 Import of argparse succeeded.
INFO: 00:00:00.252 Import of asdf succeeded.
INFO: 00:00:00.196 Import of astropy succeeded.
INFO: 00:00:00.189 Import of astroquery succeeded.
ERROR: 00:00:00.048 Failed to import dask:Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'dask' ::: 
INFO: 00:00:00.058 Import of dataclasses succeeded.
INFO: 00:00:00.780 Import of galsim succeeded.
INFO: 00:00:00.051 Import of importlib succeeded.
INFO: 00:00:00.213 Import of matplotlib succeeded.
INFO: 00:00:00.123 Import of numpy succeeded.
INFO: 00:00:01.857 Import of pysiaf succeeded.
INFO: 00:00:01.134 Import of roman_datamodels succeeded.
INFO: 00:00:00.103 Import of romanisim succeeded.
INFO: 00:00:00.355 Import of s3fs succeeded.
INFO: 00:00:00.057 Import of typing succeeded.
ERROR: 00:00:00.000 Failed to import 1: ['dask']
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/stpsf/stpsf.ipynb.
INFO: 00:00:00.000 Testing 4 imports
INFO: 00:00:00.184 Import of astropy succeeded.
INFO: 00:00:00.214 Import of matplotlib succeeded.
INFO: 00:00:00.122 Import of numpy succeeded.
INFO: 00:00:02.650 Import of stpsf succeeded.
INFO: 00:00:00.000 All imports succeeded.
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/synphot/synphot.ipynb.
INFO: 00:00:00.000 Testing 6 imports
INFO: 00:00:00.184 Import of astropy succeeded.
INFO: 00:00:00.217 Import of matplotlib succeeded.
INFO: 00:00:00.120 Import of numpy succeeded.
INFO: 00:00:01.765 Import of stpsf succeeded.
INFO: 00:00:00.844 Import of stsynphot succeeded.
INFO: 00:00:00.830 Import of synphot succeeded.
INFO: 00:00:00.000 All imports succeeded.
INFO: 00:00:00.000 Testing imports for references/roman_notebooks/notebooks/time_domain_simulations/time_domain_simulations.ipynb.
INFO: 00:00:00.000 Testing 18 imports
INFO: 00:00:00.059 Import of argparse succeeded.
INFO: 00:00:00.253 Import of asdf succeeded.
INFO: 00:00:01.202 Import of astrocut succeeded.
INFO: 00:00:00.189 Import of astropy succeeded.
INFO: 00:00:00.063 Import of dataclasses succeeded.
INFO: 00:00:00.576 Import of galsim succeeded.
INFO: 00:00:00.055 Import of glob succeeded.
INFO: 00:00:00.048 Import of importlib succeeded.
INFO: 00:00:00.215 Import of matplotlib succeeded.
INFO: 00:00:00.123 Import of numpy succeeded.
INFO: 00:00:01.181 Import of pysiaf succeeded.
INFO: 00:00:01.096 Import of roman_datamodels succeeded.
INFO: 00:00:00.096 Import of romancal succeeded.
INFO: 00:00:00.090 Import of romanisim succeeded.
INFO: 00:00:00.052 Import of shutil succeeded.
INFO: 00:00:01.063 Import of sncosmo succeeded.
INFO: 00:00:00.060 Import of typing succeeded.
INFO: 00:00:00.047 Import of warnings succeeded.
INFO: 00:00:00.000 All imports succeeded.
ERROR: 00:00:00.000 FAILED step _test_imports ... stopping...
INFO: 00:00:00.000 Exceptions: 0
INFO: 00:00:00.000 Errors: 3
INFO: 00:00:00.000 Warnings: 0
INFO: 00:00:00.000 Elapsed: 00:00:26
```

**NOTE:** the above import test shows a failure where checking imports discovers
in 26 seconds that the environment does not support `dask` so there is still more
work to do with  notebook and/or spec curation.

Note that sometimes notebooks require data to run successfully so you may also 
need to `--data-reinstall` before you can successfully `--test-notebooks`.

Once the environment is built successfully and any required data is installed,
you can automatically run all of the notebooks headlessly with:

```sh
./nb-wrangler fnc-test-spec.yaml --test-notebooks
INFO: 00:00:00.000 Loading and validating spec /home/ai/nb-wrangler/fnc-test-spec.yaml
INFO: 00:00:00.032 Running any explicitly selected steps.
INFO: 00:00:00.000 Running step _test_notebooks
INFO: 00:00:00.000 Filtered notebook list to 8 entries
INFO: 00:00:00.000 Testing 8 notebooks with 4 jobs
*********** Testing 'identifying_transiting_planet_signals.ipynb' on environment 'tess' ************
Input Notebook:  identifying_transiting_planet_signals.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
*************** Tested identifying_transiting_planet_signals.ipynb OK 0:00:45.259911 ***************
*********** Testing 'instrumental_noise_4_electronic_noise.ipynb' on environment 'tess' ************
Input Notebook:  instrumental_noise_4_electronic_noise.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
*************** Tested instrumental_noise_4_electronic_noise.ipynb OK 0:00:13.091890 ***************
******************* Testing 'beginner_how_to_use_lc.ipynb' on environment 'tess' *******************
Input Notebook:  beginner_how_to_use_lc.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
********************** Tested beginner_how_to_use_lc.ipynb OK 0:00:04.365442 ***********************
******************** Testing 'beginner_tour_lc_tp.ipynb' on environment 'tess' *********************
Input Notebook:  beginner_tour_lc_tp.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
************************ Tested beginner_tour_lc_tp.ipynb OK 0:00:07.977189 ************************
************************ Testing 'data-access.ipynb' on environment 'tess' *************************
Input Notebook:  data-access.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
**************************** Tested data-access.ipynb OK 0:00:08.415362 ****************************
*********************** Testing 'lcviz_tutorial.ipynb' on environment 'tess' ***********************
Input Notebook:  lcviz_tutorial.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
************************** Tested lcviz_tutorial.ipynb OK 0:00:15.030356 ***************************
**************************** Testing 'tglc.ipynb' on environment 'tess' ****************************
Input Notebook:  tglc.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
******************************* Tested tglc.ipynb OK 0:00:06.194112 ********************************
***************** Testing 'zooniverse_view_lightcurve.ipynb' on environment 'tess' *****************
Input Notebook:  zooniverse_view_lightcurve.ipynb
Output Notebook: test.ipynb
Executing notebook with kernel: tess
******************** Tested zooniverse_view_lightcurve.ipynb OK 0:00:09.276549 *********************
INFO: 00:00:45.270 All notebooks passed tests
INFO: 00:00:00.000 Exceptions: 0
INFO: 00:00:00.000 Errors: 0
INFO: 00:00:00.000 Warnings: 0
INFO: 00:00:00.000 Elapsed: 00:00:45
```

### Running specific notebooks

The `--test-notebooks` flag (and consequently `-t`, `--test-all`, and `--test-imports`) now supports an optional regular expression argument to select a subset of notebooks for testing. This is useful for focusing on specific notebooks during development or debugging.

For example, to run all notebooks with "tess" in their name:

```sh
./nb-wrangler fnc-test-spec.yaml --test-notebooks ".*tess.*"
```

To test imports only for notebooks with "roman" in their path:

```sh
./nb-wrangler sample-specs/roman-20.0.0.yaml --test-imports ".*roman.*"
```

## Advanced Environments

There are multiple methods of defining the Python environment which collectively use a combination of
inputs from the spec and network resources.

### Overall Approach

nb-wrangler mimics the approach taken by STSCI's notebook repositories in general, and to that end it
tends to minimize the mamba environment and emphasize usage of pip packages wherever possible. No approach
is perfect but this one tends to provide the timeliest access to new packages and the most flexibility
in how notebooks can be run.  Indeed, individual notebooks commonly run after specifying solely their
required pip requirements.txt file making them suitable for both mamba and Python virtual environments. 
One of the fundamental tasks of the wrangler however is to resolve common environments capable of running
entire sets of notebooks, and in particular, capable or running those notebooks on STSCI's JupyterHub
science platforms.

Our original bias for which packages to install with mamba can be summed up as:  (1) Python itself 
(2) Python build tools (3) non-Python libraries and tools (4) uv/pip and the wrangler and dependencies.
In a perfect world,  everything else should be installed using a variation of pip.

### Base Environment Paradigms

`nb-wrangler` provides multiple methods for defining the base software environment. These are broadly divided into a **Simple Definition** for `pip`-centric projects and **Advanced Definitions** for projects requiring precise control over the Mamba environment.

#### Method 1: Simple Definition (Implied Spec)

This is the standard and most straightforward method. You specify a `python_version` and a `kernel_name` in the spec's header. `nb-wrangler` uses this to create a minimal Mamba environment containing Python and other core packages like `uv` and `pip`.

**Example:**
```yaml
image_spec_header:
  kernel_name: my-simple-env
  display_name: "My Simple Environment"
  python_version: "3.11"
# ... rest of spec
# MUST NOT specify top-level `environment_spec` or have a second YAML document.
```

#### Advanced Definitions

For more complex environments, you can provide a complete Mamba environment specification using one of the following mutually exclusive methods. In all advanced methods, `python_version` and `kernel_name` must be omitted from the wrangler spec header.

##### Method 2: Inline Spec (via Concatenated File)

Your spec file can contain two separate YAML documents, separated by `---`. This is useful for quickly embedding an existing `environment.yml` file directly into your wrangler spec without needing to fix indentation.

**Rules:**
1.  The `nb-wrangler` spec (the first document) **must not** contain `python_version` or `kernel_name`. It may optionally provide a `display_name`.
2.  The Mamba spec (the second document) **must** contain a `name` field. This will be used as the environment's kernel name.

**Example `my-spec.yaml`:**
```yaml
image_spec_header:
  image_name: "My Inlined Env"
  description: "An environment defined by an inline Mamba spec."
  display_name: "My Inline Environment"  # Optional, defaults to the mamba name
# ... other wrangler spec fields ...
---
name: my-inline-env
channels:
  - conda-forge
dependencies:
  - python=3.10
  - numpy
  - pip:
    - rich
```

##### Method 3 & 4: External Spec (via `environment_spec` field)

This approach uses the `environment_spec` field to point to an externally defined Mamba environment file. This is the most powerful method for reusing shared, version-controlled environments.

**Rules:**
1.  The `nb-wrangler` spec **must not** contain `python_version` or `kernel_name`. It may optionally provide a `display_name`.
2.  The Mamba spec referenced externally **must** contain a `name` field.

**A) By URI (URL or Local File)**

You can point to a network URI or a local file path.

**Example:**
```yaml
image_spec_header:
  display_name: "My External Environment"
# ...
environment_spec:
  uri: https://raw.githubusercontent.com/my-org/my-repo/main/environment.yml
```
You can also use a local file path, which is resolved relative to the location of the wrangler spec file.

> **Warning:** Using a local file path (`uri: ../my-env.yml`) is convenient for development but makes your spec non-portable. For any spec that will be shared or version-controlled, using a **URL** or **Repository Path** is the recommended best practice.

**B) By Repository Path**

You can point to a file within a git repository that is already listed in the top-level `repositories` block of your spec.

**Example:**
```yaml
repositories:
  my-notebook-repo:
    url: https://github.com/my-org/my-notebooks.git
    ref: main
# ...
image_spec_header:
  display_name: "My Repo Environment"
# ...
environment_spec:
  repo: my-notebook-repo
  path: environment.yml
```

### Notebook Repo Requirements.txt

Each notebook directory is permitted to define it's own  `requirements.txt`
file to define pip dependencies which will nominally be resolved and downloaded in aggregate (all notebook
requirements combined) by `uv pip install`. As-of this writing `uv pip install` results in much improved 
version resolution and download times, as well as high quality version resolution feedback which is critical
for resolving any difficult package conflicts which result from combining requirements sources.

### Inlined extra_mamba_packages

It is possible to add a list of extra mamba packages directly to the wrangler spec as `extra_mamba_packages`
and these will be added to the environment by mamba in addition to those specified in the base mamba spec.

### Inlined common_mamba_packages

Likewise, `common_mamba_packages` allows you to specify mamba packages that should be installed in both your curated environment and the science platform's base environment (when using SPI injection).

### Inlined extra_pip_packages

Likewise it is possible to inline extra pip packages by adding `extra_pip_packages` to the wrangler spec and
these will nominally be added by `uv pip` in addition to those specified by the base mamba spec and/or
requirements.txt files.

### Inlined common_pip_packages

Similarly, `common_pip_packages` specifies pip packages that should be installed in both your curated environment and the science platform's base environment.

### Notebook Repo Helper Modules

Lastly,  it's possible for each notebook directory to define local `.py` helper modules directly although
this is not particularly recommended.  By convention,  a top level `shared` directory can also be used to 
store globally available helper modules,  but with the expectation that any notebook importing them will
symlink from the notebook directory (where it is expected to run) to the globally shared file.

### SPI (science-platform-images) Packages

As a final note,  the science platforms impose common requirements in the form of mamba and pip packages which
are collected from selected directories on https://github.com/spacetelescope/science-platform-images.
These help support the standard lab environment and platform extensions,  and while it is possible to opt out
using --packages-omit-spi (both mamba and pip are ommitted), this will most likely result in divergence from
standard science platform behavior and/or

## Notebook and Environment Reinstallation

At some later time and/or different location you can re-install a wrangler spec which was developed
using `--curate` as follows:

```sh
./nb-wrangler fnc-test-spec.yaml --reinstall
INFO: 00:00:00.000 Loading and validating spec /home/ai/nb-wrangler/fnc-test-spec.yaml
INFO: 00:00:00.038 Running workflows ['reinstall'].
INFO: 00:00:00.000 Running install-compiled-spec workflow
INFO: 00:00:00.000 Running step _validate_spec.
INFO: 00:00:00.029 Running step _spec_add.
INFO: 00:00:00.000 Running step _initialize_environment.
INFO: 00:00:00.010 Creating environment: tess
INFO: 00:00:07.306 Environment tess created. It needs to be registered before JupyterLab will display it as an option.
INFO: 00:00:00.412 Registered environment tess as a jupyter kernel making it visible to JupyterLab as 'TESS'.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/mm/envs/tess/fnc-test-spec.yaml.
INFO: 00:00:00.065 Running step _install_packages.
INFO: 00:00:00.000 Installing packages from: ['/home/ai/.nbw-live/temps/tike-2025.07-beta-tess-pip.txt']
INFO: 00:00:02.211 Package installation for tess completed successfully.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/mm/envs/tess/fnc-test-spec.yaml.
INFO: 00:00:00.054 Workflow install-compiled-spec completed.
INFO: 00:00:00.000 Running any explicitly selected steps.
INFO: 00:00:00.000 Exceptions: 0
INFO: 00:00:00.000 Errors: 0
INFO: 00:00:00.000 Warnings: 0
INFO: 00:00:00.000 Elapsed: 00:00:10
```

As above with `--curate`  after `--reinstall` you should execute `--test-imports` to make sure the environment and
notebooks are working correctly.  Note that sometimes notebooks require data to run successfully so you may also 
need to `--data-reinstall` before you can successfully `--test-notebooks`.

## Other Curation Tips and Tricks

### Setting key nb-wrangler environment variables

During development,  your best chances of using nb-wrangler successfully are to create a fully
independent wrangler environment whereever you want to work,  it could be your laptop:

#### Laptop Env settings

```
# no changes needed,  nb-wrangler installs under $HOME in hidden .nbw-live and .nbw-pantry
# directories
```

#### Science Platform Env Settings

Another (potentially better) option could be on a science platform in an OPS or TEST environment
working solo from your personal $HOME directory:

```
export NBW_ROOT="/tmp/nbw-live"
export NBW_PANTRY="$HOME/.nbw-pantry"
```

**TIP:** Add env vars to .bashrc and .bash_profile to make sure they are always added to any new shells.

Note that the entire distinction between ROOT and PANTRY has to do with the underlying
performance and persistence of the associated storage.  The above setup is intended so
that NBW_ROOT is fast but not persistent, while NBW_PANTRY is persistent and unfortunately
slow as a consequence.  (Persistence refers to "not forgotten between notebook sessions
on the science platform."  Nevertheless, maye require unpacking to restore )

### Wrangling with custom tools

If you prefer not to use **micromamba** for setting up the base environment and **uv pip** for `pip` installs,
you can override these tools and fall back to the standard `mamba` and `pip`, which are sufficiently compatible
for the limited wrangler use‑cases.

To configure **nb‑wrangler** to use `mamba` and `pip` instead of `micromamba` and `uv pip`, set the following environment variables:

```sh docs/notebooks_and_environment.md
export NBW_MAMBA_CMD="mamba"
export NBW_PIP_CMD="pip"
```

*While untested, swapping either tool independently should also work.*

The configuration above has been used in production at STScI to install **nb-wrangler** into an existing `mamba` environment and to rely solely on `pip` as the package manager—avoiding a mixed setup of `pip` + `uv pip` (which is anecdotally discouraged) and a mix of `micromamba` + `mamba`.  Stick to one toolchain or the other,  and this really applies to default development IF you choose to start installing packages manually vs. using nb-wrangler.

That said, **micromamba** and **uv pip** are the default choices for wrangler development. They provide major benefits in terms of speed for dependency‑constraint resolution and package installation, making local development a much more pleasant experience.


### Bootstrapping

After setting env vars as above, See [README.md](../README.md) for instructions on bootstrapping
the nb-wrangler software. This will install a micromamba and an nbwrangler environment in a standalone
configuration isolated from any other Python environments you may have.


### Failures and Process Iteration

If you encounter errors in the test phase and need to circle back to
earlier steps,  depending on what work needs to be repeated,  you may
need to `--reset-curation` to remove artifacts of earlier runs which
would otherwise short circuit the required repeat work as "already performed".

Environment curation can be reset like this:

```sh
nb-wrangler spec.yaml --reset-curation [--delete-repos]
```

This results in resetting the spec, deleting the environment, clearing package
caches, and any other required cleanup needed before resuming curation of
modified inputs.  Removing the repos is optional but the simplest way to
get a robust update of upstream changes.

### Environment Cleanup

The `--env-kernel-cleanup` flag scans the user's Jupyter kernel registry for "dead" kernels—those pointing to non-existent environments—and removes them. This helps maintain a clean and functional Jupyter environment.

```sh
./nb-wrangler my-spec.yaml --env-kernel-cleanup
```

