# Adapting, auditing and maintaining the catalogue

## Adapting

Porting to the other backend: the file sets differ (see the two backend sub-skills) but the
cohort query, model factory, transforms / feature engineering, figures and README substance are
shared. Copy the shared files byte-for-byte, add each pair to `scripts/check_tutorial_sync.sh`
(NVFLARE copy as the reference) and widen the sync workflow's `paths:` if needed; the new copy's
`tutorial.yaml` names the original as `twin`, and the original's gains the new one. Changing the
dataset, job type or loop: re-run the router's §1 for the parts that change (required files,
recipe / template, `has_imaging`, the tier), update the manifest, then every registration in
`registration-checklist.md` that named the old value (the Flower `case` entry, `APPS`,
`DICOM_APPS`, the e2e target, the docs catalogue line's job type).

## Auditing

Run `make -C fl-tutorials check-tutorial TUTORIAL=<name>` and read the manifest; its axis values
say which sub-skills explain the warnings. Then compare the README against `readme-shape.md`
(task figure, Expected performance with a reference curve or table, References, video link).
Common drift and where it is pinned:

- a Flower client reading `SUPERNODE_NAME` directly instead of `client_identity(context)` — every
  simulated site gets the whole cohort (FLWR-12, FLWR-13; the EHR Flower client is the known case,
  waived in its manifest until the fix on #1444 lands);
- a README quoting a target the root Makefile does not forward (COMMON-22, DATA-02,
  `test_fl_tutorials_make_targets.py`);
- a tutorial missing from the docs catalogue or the demo recorder's `APPS` (COMMON-18, COMMON-23
  to COMMON-25);
- a `torch.load` without `weights_only=True` (DL-02; `test_offline_apps.py` is authoritative);
- a README with no figure, no Expected performance, no citation (COMMON-19 to COMMON-21);
- a twin pair whose `query.sql` is not pinned in `PAIRS` (COMMON-16).

Fix what is small in place; file the rest; a waiver is for a documented exception with a tracking
reference, never for a gap.

## Maintaining

When something the tutorials depend on changes, this is what moves with it:

| Change | Touches |
|--------|---------|
| flip-utils API (`flip.flower.identity`, the NVFLARE recipes, `FlipConstants`, `flip.FLIP`) | every tutorial importing it; `make -C fl-tutorials test` runs in flip-utils' env so the CPU suite sees it |
| an `fl-apps/flower/<job_type>/app/*.py` template | re-copy into every Flower tutorial of that job type (FLWR-05 / FLWR-06 and the parity test fail until done) |
| an `fl-apps/nvflare/<template>/required_files.json` | every NVFLARE tutorial of that job type must still carry the set (COMMON-03) |
| a new guard in `fl-tutorials/tests/` | the whole catalogue at once; name it in the spec rule's `enforced_by`; `make -C fl-tutorials check-all-tutorials` |
| a new rule or axis value in `fl-tutorials/specs/` | the manifests (`COMMON-01`), the sub-skill that explains it, the router's table (`test_new_tutorial_skill_tree.py` pins all three) |
| UI change (`flip-ui/src/**`) | demo videos go stale, curves and figures do not |
| dataset version bump (`trust/.data_version`) or dataset tooling change | reference numbers and figures may change; re-run the curve / figure scripts |
| a release | pre-release checklist: `run-all-tutorials` on both backends, `check-all-tutorials`, re-record what the table above invalidated |
