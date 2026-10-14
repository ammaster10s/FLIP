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
"""Record the MONAI Label demo: a spleen CT segmented in the XNAT OHIF viewer, then exported for FL.

Drives a live trust (XNAT with the OHIF Viewer plugin, a registered MONAI Label server, export_mask
configured) the way a clinician would, and fails unless export_mask leaves the NIfTI beside the saved
DICOM-SEG, so a finished recording is also an end-to-end check. Run it with `make demo-video` in this
directory (see README.md).

Frames come from Playwright's screencast and are encoded here (h264 CRF 18): its built-in recorder is
VP8 at 1 Mbit/s, and a still page produces no frames at all, so each frame is held until the next.
"""

import gzip
import json
import os
import re
import struct
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

XNAT = os.environ.get("XNAT_URL", "http://127.0.0.1:8105").rstrip("/")
USER = os.environ.get("XNAT_USER", "admin")
PASSWORD = os.environ["XNAT_PASSWORD"]
EXPERIMENT = os.environ["XNAT_EXPERIMENT"]
MODEL = os.environ.get("MONAI_LABEL_MODEL", "segmentation_spleen")
MONAI_LABEL = os.environ.get("MONAI_LABEL_URL", "http://127.0.0.1:8030").rstrip("/")
SCALE = int(os.environ.get("DEMO_VIDEO_SCALE", "2"))
OUT = Path(os.environ.get("OUT_DIR", "/out"))
CONVERT_TIMEOUT_S = int(os.environ.get("EXPORT_MASK_TIMEOUT", "300"))
W, H = 1280, 800

# Captions and a visible cursor, injected into every page the demo visits. Playwright's own
# show_actions() prints the raw selector of each action, which is not something to put on camera.
OVERLAY_JS = """
(() => {
  const ready = () => {
    if (document.getElementById('demo-caption')) return;
    const caption = document.createElement('div');
    caption.id = 'demo-caption';
    caption.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:76%;' +
      'padding:10px 24px;border-radius:9999px;background:rgba(17,24,39,.94);color:#f9fafb;z-index:2147483647;' +
      "font:17px/1.45 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;text-align:center;" +
      'box-shadow:0 4px 14px rgba(0,0,0,.35);pointer-events:none;display:none';
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.style.cssText = 'position:fixed;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
      'background:rgba(250,204,21,.55);border:2px solid rgba(250,204,21,.95);z-index:2147483647;' +
      'pointer-events:none;left:-40px;top:-40px;transition:transform .12s';
    document.body.append(caption, cursor);
    document.addEventListener('mousemove', e => {
      cursor.style.left = e.clientX + 'px';
      cursor.style.top = e.clientY + 'px';
    }, true);
    document.addEventListener('mousedown', () => { cursor.style.transform = 'scale(.7)'; }, true);
    document.addEventListener('mouseup', () => { cursor.style.transform = ''; }, true);
    window.__demoCaption = text => { caption.textContent = text; caption.style.display = text ? 'block' : 'none'; };
  };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', ready) : ready();
})();
"""


class Frames:
    """Screencast frames written to disk with their timestamps, encoded at the end."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.frames: list[tuple[str, float]] = []

    def on_frame(self, frame: dict) -> None:
        name = f"{len(self.frames):06d}.jpg"
        (self.dir / name).write_bytes(frame["data"])
        self.frames.append((name, frame["timestamp"]))

    def encode(self, stopped_at_ms: float, target: Path) -> None:
        lines = []
        for i, (name, ts) in enumerate(self.frames):
            end = self.frames[i + 1][1] if i + 1 < len(self.frames) else stopped_at_ms
            lines += [f"file '{name}'", f"duration {max(end - ts, 1) / 1000:.4f}"]
        lines.append(f"file '{self.frames[-1][0]}'")
        (self.dir / "list.txt").write_text("\n".join(lines) + "\n")
        w, h = W * SCALE, H * SCALE
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
             "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30,"
             "format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart",
             str(target.resolve())],
            cwd=self.dir, check=True,
        )  # fmt: skip


class Demo:
    def __init__(self, page: Page) -> None:
        self.page = page

    def caption(self, text: str, hold_ms: int = 0) -> None:
        self.page.evaluate("t => window.__demoCaption && window.__demoCaption(t)", text)
        if hold_ms:
            self.page.wait_for_timeout(hold_ms)

    def tidy(self) -> None:
        """Drop XNAT's "N sessions open from M addresses" nag: it counts the box's other users, not this demo."""
        self.page.evaluate("() => document.getElementById('warning_bar')?.remove()")

    def click(self, target: Locator, pause_ms: int = 350) -> None:
        """Glide the cursor to the target, then click it, so a viewer can follow the hand."""
        target.wait_for(state="visible")
        box = target.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
        self.page.wait_for_timeout(pause_ms)
        target.click()

    def type(self, target: Locator, text: str) -> None:
        self.click(target)
        target.press_sequentially(text, delay=55)


def xnat_api(pw):
    return pw.request.new_context(
        base_url=XNAT, http_credentials={"username": USER, "password": PASSWORD, "send": "always"}
    )


def seg_files(api, experiment: str) -> dict[str, list[str]]:
    """Every ROI collection on the session -> the files in its SEG resource."""
    url = f"/data/experiments/{experiment}/assessors?format=json"
    assessors = [a["ID"] for a in api.get(url).json()["ResultSet"]["Result"] if a["xsiType"] == "icr:roiCollectionData"]
    return {
        a: [f["Name"] for f in api.get(f"/data/experiments/{experiment}/assessors/{a}/resources/SEG/files?format=json")
            .json()["ResultSet"]["Result"]]
        for a in assessors
    }  # fmt: skip


def mask_slices(api, experiment: str) -> tuple[int, list[int]]:
    """The model's mask for this session, from MONAI Label (off camera): (slices, spleen voxels per slice).

    The viewer offers no way to jump to a segment, so the recorder asks the server for the same
    mask the panel will paint and scrolls through exactly the slices it covers. The NIfTI header is
    read with the stdlib (the recorder image has no numpy): dim[1..3] at byte 40, datatype at 70,
    vox_offset at 108; the result is requested as uint8.
    """
    fields = api.get(f"/data/experiments/{experiment}?format=json").json()["items"][0]["data_fields"]
    scans = api.get(f"/data/experiments/{experiment}/scans?format=json").json()["ResultSet"]["Result"]
    (scan,) = [s["ID"] for s in scans]
    image = f"{fields['project']}/{fields['subject_ID']}/{experiment}/{scan}"
    params = {"result_extension": ".nii.gz", "result_dtype": "uint8", "result_compress": True}
    response = api.post(
        f"{MONAI_LABEL}/infer/{MODEL}", params={"image": image, "output": "image"},
        multipart={"params": json.dumps({**params, "foreground": [], "background": []})}, timeout=300_000,
    )  # fmt: skip
    assert response.ok, f"MONAI Label infer {response.status}: {response.text()[:200]}"
    raw = gzip.decompress(response.body())
    assert struct.unpack_from("<i", raw, 0)[0] == 348, "not a little-endian NIfTI-1 mask"
    nx, ny, nz = struct.unpack_from("<8h", raw, 40)[1:4]
    assert struct.unpack_from("<h", raw, 70)[0] == 2, "mask is not uint8"
    offset, plane = int(struct.unpack_from("<f", raw, 108)[0]), nx * ny
    return nz, [plane - raw[offset + z * plane : offset + (z + 1) * plane].count(0) for z in range(nz)]


def wait_for_converted_mask(api, experiment: str, before: set[str]) -> tuple[str, str]:
    """The new ROI collection and the NIfTI export_mask put beside its DICOM-SEG; fails on timeout."""
    deadline = time.monotonic() + CONVERT_TIMEOUT_S
    while time.monotonic() < deadline:
        for assessor, files in seg_files(api, experiment).items():
            nifti = [f for f in files if f.endswith(".nii.gz")]
            if assessor not in before and nifti:
                return assessor, nifti[0]
        time.sleep(5)
    raise SystemExit(f"export_mask produced no NIfTI on {experiment} within {CONVERT_TIMEOUT_S}s")


def record(pw) -> Path:
    api = xnat_api(pw)
    before = set(seg_files(api, EXPERIMENT))
    nz, per_slice = mask_slices(api, EXPERIMENT)
    covered = [z for z, voxels in enumerate(per_slice) if voxels]
    assert covered, f"{MODEL} found nothing on {EXPERIMENT}"
    # The viewer stacks the slices opposite to the NIfTI's z axis: slider = slices - 1 - z.
    to_slider = lambda z: nz - 1 - z  # noqa: E731
    widest = max(covered, key=per_slice.__getitem__)
    browser = pw.chromium.launch(args=[f"--force-device-scale-factor={SCALE}", "--use-angle=swiftshader",
                                       "--enable-unsafe-swiftshader"])  # fmt: skip
    context = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=SCALE)
    context.add_init_script(OVERLAY_JS)
    page = context.new_page()
    page.set_default_timeout(120_000)
    demo = Demo(page)
    try:
        assessor, nifti, stopped, frames = steps(page, demo, api, before, covered, widest, to_slider)
    except Exception:
        page.screenshot(path=str(OUT / "failure.png"))  # what the recorder was looking at
        raise
    context.close()
    browser.close()
    api.dispose()

    video = OUT / "monailabel-demo.mp4"
    frames.encode(stopped, video)
    (OUT / "result.json").write_text(json.dumps({"experiment": EXPERIMENT, "assessor": assessor, "nifti": nifti}))
    return video


def steps(page: Page, demo: Demo, api, before: set[str], covered: list[int], widest: int, to_slider):
    """The recorded part: from the login page to the converted mask."""

    # Off camera: the login page and its fonts, so the video opens on a settled frame.
    page.goto(f"{XNAT}/")
    page.locator("form#login_form").wait_for()
    page.evaluate("() => document.fonts.ready.then(() => true)")

    frames = Frames(OUT / "frames")
    page.screencast.start(on_frame=frames.on_frame, size={"width": W * SCALE, "height": H * SCALE})

    demo.caption("Inside the trust: a clinician signs in to the trust's XNAT", 1500)
    form = page.locator("form#login_form")
    demo.type(form.locator("input[name='username']"), USER)
    demo.type(form.locator("input[name='password']"), PASSWORD)
    demo.click(form.locator("[type='submit'], button").first)
    page.wait_for_url(lambda url: "Login.vm" not in url)

    page.goto(f"{XNAT}/data/experiments/{EXPERIMENT}?format=html")
    demo.tidy()
    demo.caption("A spleen CT imported for an FL project, opened in the OHIF viewer", 2500)
    demo.click(page.locator("#ohifViewer"))
    page.wait_for_url(re.compile("/VIEWER/"))
    page.locator("canvas").last.wait_for(state="visible")
    page.wait_for_timeout(5000)

    demo.caption("Once per browser: switch on MONAI Label under Options → Preferences → Experimental", 1500)
    demo.click(page.locator("[data-cy=options-menu]"))
    demo.click(page.get_by_role("button", name="Preferences"))
    demo.click(page.locator("li[data-cy=experimental-features] button"))
    for feature in ("MONAILabel Tools", "Load image slices from the middle"):
        box = page.locator("label.featureLabel", has_text=feature).locator("xpath=following::input[1]")
        if not box.is_checked():
            demo.click(box)
    page.wait_for_timeout(800)
    demo.click(page.get_by_role("button", name="Save"))
    page.reload()
    page.locator("canvas").last.wait_for(state="visible")
    page.wait_for_timeout(5000)

    demo.caption("The MONAI Label panel connects to the trust's own server: nothing leaves the hospital", 800)
    demo.click(page.get_by_text("Masks", exact=True))
    demo.click(page.locator("[data-cy=mask]"))
    demo.click(page.get_by_text("MONAILabel", exact=True))
    page.wait_for_timeout(1800)
    page.locator("#monaiToolList").select_option(label="Segmentation")
    page.locator("select:near(:text('Segmentation models'))").first.select_option(label=MODEL)
    demo.caption(f"Run {MODEL} — the model segments the whole volume on the trust's GPU", 1500)
    demo.click(page.get_by_role("button", name="Run"))
    page.get_by_text(re.compile(r"^spleen$")).first.wait_for()
    page.wait_for_timeout(1500)

    demo.caption("Every slice the model found the spleen on, ready to review and correct", 500)
    slider = page.locator("input.imageSlider")
    step = max(1, len(covered) // 28)  # ~28 frames through the organ, whatever its extent
    for z in covered[::-step]:
        slider.fill(str(to_slider(z)))
        page.wait_for_timeout(160)
    slider.fill(str(to_slider(widest)))
    page.wait_for_timeout(2500)

    demo.caption("Save it to XNAT: the mask becomes a DICOM-SEG ROI collection on the session", 800)
    demo.click(page.get_by_role("button", name="Export", exact=True).first)
    page.locator("input[value='spleen']").wait_for()
    page.wait_for_timeout(1200)
    demo.click(page.locator("button:right-of(input[value='spleen']):has-text('Export')").first)
    page.get_by_text("spleen", exact=True).first.wait_for()
    page.wait_for_timeout(2500)

    demo.caption("…and XNAT's export_mask command converts it to NIfTI for federated training", 500)
    assessor, nifti = wait_for_converted_mask(api, EXPERIMENT, before)
    page.goto(f"{XNAT}/data/experiments/{EXPERIMENT}/assessors/{assessor}?format=html")
    page.get_by_text("Resources", exact=True).wait_for()
    demo.tidy()
    demo.caption("The ROI collection in XNAT: its SEG resource now holds two files", 2500)
    demo.click(page.get_by_text("Manage Files", exact=True))
    # The SEG folder opens collapsed. YUI renames the toggle's class on hover (ygtvlp -> ygtvlph),
    # and the cursor glides onto it before clicking, so match either.
    demo.click(page.locator("table.ygtvdepth1 td[class*=ygtvlp]"))
    page.get_by_text(nifti).first.wait_for()
    demo.caption(f"{nifti} beside the DICOM-SEG, on the CT's own grid, ready for FL training", 4500)
    demo.caption("", 600)

    stopped = time.time() * 1000
    page.screencast.stop()
    return assessor, nifti, stopped, frames


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        video = record(pw)
    print(f"Wrote {video}")


if __name__ == "__main__":
    main()
