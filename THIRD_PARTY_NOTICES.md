# Third-party notices

CineForge's own code is MIT-licensed (see LICENSE). The Windows installer also contains the
components below. This is a good-faith summary, not legal advice - review it before you
distribute CineForge to others.

| Component | Used for | License |
|---|---|---|
| FFmpeg (Windows build shipped by the `imageio-ffmpeg` 0.5.1 package) | Video/audio processing, run as a separate `ffmpeg.exe` process | GPL (this build includes GPL components such as libx264). Exact configuration: `licenses\ffmpeg-buildinfo.txt` |
| Qt 6 / PySide6-Essentials 6.7.3 | User interface | LGPL v3 (PySide6 is also offered under GPL/commercial) |
| imageio-ffmpeg | Provides the FFmpeg binary at build time (not used at runtime) | BSD-2-Clause |
| PyInstaller 6.10.0 | Packaging (bootloader is included in the app) | GPL v2+ with bootloader exception |
| Python 3.12 runtime | Embedded interpreter | PSF License |
| Inno Setup | Builds the installer (not shipped) | Inno Setup License |

## FFmpeg (GPL)
FFmpeg is launched as a separate program; CineForge does not link against it. Because the shipped
build is GPL, you must pass on the GPL text (installed in `licenses\`) and offer the corresponding
source. FFmpeg source: https://ffmpeg.org/download.html . libx264 source: https://www.videolan.org/developers/x264.html .
The source for the exact binary is available from the imageio-ffmpeg / FFmpeg project upon request
via the project pages above. If you want to avoid GPL obligations, replace the bundled
`ffmpeg.exe` with an LGPL-only build and use an encoder it provides.

## Qt / PySide6 (LGPL v3)
Qt libraries are shipped as separate DLLs in the install folder (PyInstaller one-folder mode), so
you may replace them with another compatible Qt build. Qt source: https://download.qt.io/ . The
LGPL v3 text is installed in `licenses\`.

## Reminder
Do not bundle fonts, music or footage you do not have the rights to distribute. Media you import
into CineForge stays on your computer.
