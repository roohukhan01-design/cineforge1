# CineForge - Video Automation Studio

Turn a script into a finished MP4: split the script into scenes, attach images or clips,
voice recordings and background music, pick a transition and color look, generate subtitles,
and render with FFmpeg. Free, offline, no accounts or API keys.

## Install (Windows 10/11, 64-bit)
1. Open the **Releases** page of this repository.
2. Download `CineForge-Setup-<version>.exe` (optionally compare with the `.sha256` file).
3. Run it, choose an install folder, and optionally tick "Create a desktop shortcut".
   Windows SmartScreen may warn because the installer is not code-signed - choose
   *More info -> Run anyway*.
4. Launch **CineForge** from the Start Menu. Python and FFmpeg are included.

Uninstall from *Settings -> Apps* (or Start Menu -> Uninstall CineForge).

## Make a video
1. **Script** tab: paste your script, click *Split script into scenes*.
2. **Scenes** tab: select a scene, choose an image/video and optional voice recording, set the
   duration (a voice recording or clip can set it automatically).
3. **Style, Audio & Subtitles** tab: resolution, transition, color look, background music, subtitles.
4. Choose an output `.mp4` and press **Render video**. Cancel any time; nothing half-written is left.
   Save your work with *File -> Save* (`.cforge` project files store absolute media paths).

Notes: audio inside video clips is muted (use voice recordings / music). Subtitles come from the
scene text; if burning them in fails on a machine, CineForge falls back to a selectable subtitle track
and always writes an `.srt` next to the video.

## Build it yourself (GitHub Actions)
Push this repository to GitHub. The workflow `.github/workflows/build-windows.yml` runs on a Windows
runner: installs pinned dependencies, runs the tests (including real FFmpeg renders), builds with
PyInstaller, self-tests the packaged app, builds the Inno Setup installer, silently installs ->
runs -> uninstalls it, and uploads the installer as an artifact.

**Publish a release:** Actions -> *Build Windows installer* -> *Run workflow* -> tick
*Publish a GitHub Release*. (Or push a tag such as `v0.1.0`.) The release job only runs after the
build and every test passed. To bump the version edit `src/cineforge/__init__.py` and `CHANGELOG.md`.

## Develop locally
```
pip install -r requirements-dev.txt
python -m pytest
python run_cineforge.py
```
FFmpeg must be on PATH for local runs (or set `CINEFORGE_FFMPEG`).

## Licenses
MIT for CineForge. The installer bundles GPL FFmpeg and LGPL Qt - read `THIRD_PARTY_NOTICES.md`.
