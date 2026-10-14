# Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""XNAT Container Service command: convert an OHIF DICOM-SEG assessor to NIfTI and upload it back.

Launched by the site-wide ImageAssessorEvent subscription that configure-export-mask.sh registers
(MONAI Label trusts only). The Container Service mounts the assessor's SEG resource at --input and
injects XNAT_HOST / XNAT_USER / XNAT_PASS for the user the command runs as. Each DICOM-SEG becomes a
`.nii.gz` beside it in the assessor's SEG resource, resampled onto the session's NIfTI scan when
there is exactly one, so the mask lines up voxel for voxel with the image FL training reads.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import highdicom as hd
import numpy as np
import SimpleITK as sitk
from pyxnat import Interface


def dicom_seg_to_nifti(dicom_seg: Path, output: Path) -> None:
    """Write one DICOM-SEG as a multi-class label image (0 = background, n = segment n).

    highdicom returns the labels with an affine from array indices to patient (LPS) millimetres;
    SimpleITK indexes the same array as (x, y, z) = (axis 2, axis 1, axis 0), so its spacing,
    direction and origin are read off the affine's columns in that order.
    """
    volume = hd.seg.segread(dicom_seg).get_volume(combine_segments=True, dtype=np.uint8)
    axes = volume.affine[:3, [2, 1, 0]]
    spacing = np.linalg.norm(axes, axis=0)
    image = sitk.GetImageFromArray(volume.array)
    image.SetSpacing(spacing.tolist())
    image.SetDirection((axes / spacing).flatten().tolist())
    image.SetOrigin(volume.affine[:3, 3].tolist())
    sitk.WriteImage(image, str(output), True)


def resample_to_reference(mask: Path, reference: Path) -> None:
    """Resample ``mask`` in place onto ``reference``'s grid; nearest neighbour keeps labels integral."""
    resampled = sitk.Resample(
        sitk.ReadImage(str(mask)), sitk.ReadImage(str(reference)), sitk.Transform(), sitk.sitkNearestNeighbor, 0
    )
    sitk.WriteImage(resampled, str(mask), True)


def connect() -> Interface:
    return Interface(server=os.environ["XNAT_HOST"], user=os.environ["XNAT_USER"], password=os.environ["XNAT_PASS"])


def find_reference_nifti(xnat: Interface, project: str, experiment: str, workdir: Path) -> Path | None:
    """Download the session's NIfTI scan, or return None when there is not exactly one candidate.

    The OHIF mask covers one series, so with several scans the right reference is ambiguous; the
    mask is then kept in the DICOM-SEG's own geometry rather than resampled onto a guess.
    """
    session = xnat.select.project(project).experiment(experiment)
    scans = session.scans().get()
    if len(scans) != 1:
        print(f"Not resampling: expected exactly one scan in {experiment}, found {len(scans)}.")
        return None
    resource = session.scan(scans[0]).resource("NIFTI")
    files = resource.files().get()
    if len(files) != 1:
        print(f"Not resampling: expected exactly one NIFTI file on scan {scans[0]}, found {len(files)}.")
        return None
    path = workdir / files[0]
    resource.file(files[0]).get(str(path))
    return path


def upload(xnat: Interface, project: str, experiment: str, assessor: str, nifti: Path) -> None:
    xnat_file = xnat.select.project(project).experiment(experiment).assessor(assessor).resource("SEG").file(nifti.name)
    if xnat_file.exists():
        # Never overwrite: replacing a mask is a deliberate delete on XNAT, not a side effect of a re-run.
        print(f"Not uploading {nifti.name}: already on assessor {assessor}.")
        return
    xnat_file.put(str(nifti))
    print(f"Uploaded {nifti.name} to assessor {assessor}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-i", "--input", required=True, type=Path, help="Mounted SEG resource of the assessor")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Mounted output directory")
    parser.add_argument("--project", required=True, help="XNAT project ID")
    parser.add_argument("--experiment", required=True, help="XNAT session (experiment) ID")
    parser.add_argument("--assessor", required=True, help="XNAT assessor ID")
    args = parser.parse_args(argv)

    seg_files = sorted(args.input.rglob("*.dcm"))
    if not seg_files:
        print(f"No DICOM-SEG (*.dcm) under {args.input}.", file=sys.stderr)
        return 1

    xnat = connect()
    with tempfile.TemporaryDirectory() as workdir:
        reference = find_reference_nifti(xnat, args.project, args.experiment, Path(workdir))
        for seg in seg_files:
            nifti = args.output / seg.with_suffix(".nii.gz").name
            dicom_seg_to_nifti(seg, nifti)
            if reference:
                resample_to_reference(nifti, reference)
            upload(xnat, args.project, args.experiment, args.assessor, nifti)
    return 0


if __name__ == "__main__":
    sys.exit(main())
