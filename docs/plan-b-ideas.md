# Plab B Overview

Plan B is a system designed to leverage the difference in performance between container
storage and EFS in order to support software environments that are relatively fast to
install or re-install.  To achieve this Plan B uses (container storage) and persistent (EFS).

1. Command to install wrangler spec as live environment and persist to designated pantry.

nb-wrangler nbw-wrangler-spec.yaml --reinstall --env-pack
nb-wrangler nbw-wrangler-spec.yaml --data-install  (optional if shared data available? tricky)

2. Command to uninstall live environment to release container space.

nb-wrangler nbw-wrangler-spec.yaml --env-delete

3. Command to restore archived environment to live status.

nbw-wrangler nbw-wrangler-spec.yaml --env-unpack

4. Command to delete environment archive to release archive space.

(nbw-wrangler nbw-wrangler-spec.yaml --env-archive-delete)

5. Investigate mamba/micromamba environment bundling commands as alternative to less formal
archives created with tar.   If Plan B is robust on the platform and using mamba unpacking
commands results in performance loss,  keep informal tar archives for the platform at a minimum.

6. Notation for referring to specs whether "wild" or archived., including globbing or regex.

For regex/glob searches use nbw://(pattern)
For https use https://...
For file use <local path>
For registry use nbw-

7. Integration with wrangler data management so activated data tracks activated environment.
Verify terminal environment and disposition of refdata environment variable.

8. Ability to support user, team, and mission level installations with progressively more
isolation from unprivileged users.  Propose NBW_PATH which points to pantry-1:pantry-2:pantry-3...

9. Barebones generic JupyterLab image.  Propose clean break from science-platform-images with
goals of minimal size and simplicity.  Using jupyter/docker-stacks to track community development
is optional since it adds complexity and pre-adds many packages.

10. Set NBW_SPEC from spawner profile and "activate" the selected shared env during post-start-hook.

11.  Fancy in-session environment activation/deactivation/status
11a. Environment library lab extension
11b. Environment library service to activate/deactivate environments on platform.

12. Image registry repo interactions
12a. Scrape notebook images and spec images from registries
12b. Support a ":" separated PATH-like list of regitries
12c. Select images from available lists using regex matching / globbing;  work out clean notation to DWIM.
     Look for compatability / similarity to Spawner dynamic ECR image selection.
12d. Support extracting image plain-text spec from degenerate image spec images
12e. Support querying selected image specs using yq notations
12f. Support pulling and running selected notebook image.
12g. Provide spawner with interfaces to scrape, pull, filter by date, extract spawner image name from docker name.
12h. Integrate selected spec names with other wrangler operations where it makes sense,  e.g. --reinstall.


# Plan D

Plan D is a hybrid concept which relies on automatically curating or re-installing spec'd environments
at startup vs. the original concept of libraries of archived environments and data.

The key aspect of Plan D, conceptually, is moving the "curation pipeline" inside the hub post-start-hook
enabling users and curators to curate new specs and environments simply by selecting and wrangler spec
(on the spawn page) + check-box indicating curation or re-install.

Among the benefits proposed here is moving all of the complexity of running nb-wrangler outside the scope
of notebook testers eliminating training and tooling issues. This is an identical win to the GitHub curation
pipeline but with a simpler and more localized pipeline.  The scheme drops all complexity associated with 
the GitHub pipeline, GHCR, image scanning, ECR, and inlined perpetually failing notebook tests. It improves
or maintains spawn times by replacing copies of huge images with runtime environment curation or unpacking.
It replaces ~1 hour pipelined image builds with ~5-10 min re-spawns and dynamic env installation.

Potentially this frees Octarine from mid-to-late-game image builds where notebook curators need to iterate
with small environment changes rapidly but when environments are nevertheless fairly stable and almost always
build successfully even if they cannot yet support all notebooks.

Loose ends:
a. How does a curator choose a wrangler spec. Ans: spawner image selection replaced by spec selection.
   Latest spec scraped from GitHib repo which tracks specs for each build on dedicated branches.
b. What happens when a spec curation fails? (Need solid solution for reporting build log)
c. How do curators iterate? 1. modify spec on GitHub branch.  2. select spec and re-spawn.
d. How do finalized curated specs get uploaded to GitHub for permanant reference + re-installs?
e. How do we manage prod vs. test specs?   Maintain prod branch on GitHub.
f. How many GitHub repos do we need for all missions?  One. Use either deployment branches or directories
   for each notebook_repo we're supporting. Each site chooses portions of GitHub it wants to publish.

