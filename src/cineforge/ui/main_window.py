"""Main window of CineForge."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..core.ffmpeg_utils import (AUDIO_EXT, IMAGE_EXT, VIDEO_EXT, FFmpegError, find_ffmpeg,
                                 probe)
from ..core.project import (COLOR_PRESETS, RESOLUTIONS, TRANSITIONS, Project, ProjectError,
                            Scene, load_project, save_project, scenes_from_script)
from ..core.renderer import RenderCancelled, Renderer

VISUAL_FILTER = "Images and video (" + " ".join(f"*{e}" for e in sorted(IMAGE_EXT | VIDEO_EXT)) + ")"
AUDIO_FILTER = "Audio (" + " ".join(f"*{e}" for e in sorted(AUDIO_EXT)) + ")"
PROJECT_FILTER = "CineForge project (*.cforge)"


class RenderWorker(QThread):
    progress = Signal(float, str)
    message = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project: Project, output: str):
        super().__init__()
        self.renderer = Renderer(project, output, progress=self.progress.emit,
                                 log=self.message.emit)

    def run(self):
        try:
            self.succeeded.emit(self.renderer.run())
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.failed.emit(str(e))

    def cancel(self):
        self.renderer.cancel()


def dspin(lo, hi, step, val, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(2 if step < 0.1 else 1)
    w.setValue(val)
    if suffix:
        w.setSuffix(suffix)
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.path: str | None = None
        self.dirty = False
        self._loading = False
        self.worker: RenderWorker | None = None
        self.resize(1180, 780)
        self._build_ui()
        self._apply_settings()
        self._refresh_list()
        self._update_title()
        if not find_ffmpeg():
            self.log("WARNING: FFmpeg not found. Rendering is disabled until it is installed.")
            self.render_btn.setEnabled(False)

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        m = self.menuBar().addMenu("&File")
        for text, slot, key in (("&New", self.new_project, "Ctrl+N"),
                                ("&Open...", self.open_project, "Ctrl+O"),
                                ("&Save", self.save_project_action, "Ctrl+S"),
                                ("Save &As...", self.save_as, "Ctrl+Shift+S")):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(slot)
            m.addAction(a)
        m.addSeparator()
        q = QAction("E&xit", self)
        q.triggered.connect(self.close)
        m.addAction(q)
        h = self.menuBar().addMenu("&Help")
        ab = QAction("&About", self)
        ab.triggered.connect(lambda: QMessageBox.information(
            self, "About CineForge",
            f"CineForge {__version__}\nVideo Automation Studio\n\nUses FFmpeg and Qt (PySide6). "
            "See THIRD_PARTY_NOTICES.md in the install folder."))
        h.addAction(ab)

        self.editor_area = QTabWidget()
        self.editor_area.addTab(self._script_tab(), "1. Script")
        self.editor_area.addTab(self._scenes_tab(), "2. Scenes")
        self.editor_area.addTab(self._settings_tab(), "3. Style, Audio && Subtitles")

        bottom = QGroupBox("Export")
        bl = QVBoxLayout(bottom)
        row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Choose where to save the MP4...")
        self.out_edit.textChanged.connect(self._touch)
        b = QPushButton("Browse...")
        b.clicked.connect(self._browse_output)
        row.addWidget(QLabel("Output file:"))
        row.addWidget(self.out_edit, 1)
        row.addWidget(b)
        bl.addLayout(row)
        row2 = QHBoxLayout()
        self.render_btn = QPushButton("Render video")
        self.render_btn.setObjectName("primary")
        self.render_btn.clicked.connect(self.start_render)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_render)
        self.open_btn = QPushButton("Open output folder")
        self.open_btn.clicked.connect(self.open_output_folder)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = QLabel("Ready")
        row2.addWidget(self.render_btn)
        row2.addWidget(self.cancel_btn)
        row2.addWidget(self.open_btn)
        row2.addWidget(self.progress, 1)
        row2.addWidget(self.status)
        bl.addLayout(row2)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(110)
        bl.addWidget(self.log_view)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.editor_area, 1)
        lay.addWidget(bottom)
        self.setCentralWidget(central)

    def _script_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Write or paste your script. Separate scenes with a blank line; "
                           "a single block is split into scenes by sentences."))
        self.script_edit = QPlainTextEdit()
        self.script_edit.textChanged.connect(self._touch)
        l.addWidget(self.script_edit, 1)
        b = QPushButton("Split script into scenes")
        b.clicked.connect(self.split_script_action)
        l.addWidget(b, 0, Qt.AlignLeft)
        return w

    def _scenes_tab(self):
        w = QWidget()
        l = QHBoxLayout(w)
        left = QVBoxLayout()
        self.scene_list = QListWidget()
        self.scene_list.currentRowChanged.connect(self._load_scene_fields)
        left.addWidget(self.scene_list, 1)
        r = QHBoxLayout()
        for text, slot in (("Add", self.add_scene), ("Remove", self.remove_scene),
                           ("Up", lambda: self.move_scene(-1)), ("Down", lambda: self.move_scene(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            r.addWidget(b)
        left.addLayout(r)
        self.total_label = QLabel("")
        left.addWidget(self.total_label)
        l.addLayout(left, 2)

        box = QGroupBox("Selected scene")
        f = QVBoxLayout(box)
        f.addWidget(QLabel("Narration / subtitle text:"))
        self.scene_text = QPlainTextEdit()
        self.scene_text.textChanged.connect(self._scene_text_changed)
        f.addWidget(self.scene_text, 1)
        self.media_label = QLabel("Media: (none - black screen)")
        self.media_label.setWordWrap(True)
        f.addWidget(self.media_label)
        r = QHBoxLayout()
        for text, slot in (("Choose image / video...", self.choose_media), ("Clear", self.clear_media)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            r.addWidget(b)
        f.addLayout(r)
        self.voice_label = QLabel("Voice recording: (none)")
        self.voice_label.setWordWrap(True)
        f.addWidget(self.voice_label)
        r = QHBoxLayout()
        for text, slot in (("Choose voice recording...", self.choose_voice), ("Clear", self.clear_voice)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            r.addWidget(b)
        f.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("Duration:"))
        self.dur_spin = dspin(0.5, 3600, 0.5, 4.0, " s")
        self.dur_spin.valueChanged.connect(self._duration_changed)
        r.addWidget(self.dur_spin)
        b = QPushButton("Use media length")
        b.clicked.connect(self.use_media_length)
        r.addWidget(b)
        r.addStretch(1)
        f.addLayout(r)
        l.addWidget(box, 3)
        return w

    def _settings_tab(self):
        inner = QWidget()
        l = QVBoxLayout(inner)
        g = QGroupBox("Video")
        f = QFormLayout(g)
        self.res_combo = QComboBox()
        for label, w, h in RESOLUTIONS:
            self.res_combo.addItem(label, (w, h))
        self.fps_combo = QComboBox()
        for v in (24, 25, 30):
            self.fps_combo.addItem(str(v), v)
        self.trans_combo = QComboBox()
        self.trans_combo.addItems(TRANSITIONS)
        self.trans_dur = dspin(0.1, 5, 0.1, 0.5, " s")
        self.color_combo = QComboBox()
        self.color_combo.addItems(COLOR_PRESETS)
        self.fade_in = dspin(0, 5, 0.1, 0.5, " s")
        self.fade_out = dspin(0, 5, 0.1, 0.5, " s")
        for label, wdg in (("Resolution", self.res_combo), ("Frame rate", self.fps_combo),
                           ("Transition", self.trans_combo), ("Transition length", self.trans_dur),
                           ("Color look", self.color_combo), ("Fade in", self.fade_in),
                           ("Fade out", self.fade_out)):
            f.addRow(label, wdg)
        l.addWidget(g)

        g = QGroupBox("Audio")
        f = QFormLayout(g)
        self.music_edit = QLineEdit()
        self.music_edit.setReadOnly(True)
        self.music_edit.setPlaceholderText("No background music")
        r = QHBoxLayout()
        r.addWidget(self.music_edit, 1)
        for text, slot in (("Choose...", self.choose_music), ("Clear", self.clear_music)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            r.addWidget(b)
        rw = QWidget()
        rw.setLayout(r)
        r.setContentsMargins(0, 0, 0, 0)
        self.music_vol = QSlider(Qt.Horizontal)
        self.music_vol.setRange(0, 100)
        self.music_vol.setValue(25)
        self.voice_vol = QSlider(Qt.Horizontal)
        self.voice_vol.setRange(0, 200)
        self.voice_vol.setValue(100)
        self.duck = QCheckBox("Lower music while a voice recording plays")
        f.addRow("Background music", rw)
        f.addRow("Music volume (%)", self.music_vol)
        f.addRow("Voice volume (%)", self.voice_vol)
        f.addRow("", self.duck)
        l.addWidget(g)

        g = QGroupBox("Subtitles (generated from your scene text)")
        f = QFormLayout(g)
        self.sub_on = QCheckBox("Generate subtitles (also saves an .srt next to the video)")
        self.sub_burn = QCheckBox("Burn subtitles into the video (otherwise a selectable track)")
        self.sub_chars = QSpinBox()
        self.sub_chars.setRange(15, 80)
        self.sub_offset = dspin(0, 5, 0.1, 0.0, " s")
        f.addRow(self.sub_on)
        f.addRow(self.sub_burn)
        f.addRow("Max characters per line", self.sub_chars)
        f.addRow("Delay after scene start", self.sub_offset)
        l.addWidget(g)
        l.addStretch(1)
        for wdg in (self.res_combo, self.fps_combo, self.trans_combo, self.color_combo):
            wdg.currentIndexChanged.connect(self._touch)
        for wdg in (self.trans_dur, self.fade_in, self.fade_out, self.sub_chars, self.sub_offset):
            wdg.valueChanged.connect(self._touch)
        for wdg in (self.music_vol, self.voice_vol):
            wdg.valueChanged.connect(self._touch)
        for wdg in (self.duck, self.sub_on, self.sub_burn):
            wdg.toggled.connect(self._touch)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(inner)
        return sc

    # ------------------------------------------------------------ state
    def log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def _touch(self, *_):
        if self._loading:
            return
        self.dirty = True
        self._update_title()
        if hasattr(self, "total_label"):
            self._update_total()

    def _update_title(self):
        name = Path(self.path).name if self.path else "Untitled"
        self.setWindowTitle(f"{name}{'*' if self.dirty else ''} - CineForge")

    def _collect(self):
        p, s = self.project, self.project.settings
        p.script = self.script_edit.toPlainText()
        p.output = self.out_edit.text().strip()
        s.width, s.height = self.res_combo.currentData()
        s.fps = self.fps_combo.currentData()
        s.transition = self.trans_combo.currentText()
        s.transition_duration = self.trans_dur.value()
        s.color = self.color_combo.currentText()
        s.fade_in, s.fade_out = self.fade_in.value(), self.fade_out.value()
        s.music = self.music_edit.text()
        s.music_volume = self.music_vol.value() / 100
        s.voice_volume = self.voice_vol.value() / 100
        s.duck_music = self.duck.isChecked()
        s.subtitles = self.sub_on.isChecked()
        s.burn_subtitles = self.sub_burn.isChecked()
        s.sub_max_chars = self.sub_chars.value()
        s.sub_offset = self.sub_offset.value()

    def _apply_settings(self):
        self._loading = True
        p, s = self.project, self.project.settings
        self.script_edit.setPlainText(p.script)
        self.out_edit.setText(p.output)
        i = self.res_combo.findData((s.width, s.height))
        self.res_combo.setCurrentIndex(max(0, i))
        self.fps_combo.setCurrentIndex(max(0, self.fps_combo.findData(s.fps)))
        self.trans_combo.setCurrentIndex(max(0, self.trans_combo.findText(s.transition)))
        self.trans_dur.setValue(s.transition_duration)
        self.color_combo.setCurrentIndex(max(0, self.color_combo.findText(s.color)))
        self.fade_in.setValue(s.fade_in)
        self.fade_out.setValue(s.fade_out)
        self.music_edit.setText(s.music)
        self.music_vol.setValue(int(s.music_volume * 100))
        self.voice_vol.setValue(int(s.voice_volume * 100))
        self.duck.setChecked(s.duck_music)
        self.sub_on.setChecked(s.subtitles)
        self.sub_burn.setChecked(s.burn_subtitles)
        self.sub_chars.setValue(s.sub_max_chars)
        self.sub_offset.setValue(s.sub_offset)
        self._loading = False

    # ------------------------------------------------------------ scenes
    def _scene(self) -> Scene | None:
        r = self.scene_list.currentRow()
        return self.project.scenes[r] if 0 <= r < len(self.project.scenes) else None

    def _label(self, i: int, sc: Scene) -> str:
        txt = " ".join(sc.text.split())[:45] or "(empty)"
        return f"{i + 1}. {txt}  [{sc.duration:.1f}s]"

    def _refresh_list(self, select: int | None = None):
        self._loading = True
        cur = self.scene_list.currentRow() if select is None else select
        self.scene_list.clear()
        for i, sc in enumerate(self.project.scenes):
            self.scene_list.addItem(self._label(i, sc))
        if self.project.scenes:
            self.scene_list.setCurrentRow(min(max(cur, 0), len(self.project.scenes) - 1))
        self._loading = False
        self._load_scene_fields()
        self._update_total()

    def _update_total(self):
        from ..core.project import total_duration
        s = self.project.settings
        t = self.trans_dur.value() if self.trans_combo.currentText() != "none" else 0
        total = total_duration([x.duration for x in self.project.scenes], t)
        self.total_label.setText(f"{len(self.project.scenes)} scene(s), about {total:.1f} s total")

    def _load_scene_fields(self, *_):
        sc = self._scene()
        self._loading = True
        on = sc is not None
        for w in (self.scene_text, self.dur_spin):
            w.setEnabled(on)
        self.scene_text.setPlainText(sc.text if sc else "")
        self.dur_spin.setValue(sc.duration if sc else 4.0)
        self.media_label.setText(f"Media: {sc.media}" if sc and sc.media else "Media: (none - black screen)")
        self.voice_label.setText(f"Voice recording: {sc.voice}" if sc and sc.voice else "Voice recording: (none)")
        self._loading = False

    def _scene_text_changed(self):
        sc = self._scene()
        if self._loading or not sc:
            return
        sc.text = self.scene_text.toPlainText()
        self._relabel()
        self._touch()

    def _duration_changed(self, v: float):
        sc = self._scene()
        if self._loading or not sc:
            return
        sc.duration = float(v)
        self._relabel()
        self._touch()

    def _relabel(self):
        r = self.scene_list.currentRow()
        if r >= 0:
            self.scene_list.item(r).setText(self._label(r, self.project.scenes[r]))
        self._update_total()

    def split_script_action(self):
        text = self.script_edit.toPlainText()
        scenes = scenes_from_script(text)
        if not scenes:
            QMessageBox.information(self, "Split script", "The script is empty.")
            return
        if self.project.scenes and QMessageBox.question(
                self, "Replace scenes?",
                "This replaces your current scenes (media assignments will be lost). Continue?"
        ) != QMessageBox.Yes:
            return
        self.project.scenes = scenes
        self._refresh_list(0)
        self._touch()
        self.editor_area.setCurrentIndex(1)

    def add_scene(self):
        self.project.scenes.append(Scene())
        self._refresh_list(len(self.project.scenes) - 1)
        self._touch()

    def remove_scene(self):
        r = self.scene_list.currentRow()
        if 0 <= r < len(self.project.scenes):
            del self.project.scenes[r]
            self._refresh_list(r)
            self._touch()

    def move_scene(self, d: int):
        r, sc = self.scene_list.currentRow(), self.project.scenes
        n = r + d
        if 0 <= r < len(sc) and 0 <= n < len(sc):
            sc[r], sc[n] = sc[n], sc[r]
            self._refresh_list(n)
            self._touch()

    def _probe(self, path: str, need_audio=False, need_video=False):
        try:
            info = probe(path)
        except (FFmpegError, OSError) as e:
            QMessageBox.warning(self, "Cannot use this file", str(e))
            return None
        if need_audio and not info.has_audio:
            QMessageBox.warning(self, "Cannot use this file", f"{Path(path).name} has no audio.")
            return None
        if need_video and not info.has_video:
            QMessageBox.warning(self, "Cannot use this file", f"{Path(path).name} has no picture.")
            return None
        return info

    def choose_media(self):
        sc = self._scene()
        if not sc:
            QMessageBox.information(self, "No scene", "Add or select a scene first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose image or video", "", VISUAL_FILTER)
        if not path:
            return
        info = self._probe(path, need_video=True)
        if not info:
            return
        sc.media = path
        if not info.is_image and info.duration:
            sc.duration = round(info.duration, 1)
            self.log(f"Scene duration set to the clip length ({sc.duration}s).")
        self._refresh_list()
        self._touch()

    def clear_media(self):
        sc = self._scene()
        if sc:
            sc.media = ""
            self._load_scene_fields()
            self._touch()

    def choose_voice(self):
        sc = self._scene()
        if not sc:
            QMessageBox.information(self, "No scene", "Add or select a scene first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose voice recording", "", AUDIO_FILTER)
        if not path:
            return
        info = self._probe(path, need_audio=True)
        if not info:
            return
        sc.voice = path
        if info.duration and info.duration + 0.2 > sc.duration:
            sc.duration = round(info.duration + 0.2, 1)
            self.log(f"Scene duration extended to fit the recording ({sc.duration}s).")
        self._refresh_list()
        self._touch()

    def clear_voice(self):
        sc = self._scene()
        if sc:
            sc.voice = ""
            self._load_scene_fields()
            self._touch()

    def use_media_length(self):
        sc = self._scene()
        if not sc:
            return
        path = sc.voice or sc.media
        if not path:
            QMessageBox.information(self, "Use media length", "This scene has no media or voice.")
            return
        info = self._probe(path)
        if info and info.duration and not info.is_image:
            sc.duration = round(info.duration + (0.2 if sc.voice else 0), 1)
            self._refresh_list()
            self._touch()
        elif info:
            QMessageBox.information(self, "Use media length", "Images have no length; set the duration manually.")

    def choose_music(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose background music", "", AUDIO_FILTER)
        if path and self._probe(path, need_audio=True):
            self.music_edit.setText(path)
            self._touch()

    def clear_music(self):
        self.music_edit.setText("")
        self._touch()

    # ------------------------------------------------------------ files
    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to this project first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_project_action()
        return r == QMessageBox.Discard

    def new_project(self):
        if self.worker or not self._confirm_discard():
            return
        self.project, self.path, self.dirty = Project(), None, False
        self._apply_settings()
        self._refresh_list()
        self._update_title()

    def open_project(self):
        if self.worker or not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", PROJECT_FILTER)
        if path:
            self.load_from(path)

    def load_from(self, path: str) -> bool:
        try:
            self.project = load_project(path)
        except ProjectError as e:
            QMessageBox.warning(self, "Cannot open project", str(e))
            return False
        self.path, self.dirty = path, False
        self._apply_settings()
        self._refresh_list(0)
        self._update_title()
        missing = [x for x in [*(s.media for s in self.project.scenes),
                               *(s.voice for s in self.project.scenes),
                               self.project.settings.music] if x and not Path(x).is_file()]
        if missing:
            self.log(f"WARNING: {len(missing)} media file(s) in this project are missing.")
        return True

    def save_to(self, path: str) -> bool:
        self._collect()
        try:
            save_project(self.project, path)
        except ProjectError as e:
            QMessageBox.warning(self, "Cannot save project", str(e))
            return False
        self.path, self.dirty = path, False
        self._update_title()
        return True

    def save_project_action(self) -> bool:
        return self.save_to(self.path) if self.path else self.save_as()

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "project.cforge", PROJECT_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".cforge"):
            path += ".cforge"
        return self.save_to(path)

    # ------------------------------------------------------------ render
    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save video as", self.out_edit.text() or "video.mp4",
                                              "MP4 video (*.mp4)")
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.out_edit.setText(path)

    def start_render(self):
        if self.worker:
            return
        self._collect()
        if not self.project.output:
            self._browse_output()
            self._collect()
        proj = copy.deepcopy(self.project)
        r = Renderer(proj, proj.output)
        errs = r.validate()
        if errs:
            QMessageBox.warning(self, "Cannot render yet", "\n\n".join(errs))
            return
        self.log_view.clear()
        self.worker = RenderWorker(proj, proj.output)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self.log)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(self._on_thread_finished)
        self._set_rendering(True)
        self.worker.start()

    def _set_rendering(self, on: bool):
        self.editor_area.setEnabled(not on)
        self.out_edit.setEnabled(not on)
        self.render_btn.setEnabled(not on)
        self.cancel_btn.setEnabled(on)
        if on:
            self.progress.setValue(0)

    def cancel_render(self):
        if self.worker:
            self.status.setText("Cancelling...")
            self.cancel_btn.setEnabled(False)
            self.worker.cancel()

    def _on_progress(self, frac: float, label: str):
        self.progress.setValue(int(frac * 1000))
        self.status.setText(f"{label} - {frac * 100:.0f}%")

    def _on_success(self, out: str):
        self.status.setText("Done")
        self.progress.setValue(1000)
        self.log(f"Finished: {out}")
        box = QMessageBox(self)
        box.setWindowTitle("Video ready")
        box.setText(f"Your video was exported and verified:\n{out}")
        open_btn = box.addButton("Open folder", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            self.open_output_folder()

    def _on_failed(self, msg: str):
        self.status.setText("Failed")
        self.log("ERROR: " + msg)
        QMessageBox.critical(self, "Render failed", msg)

    def _on_cancelled(self):
        self.status.setText("Cancelled")
        self.progress.setValue(0)
        self.log("Render cancelled. No output file was written.")

    def _on_thread_finished(self):
        self.worker = None
        self._set_rendering(False)
        if not find_ffmpeg():
            self.render_btn.setEnabled(False)

    def open_output_folder(self):
        out = self.out_edit.text().strip()
        folder = Path(out).expanduser().parent if out else Path.home()
        if not folder.is_dir():
            QMessageBox.information(self, "Output folder", "The output folder does not exist yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, e):
        if self.worker:
            if QMessageBox.question(self, "Rendering", "A render is running. Cancel it and exit?") != QMessageBox.Yes:
                e.ignore()
                return
            self.worker.cancel()
            self.worker.wait(15000)
        elif not self._confirm_discard():
            e.ignore()
            return
        e.accept()
