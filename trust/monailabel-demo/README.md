# MONAI Label demo video

Records a clinician's path through MONAI Label on a live trust, as an mp4:

1. sign in to the trust's XNAT and open a CT session in the OHIF viewer;
2. switch on MONAI Label (*Options → Preferences → Experimental*, once per browser);
3. run `segmentation_spleen` from the MONAI Label panel on the trust's GPU, and scroll through
   every slice the mask covers;
4. export the mask to XNAT as a DICOM-SEG ROI collection;
5. wait for the `export_mask` Container Service command and show the NIfTI it wrote beside the
   DICOM-SEG.

The recording fails unless step 5 happens, so a finished video is also an end-to-end check of
MONAI Label, the viewer, the export and the converter on that trust.

## Prerequisites

- A trust up with `MONAI_LABEL=true` (see [`trust/README.md`](../README.md#monai-label-optional)),
  with `segmentation_spleen` among `MONAI_LABEL_MODELS`, and `export_mask` registered.
- A spleen CT session with exactly one scan (the spleen tutorial's data), not yet annotated: the
  recorder saves a new ROI collection on it.
- Run it **on the trust host**. The browser runs in a container on the host network and reaches
  XNAT and MONAI Label the way a browser on that host would; MONAI Label's registered URL must
  resolve from there (the default `http://localhost:8030` does).

## Usage

```sh
make -C trust/monailabel-demo demo-video KIT=GSTT XNAT_EXPERIMENT=XNAT_E02217
# -> trust/monailabel-demo/out/monailabel-demo.mp4 (2560x1600; DEMO_VIDEO_SCALE=3 for 4K)
```

It signs in as the kit's `XNAT_ADMIN_USER`. On failure `out/failure.png` shows what the recorder
was looking at.

Frames come from Playwright's screencast and are encoded with ffmpeg (h264 CRF 18) rather than
Playwright's built-in VP8 recorder, which is soft at this resolution.
