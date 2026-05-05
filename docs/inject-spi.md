# Science Platform Images (SPI) Injection

> **Note:** SPI Injection is a manual fallback or debugging mechanism. The standard workflow is the fully [Automated Image Pipeline](automated_image_pipeline.md), which handles injection as part of its execution.

## Overview

Science Platform Images (SPI) Injection is a semi-automated workflow that enables extracting portions of a wrangler spec and applying them to the appropriate locations within the science platform images repository to define a corresponding image build.

Unlike traditional "wrangler" image builds, which are fully automated and managed by a pipeline, SPI Injection stops once `nb-wrangler` has completed a source code update. In essence, SPI Injection mirrors the process of transferring package and notebook requirements from Jira to an SPI repository checkout, allowing for the initiation of an image PR. From this point forward, an SPI Injection build functions as a standard SPI build. Therefore, SPI Injection serves as a fallback mechanism and offers a minor time-saving advantage and reliability boost compared to fully manual Jira based builds. Also, because the procedural aspects of the build process are unchanged,  and because very little or no other code needs to change, using SPI injection and classic builds significantly lowers risk compared to new wrangler builds.

## Prerequisites

To perform SPI Injection, you will need:

1. An installation of `nb-wrangler`.
2. A complete `nb-wrangler` spec for the desired SPI image.

Additionally, for practical application, you will need:

3. Familiarity with Docker and GitHub workflows, including installations of both Docker and Git.
4. Knowledge of how to configure and perform a standard SPI build.
5. Access to an image repository (typically ECR) to push the final built image.
6. Access to the `science-platform-images` repository on GitHub to create pull requests for your build changes.

## Example SPI Injection Workflow

The base injection command is straightforward:

```bash
$ nb-wrangler --clone --repos-dir spi-references --inject-spi sample-specs/tike-2025-07-beta.yaml
INFO: 00:00:00.000 Loading and validating spec /home/ai/nb-wrangler/sample-specs/tike-2025-07-beta.yaml
INFO: 00:00:00.035 Running explicitly selected steps, if any.
INFO: 00:00:00.000 Running step _clone_repos
INFO: 00:00:00.000 Setting up repository clones.
INFO: 00:00:00.000 Cloning repository https://github.com/jaytmiller/science-platform-images.git to spi-references/science-platform-images.
INFO: 00:00:01.435 Successfully cloned repository to spi-references/science-platform-images.
INFO: 00:00:00.000 Cloning --single-branch repository https://github.com/spacetelescope/mast_notebooks to spi-references/mast_notebooks.
INFO: 00:00:04.199 Successfully cloned repository to spi-references/mast_notebooks.
INFO: 00:00:00.000 Cloning --single-branch repository https://github.com/spacetelescope/tike_content to spi-references/tike_content.
INFO: 00:00:01.493 Successfully cloned repository to spi-references/tike_content.
INFO: 00:00:00.003 Found 8 notebooks in all notebook repositories.
INFO: 00:00:00.000 Processing 8 unique notebooks for imports.
INFO: 00:00:00.001 Extracted 7 package imports from 8 notebooks.
INFO: 00:00:00.000 Revising spec file /home/ai/nb-wrangler/sample-specs/tike-2025-07-beta.yaml.
INFO: 00:00:00.000 Saving spec file to /home/ai/.nbw-live/temps/tike-2025-07-beta.yaml.
INFO: 00:00:00.057 Running step inject
INFO: 00:00:00.000 Initiating SPI injection into spi-references/science-platform-images for tike kernel tess...
INFO: 00:00:00.000 Injecting field test_imports to spi-references/science-platform-images/deployments/tike/environments/tess/tests/imports
INFO: 00:00:00.000 Injecting field mamba_spec to spi-references/science-platform-images/deployments/tike/environments/tess/tess.yml
INFO: 00:00:00.000 Injecting field pip_compiler_output to spi-references/science-platform-images/deployments/tike/environments/tess/tess.pip
INFO: 00:00:00.000 Injecting field None to spi-references/science-platform-images/deployments/tike/environments/common-hints.mamba
INFO: 00:00:00.000 Injecting field None to spi-references/science-platform-images/deployments/tike/environments/common-hints.pip
INFO: 00:00:00.000 Saving spec file to spi-references/science-platform-images/deployments/tike/environments/nbw-wrangler-spec.yaml.
INFO: 00:00:00.055 SPI injection complete.
INFO: 00:00:00.000 Exceptions: 0
INFO: 00:00:00.000 Errors: 0
INFO: 00:00:00.000 Warnings: 0
INFO: 00:00:00.000 Elapsed: 00:00:07
```

**Automated SPI Injection Workflow**

To fully automate the SPI injection process, including pushing changes and creating a Pull Request on GitHub, you can use the `--spi-push` and `--spi-pr` flags:

```bash
$ nb-wrangler --clone --repos-dir spi-references --inject-spi sample-specs/tike-2025-07-beta.yaml --spi-push --spi-pr
```

This command will:
1.  Perform the standard SPI injection (as described above).
2.  Create a new Git branch in your local `science-platform-images` repository clone (with an automatically generated name based on the spec moniker).
3.  Commit the injected changes to this new branch (with a default commit message).
4.  Push this new branch to your remote `science-platform-images` repository.
5.  Create a Pull Request on GitHub from this new branch to `origin/main`.

**GitHub Authentication (`gh auth login`)**

To enable `nb-wrangler` to push branches and create Pull Requests on GitHub, you must first authenticate the GitHub CLI (`gh`). You can do this by running:

```bash
gh auth login
```

Follow the prompts to authenticate using your GitHub account. A standard GitHub CLI token will work.

**NOTE:** Because `nb-wrangler` aggressively deletes repository clones, we set `--repos-dir spi-references` to a private, writable path to accommodate the SPI injection updates. Using a custom directory name prevents `nb-wrangler` from attempting to delete it when you perform other unrelated activities.  The default `--repos-dir` is `references` located relative to
whereever you run nb-wrangler.

The final result of the injection is available in the subdirectory `spi-references/science-platform-images`, as demonstrated by the following `git status` output:

```bash
$ cd spi-references/science-platform-images
$ git status
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  modified:  deployments/tike/environments/tess/tess.pip
  modified:  deployments/tike/environments/tess/tess.yml
  modified:  deployments/tike/environments/tess/tests/imports

Untracked files:
  deployments/tike/environments/nbw-wrangler-spec.yaml
  deployments/tike/environments/nbw-exports.sh
  deployments/tike/environments/common-hints.mamba
  deployments/tike/environments/common-hints.pip

no changes added to commit (use "git add" and/or "git commit -a")
```

As shown in the `git status`, the `mamba` (tess.yml) and `pip` (tess.pip) package requirements, and the import tests, have been extracted from the input spec and injected into the declarative section of the TIKE deployment within our science-platform-images clone.  Note that this particular pattern of injection is in the process of being replaced by a more flexible and automated approach based solely on the spec and nb-wrangler vs. classic install scripts.

Additionally, the spec itself has been added to the environments directory under the generic name `nbw-wrangler-spec.yaml`. This file can be used later for wrangler functions such as testing or data installation. In the fully built image, the spec will be located at `/opt/environments/mb-wrangler-spec.yaml`.

Before proceeding, it's recommended to add and commit all changes under `spi-references/science-platform-images/deployments`:

```bash
$ git checkout -b my-spi-branch
$ git add deployments
$ git commit
```

If you have Docker installed, you can proceed directly to a standard local SPI image build:

```bash
$ scripts/image-configure tike
$ source setup-env
$ image-build
```

Like all classic builds, while obtaining a fully built image and environment is the primary task, the specific details of the `post-start-hook` and/or deployment `test` function may require adjustments to accommodate the current set of notebooks, etc. In principle, the wrangler can automate both of these aspects even for classic builds, but this would require incorporating too many common changes from `nb-wrangler`, which would add unnecessary development effort and risk.

## Experimental Features

The following flags are available for advanced users or for testing experimental functionalities. They are not part of the primary SPI injection workflow and their behavior may change in future releases.

*   `--spi-branch <branch-name>`: Allows you to specify the name of the Git branch to create in the `science-platform-images` repository. By default, a branch name is automatically generated.
*   `--spi-commit-message <message>`: Provides a custom commit message for the changes. If not provided, a default message is used.
*   `--spi-build`: Triggers a Docker build in the `science-platform-images` repository after injection and before committing changes. This can be useful for local validation of the generated environment.
*   `--spi-prune`: Prunes old Docker images before a build. This ensures a clean rebuild and can free up disk space.

## Key Differences from True Wrangler Builds

True wrangler builds all share a common `wrangler` deployment and have a very generic Dockerfile.  As-of this writing they have
few customizations other than mamba and pip package selections, notebooks, data, and environment variables. Consequently,  the 
same wrangler deployment can serve many different projects.

### SPI Injection

`SPI Injection`-based builds possess these fundamental characteristics:

1. **Primitive Automation:** The only real automation beyond the original build scripts is limited to populating package requirements and tests defined by a wrangler spec.
2. **Original Dockerfiles:** Images are built using the original mission Dockerfiles, which execute arbitrary actions, including custom library or package builds not readily available from `mamba` or `pip`.
3. **Classic Build Scripts:** Package installation and cleanup are performed using standard build scripts such as `env-conda`, `env-compile`, and `env-sync`.
4. **Manual Configuration:** Manual configuration of `post-start-hook` and tests is required to manage tasks like Git synchronization and notebook test setup.
5. **Manual Image Management:** Manual image build, scanning, tagging, and pushing are necessary.
6. **3+ Kernel Support:** While image size typically prohibits this,  the classic framework was designed to support both base an N-different mission-specific mamba environments.  Even adding it manually, a 3rd kernel will be much easier to do using classic builds than using standard wrangler builds.
7. **Low Risk:** Since these builds are closely aligned with what we've done for years, they are lower risk.
