---
name: new-tutorial-imaging
description: Loaded by the new-tutorial router for an imaging tutorial — 2-D DICOM through MONAI or 3-D NIfTI converted by XNAT with labels as enrichment — the cohort columns, image access, DICOM_APPS, enrichment, GPU and figure rules behind fl-tutorials/specs/data-imaging.yaml.
user-invocable: false
---

# Imaging tutorials

Imaging cohorts are resolved by **accession**: `query.sql` projects `accession_id` (IMG-01), the
hub's `create_imaging` task makes each trust pull those studies from PACS into XNAT, and the app
fetches them through `flip.get_by_accession_number` (IMG-03) — never from a path. The platform
project is created with imaging **on** (IMG-02); the manifest says `data: imaging_2d` or
`imaging_3d` and `platform.has_imaging: true`. Spec: `fl-tutorials/specs/data-imaging.yaml`.

## Two shapes

**2-D DICOM (`imaging_2d`).** The study arrives as a DICOM series and the app reads it through
MONAI `LoadImaged` (`transforms.py` / `data_utils.py`). Register the app in
`fl-tutorials/tests/tutorial_apps.py` `DICOM_APPS` (IMG-04): the orientation suite then writes
synthetic DICOMs in three encodings through the app's own transform chain and asserts the pixel
orientation. FLIP#821 is why — a README figure stayed upright while the model trained on
transposed images, and only the transform suite caught it. Precedents: `xray_classification`
(both backends), the three Ark+ tutorials. The dev tree mirrors what imaging-api serves: one
directory per accession under `fl-tutorials/data/<dataset>/accession-resources/`.

**3-D NIfTI via XNAT (`imaging_3d`).** XNAT converts the pulled DICOM to NIfTI (dcm2niix) and
the app receives `input_*.nii.gz` per accession; **labels are not in PACS**, they are uploaded to
XNAT as a *data-enrichment* step between the image pull and training (`make -C fl-tutorials
upload-spleen-labels` / `upload-prostate-labels`; the e2e target carries the same step as
`ENRICHMENT_ARGS`, IMG-06, and the demo recorder as `--data-enrichment-cwd/-cmd`), so the app
loads `label_*.nii.gz` beside the input. Multi-series studies (prostate: T2W + ADC + HBV, two
label sets, an nnU-Net plan) extend the same layout. 3-D apps are deliberately **not** in
`DICOM_APPS` (IMG-11). Precedents: `3d_spleen_segmentation` (both backends),
`3d_prostate_segmentation` (Flower), `latent_diffusion_model` (two-stage, NVFLARE). The dev tree is
`fl-tutorials/data/<dataset>/images/<accession>/` with the NIfTI pairs.

## Rules and traps

- **GPU.** Imaging training is a GPU job; the manifest says `simulator: {device: gpu}` (IMG-07).
  Flower takes `SIM_NUM_GPUS`; prostate documents `SIM_NUM_GPUS=0` as a debugging mode, not the
  path. CI never runs these simulators, so say which of check / test / simulator you ran.
- **Per-site data under the simulator.** NVFLARE `.env.app` sets `DEV_IMAGES_DIR` (or
  `SITE{N}_IMAGES_DIR`, IMG-05); Flower's `sim-tutorial.sh` case exports `DEV_IMAGES_DIR` and the
  ClientApp slices the shared dataframe with `partition_cohort` keyed on `accession_id`, then
  `check_splits_are_populated` before touching images.
- **Image cache scope.** Each FL client sees only its own `net-N` slice of the trust's image cache;
  nothing in app code may assume another net's studies are present.
- **has_imaging and the e2e / demo wiring.** The e2e target runs the image pull and (3-D) the
  enrichment step; the demo profile keeps imaging on so the XNAT/OHIF segment is recorded (IMG-09),
  and segmentation profiles add `--publish-segmentations` for the DICOM-SEG overlay beat.
- **The figure.** Inputs per class for classification; a slice with its label mask or the model's
  prediction for segmentation (prostate: a T2W slice with gland and zonal masks). When the script
  reads pixels through pydicom / nibabel rather than the app's transform chain, say so in the
  docstring and the README — it is a picture of the data, not of the model's input (IMG-10).
- **Enrichment in the README.** A 3-D training README quotes the label-upload target and says it
  runs between the image pull and training on the platform (IMG-08).
- **Cohort size.** The trust's disclosure floor counts distinct subjects; a study-per-row cohort
  with ten X-rays per patient still needs ten *patients*. Project `person_id` too (COMMON-10) so
  the count does not have to be resolved through `image_occurrence`.

## Nearest tutorials to copy

| Shape | NVFLARE | Flower |
|-------|---------|--------|
| 2-D DICOM classification | `image_classification/xray_classification` | `xray_classification` |
| 2-D fine-tune / evaluation | `image_classification/arkplus_fine_tuning`, `image_evaluation/arkplus_*` | — |
| 3-D segmentation + enrichment | `image_segmentation/3d_spleen_segmentation` | `3d_spleen_segmentation`; `3d_prostate_segmentation` (multi-series) |
| 3-D evaluation | `image_evaluation/3d_spleen_segmentation_evaluation` | `3d_spleen_segmentation_evaluation` |

Spec: `fl-tutorials/specs/data-imaging.yaml` (IMG-01 to IMG-11).
