"""
SigmaScope – User Interface v4 (Studio Monochrome)
Added BG Image and Freehand Draw modes.
"""

import os
import time

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QComboBox, QFileDialog,
    QSizePolicy, QSpacerItem, QFrame,
)
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QFont, QPainter, QPen, QColor

from audio import AudioEngine, PlayState
from visualizer import Visualizer, VisMode

class JumpSlider(QSlider):
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * e.position().x()) / self.width()
            self.setValue(int(val))
            e.accept()
        super().mousePressEvent(e)


class DrawOverlay(QWidget):
    """Transparent overlay for capturing freehand drawing paths."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.points = []
        self.drawing = False
        self.on_complete = None
        self.hide()

    def mousePressEvent(self, e):
        self.points = [(e.position().x() / self.width(), 1.0 - (e.position().y() / self.height()))]
        self.drawing = True
        self.update()

    def mouseMoveEvent(self, e):
        if self.drawing:
            self.points.append((e.position().x() / self.width(), 1.0 - (e.position().y() / self.height())))
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drawing:
            self.drawing = False
            if self.on_complete:
                self.on_complete(self.points)
            self.hide()
            self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.points:
            return
            
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(255, 255, 255))
        pen.setWidth(2)
        p.setPen(pen)
        
        for i in range(len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i+1]
            p.drawLine(
                int(p1[0] * self.width()), int((1.0 - p1[1]) * self.height()),
                int(p2[0] * self.width()), int((1.0 - p2[1]) * self.height())
            )
        p.end()


STYLESHEET = """
/* ── Base ── */
QMainWindow, QWidget#centralWidget { background-color: #f4f4f0; }
QFrame#panelTop, QFrame#panelSeek, QFrame#panelControls {
    background-color: transparent;
    border: 2px solid #2b2b2b;
    border-radius: 6px;
}
/* ── Buttons ── */
QPushButton {
    background-color: #ffffff;
    color: #2b2b2b;
    border: 2px solid #2b2b2b;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Jokerman', 'Snap ITC', 'Comic Sans MS', cursive;
    text-transform: uppercase;
}
QPushButton:hover { background-color: #e8e8e4; }
QPushButton:pressed { background-color: #dcdccf; color: #ff6b6b; border-color: #ff6b6b; }
QPushButton#btnPlay {
    background-color: #ffffff;
    border: 3px solid #2b2b2b;
    padding: 6px 24px;
    font-size: 14px;
}
QPushButton#btnPlay:hover { background-color: #e8e8e4; }
QPushButton#btnPlay:pressed { background-color: #dcdccf; color: #4ecdc4; border-color: #4ecdc4; }
/* ── Seek bar ── */
QSlider#seekBar::groove:horizontal { height: 2px; background: #2b2b2b; }
QSlider#seekBar::handle:horizontal {
    width: 14px; height: 14px;
    background: #ffffff;
    border-radius: 7px;
    margin: -6px 0;
    border: 2px solid #2b2b2b;
}
QSlider#seekBar::handle:horizontal:hover { background: #ff6b6b; }
QSlider#seekBar::sub-page:horizontal { background: #2b2b2b; }
/* ── Param sliders ── */
QSlider::groove:horizontal { height: 2px; background: #2b2b2b; }
QSlider::handle:horizontal {
    width: 12px; height: 16px;
    background: #ffffff;
    border: 2px solid #2b2b2b;
    margin: -7px 0;
    border-radius: 3px;
}
QSlider::handle:horizontal:hover { background: #4ecdc4; }
QSlider::sub-page:horizontal { background: #2b2b2b; }
/* ── Combo box ── */
QComboBox {
    background-color: #ffffff;
    color: #2b2b2b;
    border: 2px solid #2b2b2b;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: bold;
    font-family: 'Jokerman', 'Snap ITC', 'Comic Sans MS', cursive;
    text-transform: uppercase;
}
QComboBox:hover { background-color: #e8e8e4; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #2b2b2b;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #2b2b2b;
    selection-background-color: #e8e8e4;
    selection-color: #ff6b6b;
    border: 2px solid #2b2b2b;
    font-family: 'Jokerman', 'Snap ITC', 'Comic Sans MS', cursive;
    font-weight: bold;
}
/* ── Labels ── */
QLabel {
    color: #2b2b2b;
    font-size: 13px;
    font-family: 'Jokerman', 'Snap ITC', 'Comic Sans MS', cursive;
    font-weight: bold;
    text-transform: uppercase;
}
QLabel#lblTitle {
    color: #ff6b6b;
    font-size: 18px;
    font-weight: 900;
    letter-spacing: 2px;
    text-shadow: 2px 2px #2b2b2b;
}
QLabel#lblFile { color: #555555; font-size: 11px; }
QLabel#lblTime { color: #2b2b2b; font-size: 13px; }
QLabel#lblFps  { color: #777777; font-size: 11px; }
QLabel#lblVol  { color: #2b2b2b; min-width: 32px; font-size: 12px; }
"""

def _fmt(seconds: float) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m:02d}:{s:02d}"


class MainWindow(QMainWindow):
    def __init__(self, engine: AudioEngine):
        super().__init__()
        self.setWindowTitle("SigmaScope Studio")
        self.setMinimumSize(1000, 680)
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self.engine = engine
        self.visualizer = Visualizer()
        self._ftimes: list[float] = []
        self._fps = 0.0
        self._seeking = False
        self._mode_params: dict[str, dict[str, any]] = {}
        self._updating_sliders = False

        self._build()
        self._wire()
        self._timers()
        self._on_mode_changed(self.combo.currentText())

    def _build(self):
        cw = QWidget(); cw.setObjectName("centralWidget")
        self.setCentralWidget(cw)
        
        # We need a layered layout to put the DrawOverlay on top of the visualizer
        root = QVBoxLayout(cw)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Top panel ──
        top_panel = QFrame(); top_panel.setObjectName("panelTop")
        top = QHBoxLayout(top_panel)
        top.setContentsMargins(16, 10, 16, 10)
        
        title_col = QVBoxLayout(); title_col.setSpacing(4)
        self.lbl_title = QLabel("SIGMASCOPE"); self.lbl_title.setObjectName("lblTitle")
        self.lbl_file = QLabel("NO FILE LOADED"); self.lbl_file.setObjectName("lblFile")
        title_col.addWidget(self.lbl_title); title_col.addWidget(self.lbl_file)
        top.addLayout(title_col)

        top.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.combo = QComboBox()
        self.combo.addItems(["Wave", "Circle", "Equalizer", "Spectrogram",
                             "Custom Shape", "Lissajous", "Polar Sample", "Polar Level", "All Together"])
        top.addWidget(QLabel("MODE")); top.addWidget(self.combo)
        
        sep = QLabel("│"); sep.setFixedWidth(12); sep.setAlignment(Qt.AlignCenter); top.addWidget(sep)
        self.lbl_fps = QLabel("-- FPS"); self.lbl_fps.setObjectName("lblFps"); self.lbl_fps.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.lbl_fps)
        root.addWidget(top_panel)

        # ── Visualizer Container (for Overlay) ──
        vis_container = QWidget()
        vis_layout = QVBoxLayout(vis_container)
        vis_layout.setContentsMargins(0,0,0,0)
        vis_layout.addWidget(self.visualizer.widget)
        
        self.draw_overlay = DrawOverlay(vis_container)
        
        root.addWidget(vis_container, stretch=1)

        # ── Seek panel ──
        seek_panel = QFrame(); seek_panel.setObjectName("panelSeek")
        seek = QHBoxLayout(seek_panel); seek.setContentsMargins(16, 12, 16, 12)
        
        self.lbl_cur = QLabel("00:00"); self.lbl_cur.setObjectName("lblTime")
        self.seek = JumpSlider(Qt.Horizontal); self.seek.setObjectName("seekBar"); self.seek.setRange(0, 10000)
        self.lbl_dur = QLabel("00:00"); self.lbl_dur.setObjectName("lblTime"); self.lbl_dur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        seek.addWidget(self.lbl_cur); seek.addWidget(self.seek); seek.addWidget(self.lbl_dur)
        root.addWidget(seek_panel)

        # ── Controls panel ──
        ctrl_panel = QFrame(); ctrl_panel.setObjectName("panelControls")
        ctrl = QHBoxLayout(ctrl_panel); ctrl.setContentsMargins(16, 12, 16, 12)

        self.btn_open = QPushButton("OPEN")
        self.btn_bg = QPushButton("BG IMAGE")
        self.btn_draw = QPushButton("DRAW SHAPE")
        self.btn_play = QPushButton("PLAY"); self.btn_play.setObjectName("btnPlay")
        self.btn_stop = QPushButton("STOP")

        ctrl.addWidget(self.btn_open)
        ctrl.addWidget(self.btn_bg)
        ctrl.addWidget(self.btn_draw)
        ctrl.addWidget(self.btn_play)
        ctrl.addWidget(self.btn_stop)
        
        ctrl.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.lbl_vol_icon = QLabel("VOL"); self.lbl_vol_icon.setFixedWidth(26)
        self.vol = QSlider(Qt.Horizontal); self.vol.setObjectName("volumeSlider"); self.vol.setRange(0, 100); self.vol.setValue(70)
        self.lbl_vol = QLabel("70%"); self.lbl_vol.setObjectName("lblVol")
        
        ctrl.addWidget(self.lbl_vol_icon); ctrl.addWidget(self.vol); ctrl.addWidget(self.lbl_vol)
        root.addWidget(ctrl_panel)
        
        # ── Parameter panel ──
        param_panel = QFrame(); param_panel.setObjectName("panelControls")
        param = QVBoxLayout(param_panel); param.setContentsMargins(16, 8, 16, 8); param.setSpacing(8)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("SENSITIVITY"))
        self.sl_sens = QSlider(Qt.Horizontal); self.sl_sens.setRange(1, 200); self.sl_sens.setValue(100); row1.addWidget(self.sl_sens)
        row1.addWidget(QLabel("SPEED"))
        self.sl_speed = QSlider(Qt.Horizontal); self.sl_speed.setRange(1, 200); self.sl_speed.setValue(100); row1.addWidget(self.sl_speed)
        row1.addWidget(QLabel("COMPLEXITY"))
        self.sl_comp = QSlider(Qt.Horizontal); self.sl_comp.setRange(1, 200); self.sl_comp.setValue(100); row1.addWidget(self.sl_comp)
        param.addLayout(row1)
        
        row2 = QHBoxLayout()
        self.lbl_color = QLabel("COLOR (HUE)")
        row2.addWidget(self.lbl_color)
        self.sl_color = QSlider(Qt.Horizontal); self.sl_color.setRange(-10, 360); self.sl_color.setValue(-10); row2.addWidget(self.sl_color)
        self.lbl_imgop = QLabel("IMG OPACITY")
        row2.addWidget(self.lbl_imgop)
        self.sl_imgop = QSlider(Qt.Horizontal); self.sl_imgop.setRange(0, 100); self.sl_imgop.setValue(30); row2.addWidget(self.sl_imgop)
        self.lbl_spec_color = QLabel("SPEC COLOR")
        row2.addWidget(self.lbl_spec_color)
        self.combo_spec = QComboBox()
        self.combo_spec.addItems(["Viridis", "Inferno", "Magma"])
        row2.addWidget(self.combo_spec)
        param.addLayout(row2)

        root.addWidget(param_panel)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.draw_overlay.resize(self.visualizer.widget.size())

    def _wire(self):
        self.btn_open.clicked.connect(self._open)
        self.btn_bg.clicked.connect(self._set_bg)
        self.btn_draw.clicked.connect(self._toggle_draw)
        self.draw_overlay.on_complete = self._handle_draw_complete
        self.btn_play.clicked.connect(self._toggle)
        self.btn_stop.clicked.connect(self._stop)
        self.vol.valueChanged.connect(self._vol_changed)
        self.seek.sliderPressed.connect(lambda: setattr(self, '_seeking', True))
        self.seek.sliderReleased.connect(self._seek_done)
        self.combo.currentTextChanged.connect(self._on_mode_changed)
        
        self.sl_sens.valueChanged.connect(lambda v: self._on_param_changed('sens', v))
        self.sl_speed.valueChanged.connect(lambda v: self._on_param_changed('speed', v))
        self.sl_comp.valueChanged.connect(lambda v: self._on_param_changed('comp', v))
        self.sl_color.valueChanged.connect(lambda v: self._on_param_changed('color', v))
        self.sl_imgop.valueChanged.connect(lambda v: self._on_param_changed('imgop', v))
        self.combo_spec.currentTextChanged.connect(lambda t: self._on_param_changed('spec', t))

    def _on_param_changed(self, param_key: str, val):
        mode = self.combo.currentText()
        if mode not in self._mode_params:
            self._mode_params[mode] = {'sens': 100, 'speed': 100, 'comp': 100, 'color': -10, 'imgop': 30, 'spec': 'Viridis'}
        if not self._updating_sliders:
            self._mode_params[mode][param_key] = val
            if param_key == 'sens': setattr(self.visualizer, 'p_sens', val / 100.0)
            elif param_key == 'speed': setattr(self.visualizer, 'p_speed', val / 100.0)
            elif param_key == 'comp': setattr(self.visualizer, 'p_comp', val / 100.0)
            elif param_key == 'color': setattr(self.visualizer, 'p_color', val)
            elif param_key == 'imgop': self.visualizer.set_bg_opacity(val / 100.0)
            elif param_key == 'spec': self.visualizer.set_spec_colormap(val)

    def _on_mode_changed(self, text):
        if text not in self._mode_params:
            self._mode_params[text] = {'sens': 100, 'speed': 100, 'comp': 100, 'color': -10, 'imgop': 30, 'spec': 'Viridis'}
        params = self._mode_params[text]
        self._updating_sliders = True
        self.sl_sens.setValue(params['sens'])
        self.sl_speed.setValue(params['speed'])
        self.sl_comp.setValue(params['comp'])
        self.sl_color.setValue(params['color'])
        self.sl_imgop.setValue(params['imgop'])
        self.combo_spec.setCurrentText(params['spec'])
        self._updating_sliders = False
        
        self.visualizer.p_sens = params['sens'] / 100.0
        self.visualizer.p_speed = params['speed'] / 100.0
        self.visualizer.p_comp = params['comp'] / 100.0
        self.visualizer.p_color = params['color']
        self.visualizer.set_bg_opacity(params['imgop'] / 100.0)
        self.visualizer.set_spec_colormap(params['spec'])
        self.visualizer.set_mode(text)

        # Show/hide controls where they are applicable
        uses_hue = text in ('Circle', 'EQ', 'Wave', 'Geometry', 'Custom', 'Image Circle', 'All Together')
        uses_imgop = text in ('Circle', 'EQ', 'Wave', 'Geometry', 'Custom')
        uses_spec = text in ('Spectrogram', 'All Together')
        
        self.lbl_color.setVisible(uses_hue)
        self.sl_color.setVisible(uses_hue)
        self.lbl_imgop.setVisible(uses_imgop)
        self.sl_imgop.setVisible(uses_imgop)
        self.lbl_spec_color.setVisible(uses_spec)
        self.combo_spec.setVisible(uses_spec)

    def _timers(self):
        self._vt = QTimer(self); self._vt.timeout.connect(self._vis_tick); self._vt.start(16)
        self._ut = QTimer(self); self._ut.timeout.connect(self._ui_tick); self._ut.start(80)

    def _vis_tick(self):
        now = time.perf_counter()
        self._ftimes.append(now)
        if len(self._ftimes) > 60: self._ftimes = self._ftimes[-60:]
        if len(self._ftimes) >= 2:
            dt = self._ftimes[-1] - self._ftimes[0]
            self._fps = (len(self._ftimes) - 1) / dt if dt > 0 else 0
        chunk = self.engine.get_current_chunk(2048)
        # Push stereo data so Ozone modes have L/R channels
        L, R = self.engine.get_stereo_chunk(2048)
        self.visualizer._stereo_L = L
        self.visualizer._stereo_R = R
        self.visualizer.update(chunk)

    def _ui_tick(self):
        self.lbl_fps.setText(f"{self._fps:.0f} FPS")
        if not self._seeking:
            self.lbl_cur.setText(_fmt(self.engine.get_position()))
            self.lbl_dur.setText(_fmt(self.engine.get_duration()))
            self.seek.setValue(int(self.engine.get_progress() * 10000))
        self.btn_play.setText("PAUSE" if self.engine.state == PlayState.PLAYING else "PLAY")

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio Files (*.wav *.flac *.ogg *.mp3)")
        if path: self._load(path)

    def _set_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.visualizer.set_background_image(path)
            
    def _toggle_draw(self):
        self.draw_overlay.show()
        self.draw_overlay.raise_()
        self.combo.setCurrentText("Custom Shape")

    def _handle_draw_complete(self, points):
        self.visualizer.set_custom_shape(points)

    def _load(self, path: str):
        if self.engine.load(path):
            self.lbl_title.setText(f"SIGMASCOPE  //  {os.path.basename(path).upper()}")
            self.lbl_file.setText(f"{self.engine.samplerate // 1000}KHZ   |   {_fmt(self.engine.get_duration())}")
            self.engine.play()

    def _toggle(self):
        if not self.engine.is_loaded(): self._open(); return
        self.engine.pause() if self.engine.state == PlayState.PLAYING else self.engine.play()

    def _stop(self): self.engine.stop()
    def _seek_done(self): self.engine.seek(self.seek.value() / 10000.0); self._seeking = False
    def _vol_changed(self, v): self.engine.set_volume(v / 100.0); self.lbl_vol.setText(f"{v}%")

    _EXTS = (".wav", ".flac", ".ogg", ".mp3")
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(self._EXTS) for u in e.mimeData().urls()):
            e.acceptProposedAction()
    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(self._EXTS): self._load(u.toLocalFile()); break

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space: self._toggle()
        elif e.key() == Qt.Key_Escape: self._stop()
        elif e.key() == Qt.Key_Right: self.engine.seek(min(self.engine.get_progress() + 0.02, 1.0))
        elif e.key() == Qt.Key_Left: self.engine.seek(max(self.engine.get_progress() - 0.02, 0.0))
        elif e.key() == Qt.Key_Up: self.vol.setValue(min(self.vol.value() + 5, 100))
        elif e.key() == Qt.Key_Down: self.vol.setValue(max(self.vol.value() - 5, 0))
        else: super().keyPressEvent(e)

    def closeEvent(self, e):
        self._vt.stop(); self._ut.stop(); self.engine.cleanup(); super().closeEvent(e)
