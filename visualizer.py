"""
SigmaScope – Visualization Engine v5
Fixed: inverted BG image, inverted EQ graph, color mixing.
Added: blend modes for background image.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt
from enum import Enum


class _BlendImageItem(pg.ImageItem):
    """
    ImageItem subclass that scopes its QPainter composition mode
    to only its own draw call, so other scene items are unaffected.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._comp_mode = QPainter.CompositionMode_SourceOver

    def setCompositionMode(self, mode):
        self._comp_mode = mode
        self.update()

    def paint(self, p, *args):
        p.save()
        p.setCompositionMode(self._comp_mode)
        super().paint(p, *args)
        p.restore()  # restores composition mode AND all other painter state


class VisMode(Enum):
    WAVE = 0
    CIRCLE = 1
    GEOMETRY = 2
    EQUALIZER = 3
    SPECTROGRAM = 4
    CUSTOM_SHAPE = 7
    IMAGE_CIRCLE = 8
    LISSAJOUS = 9
    POLAR_LEVEL = 11
    ALL_TOGETHER = 10


class Visualizer:
    def __init__(self):
        pg.setConfigOptions(antialias=True, useOpenGL=True)

        self.widget = pg.PlotWidget()
        self.widget.setBackground("#f4f4f0")
        self.widget.hideAxis("left")
        self.widget.hideAxis("bottom")
        self.widget.setMouseEnabled(False, False)
        self.widget.hideButtons()
        self.widget.setMenuEnabled(False)
        self.widget.getViewBox().setDefaultPadding(0)

        self.mode = VisMode.WAVE
        self._prev = None
        self._prev_fft = None
        self._peaks = None
        self._rot = 0.0
        
        self._avg_e = 0.0
        self._beat_e = 0.0
        
        self.p_sens = 1.0
        self.p_speed = 1.0
        self.p_comp = 1.0
        self.p_color = -10
        self.p_decay = 0.85
        self._last_color = -999
        self._blend_mode = "normal"  # current blend mode name

        self._xlin = np.linspace(0, 1, 1024, dtype=np.float32)
        self._angles = np.linspace(0, 2 * np.pi, 256, endpoint=False).astype(np.float32)

        # ── BG Image ──
        self._bg_img = _BlendImageItem()
        self._bg_img.setOpacity(0.3)
        self._bg_img.setZValue(-1)
        self.widget.addItem(self._bg_img)

        self._img_circle_item = _BlendImageItem()
        self._img_circle_item.setZValue(-1)
        self.widget.addItem(self._img_circle_item)

        # ── WAVE ──

        # 0 is the shadow/colored pencil, 1 is the graphite outline
        self._wave_curves = []
        self._wave_curves.append(self.widget.plot([], [], pen=pg.mkPen(color=(255, 100, 120, 180), width=6.0)))
        self._wave_curves.append(self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 255), width=4.0)))

        # Global Boil State
        self._boil_frame = 0
        self._boil_x = None
        self._boil_y = None
        self._boil_polar = None

        # ── CIRCLE ──
        self._circle_rings = []
        for i, (a, w) in enumerate([(255, 2.5), (150, 1.5), (80, 1.0)]):
            self._circle_rings.append(self.widget.plot([], [], pen=pg.mkPen(color=(255, 255, 255, a), width=w)))
        self._circle_fill = pg.PlotCurveItem(pen=pg.mkPen(color=(255, 255, 255, 0)), fillLevel=0, brush=pg.mkBrush(255, 255, 255, 15))
        self.widget.addItem(self._circle_fill)
        self._circle_chords = self.widget.plot([], [], pen=pg.mkPen(color=(255, 255, 255, 40), width=1.0))
        # Trail curves for circle (afterglow)
        self._circle_trails = []
        for i in range(3):
            a = int(100 - i * 30)
            self._circle_trails.append(self.widget.plot([], [], pen=pg.mkPen(color=(255, 255, 255, a), width=1.0)))
        self._circle_trail_hist = []

        # ── GEOMETRY ──
        self._polys = []
        for i in range(5):
            a = int(255 - (i * 40))
            w = 2.5 if i == 0 else 1.5
            self._polys.append(self.widget.plot([], [], pen=pg.mkPen(color=(255, 255, 255, a), width=w)))
        self._geo_web = self.widget.plot([], [], pen=pg.mkPen(color=(255, 255, 255, 25), width=1.0))
        # Trail curves for geometry (afterglow)
        self._geo_trails = []
        for i in range(3):
            a = int(80 - i * 25)
            self._geo_trails.append(self.widget.plot([], [], pen=pg.mkPen(color=(255, 255, 255, a), width=1.0)))
        self._geo_trail_hist = []

        # ── EQUALIZER (Parametric EQ Style) ──
        self._eq_fill = pg.PlotCurveItem(pen=pg.mkPen(color=(255, 255, 255, 0)), fillLevel=0, brush=pg.mkBrush(150, 160, 170, 70))
        self.widget.addItem(self._eq_fill)
        self._eq_line = self.widget.plot([], [], pen=pg.mkPen(color=(220, 230, 240, 255), width=2.5))
        
        band_colors = [
            (148, 0, 211),   # 1: Purple (Sub)
            (255, 0, 255),   # 2: Magenta (Bass)
            (255, 69, 0),    # 3: Orange (Low Mid)
            (255, 215, 0),   # 4: Yellow (Mid)
            (0, 255, 0),     # 5: Green (High Mid)
            (0, 255, 255),   # 6: Cyan (Presence)
            (0, 100, 255),   # 7: Blue (Treble)
        ]
        self._eq_tokens = []
        for i, col in enumerate(band_colors):
            tok = self.widget.plot([], [], pen=pg.mkPen(color=(*col, 200), width=2.5), symbol='o', symbolSize=16, symbolBrush=pg.mkBrush(30, 34, 41, 200))
            self._eq_tokens.append(tok)
            
        self._eq_max_y = 0.0

        # ── SPECTROGRAM ──
        self._spec_img = pg.ImageItem()
        self.widget.addItem(self._spec_img)
        self._spec_y_res = 256
        self._spec_history = np.zeros((400, self._spec_y_res), dtype=np.float32)
        self._apply_spec_colormap('Inferno')

        # ── LISSAJOUS (legacy) ──
        self._lissajous = self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 180), width=1.0))

        # ── GRID ──
        self._grid_pts = pg.ScatterPlotItem(size=5, pxMode=True, pen=pg.mkPen(None), brush=pg.mkBrush(43, 43, 43, 200))
        self.widget.addItem(self._grid_pts)

        # ── CUSTOM SHAPE ──
        self._custom_base = None
        self._custom_normals = None
        self._custom_curve = self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 220), width=1.5))
        self._custom_chords = self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 30), width=1.0))

        # ── OZONE LISSAJOUS ──
        # 3 trail layers (oldest → most transparent) + bright current
        self._liss_trails = []
        for i in range(4):
            alpha = int(220 - i * 50)
            w = 1.5 - i * 0.3
            self._liss_trails.append(
                self.widget.plot([], [], pen=pg.mkPen(color=(78, 205, 196, alpha), width=max(0.5, w)))
            )
        self._liss_diamond = self.widget.plot([], [], pen=pg.mkPen(color=(180, 200, 210, 60), width=1.0))
        self._liss_crosshair_h = self.widget.plot([], [], pen=pg.mkPen(color=(180, 200, 210, 40), width=0.8))
        self._liss_crosshair_v = self.widget.plot([], [], pen=pg.mkPen(color=(180, 200, 210, 40), width=0.8))
        self._liss_hist = []  # rolling buffer of (x, y) arrays

        # ── POLAR LEVEL ──
        # arc reference lines
        self._polar_arc = self.widget.plot([], [], pen=pg.mkPen(color=(180, 200, 210, 50), width=1.0))
        self._polar_lr_line = self.widget.plot([], [], pen=pg.mkPen(color=(180, 200, 210, 50), width=1.0))
        self._polar_guide_arcs = [self.widget.plot([], [], pen=pg.mkPen(color=(180, 200, 210, 25), width=0.8))
                                   for _ in range(2)]
        # filled spikes
        self._polar_fill = pg.PlotCurveItem(
            pen=pg.mkPen(color=(78, 205, 196, 200), width=1.5),
            fillLevel=0, brush=pg.mkBrush(78, 205, 196, 80)
        )
        self.widget.addItem(self._polar_fill)
        self._polar_outline = self.widget.plot([], [], pen=pg.mkPen(color=(140, 230, 225, 255), width=2.0))

        # ── ALL mode: sketchbook quadrant borders + labels ──
        # 4 rectangle borders (each as a closed polygon)
        self._all_borders = [self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 80),
                                                                    width=1.5,
                                                                    style=Qt.SolidLine))
                             for _ in range(4)]
        # Divider lines
        self._all_div_v = self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 60), width=1.0,
                                                                 style=Qt.DashLine))
        self._all_div_h = self.widget.plot([], [], pen=pg.mkPen(color=(43, 43, 43, 60), width=1.0,
                                                                 style=Qt.DashLine))
        # Section labels
        _lbl_font = pg.QtGui.QFont('Inter', 8, pg.QtGui.QFont.Bold)
        _lbl_color = (80, 80, 80, 160)
        self._all_labels = []
        for txt in ('CIRCLE', 'GEOMETRY', 'EQ', 'WAVE'):
            ti = pg.TextItem(text=txt, color=_lbl_color, anchor=(0, 0))
            ti.setFont(_lbl_font)
            self.widget.addItem(ti)
            self._all_labels.append(ti)

        self._hide_all()

    def set_bg_opacity(self, alpha):
        self._bg_img.setOpacity(alpha)

    # ─── Spectrogram colormaps ───────────────────────────────────────
    _SPEC_CMAPS = {
        'Inferno': [
            [0,   [10,  0,   20,  255]],
            [0.25,[120, 0,   80,  255]],
            [0.5, [220, 60,  0,   255]],
            [0.75,[255, 180, 20,  255]],
            [1.0, [255, 255, 200, 255]],
        ],
        'Viridis': [
            [0,   [68,  1,   84,  255]],
            [0.25,[59,  82,  139, 255]],
            [0.5, [33,  144, 141, 255]],
            [0.75,[93,  201, 98,  255]],
            [1.0, [253, 231, 37,  255]],
        ],
        'Plasma': [
            [0,   [13,  8,   135, 255]],
            [0.25,[126, 3,   168, 255]],
            [0.5, [204, 71,  120, 255]],
            [0.75,[248, 149, 64,  255]],
            [1.0, [240, 249, 33,  255]],
        ],
        'Magma': [
            [0,   [0,   0,   4,   255]],
            [0.25,[81,  18,  124, 255]],
            [0.5, [183, 55,  121, 255]],
            [0.75,[251, 136, 97,  255]],
            [1.0, [252, 253, 191, 255]],
        ],
        'Ocean': [
            [0,   [0,   10,  30,  255]],
            [0.33,[0,   60,  120, 255]],
            [0.66,[0,   160, 180, 255]],
            [1.0, [200, 240, 255, 255]],
        ],
        'Sunset': [
            [0,   [20,  0,   40,  255]],
            [0.33,[160, 0,   100, 255]],
            [0.66,[255, 120, 0,   255]],
            [1.0, [255, 240, 80,  255]],
        ],
    }

    def _apply_spec_colormap(self, name: str):
        stops = self._SPEC_CMAPS.get(name, self._SPEC_CMAPS['Inferno'])
        pos   = np.array([s[0] for s in stops])
        color = np.array([s[1] for s in stops], dtype=np.ubyte)
        cmap  = pg.ColorMap(pos, color)
        self._spec_img.setLookupTable(cmap.getLookupTable(nPts=256))

    def set_spec_colormap(self, name: str):
        self._apply_spec_colormap(name)

    # ── Blend mode names mapped to Qt.CompositionMode ──
    BLEND_MODES = {
        "normal":      QPainter.CompositionMode_SourceOver,
        "multiply":    QPainter.CompositionMode_Multiply,
        "screen":      QPainter.CompositionMode_Screen,
        "overlay":     QPainter.CompositionMode_Overlay,
        "color burn":  QPainter.CompositionMode_ColorBurn,
        "color dodge": QPainter.CompositionMode_ColorDodge,
        "hard light":  QPainter.CompositionMode_HardLight,
        "soft light":  QPainter.CompositionMode_SoftLight,
        "difference":  QPainter.CompositionMode_Difference,
        "exclusion":   QPainter.CompositionMode_Exclusion,
        "lighten":     QPainter.CompositionMode_Lighten,
        "darken":      QPainter.CompositionMode_Darken,
    }

    def set_blend_mode(self, mode_name: str):
        """Apply a named blend mode to the background image."""
        self._blend_mode = mode_name.lower()
        comp = self.BLEND_MODES.get(self._blend_mode, QPainter.CompositionMode_SourceOver)
        self._bg_img.setCompositionMode(comp)

    def set_background_image(self, path):
        img = QImage(path).convertToFormat(QImage.Format_RGBA8888)
        width, height = img.width(), img.height()
        ptr = img.bits()
        arr = np.array(ptr).reshape(height, width, 4)

        # ── Fix: pyqtgraph uses Y-up, so flip vertically before transposing ──
        arr = np.flipud(arr)

        # Circular Mask (from the non-flipped square for the circle item)
        # Use original orientation then flip
        img_orig = QImage(path).convertToFormat(QImage.Format_RGBA8888)
        ptr2 = img_orig.bits()
        arr_orig = np.array(ptr2).reshape(height, width, 4)
        size = min(width, height)
        sy = (height - size) // 2
        sx = (width - size) // 2
        square = arr_orig[sy:sy+size, sx:sx+size].copy()
        square = np.flipud(square)  # flip vertically for Y-up

        Y, X = np.ogrid[:size, :size]
        center = size / 2.0
        dist_from_center = np.sqrt((X - center)**2 + (Y - center)**2)
        mask = dist_from_center <= center
        square[~mask, 3] = 0

        # Transpose from (H, W, 4) → (W, H, 4) for pyqtgraph ImageItem
        self._img_circle_item.setImage(np.ascontiguousarray(np.swapaxes(square, 0, 1)))

        # Standard BG – transpose axes for pyqtgraph
        arr = np.ascontiguousarray(np.swapaxes(arr, 0, 1))
        self._bg_img.setImage(arr)

        # Re-apply blend mode after image is set
        self.set_blend_mode(self._blend_mode)

    def set_custom_shape(self, points):
        """points: list of (x,y) tuples normalized between 0 and 1."""
        if len(points) < 3:
            return
        
        # Map 0..1 to -4..4 range for visualizer
        pts = np.array(points)
        pts = (pts * 8.0) - 4.0
        
        # Resample path to fixed number of vertices (e.g. 256)
        x, y = pts[:, 0], pts[:, 1]
        
        # Calculate cumulative distance along path
        dx = np.diff(x)
        dy = np.diff(y)
        dist = np.concatenate(([0], np.cumsum(np.hypot(dx, dy))))
        
        # Filter duplicate points
        valid = np.concatenate(([True], dist[1:] > dist[:-1]))
        if not np.any(valid): return
        x = x[valid]
        y = y[valid]
        dist = dist[valid]
        
        if dist[-1] == 0:
            return
            
        # Interpolate
        new_dist = np.linspace(0, dist[-1], 256)
        new_x = np.interp(new_dist, dist, x)
        new_y = np.interp(new_dist, dist, y)
        
        self._custom_base = np.column_stack((new_x, new_y))
        
        # Calculate normals
        nx = np.gradient(new_x)
        ny = np.gradient(new_y)
        normals = np.column_stack((-ny, nx))
        
        # Normalize vectors
        norms = np.linalg.norm(normals, axis=1)
        norms[norms == 0] = 1.0
        self._custom_normals = normals / norms[:, np.newaxis]
        
        self.set_mode(VisMode.CUSTOM_SHAPE)

    def set_mode(self, mode):
        if isinstance(mode, str):
            try:
                mode = VisMode[mode.upper().replace(' ', '_')]
            except KeyError:
                return
        self.mode = mode
        self._prev = None
        self._prev_fft = None
        self._peaks = None
        self._spec_history.fill(0)
        self._hide_all()

    def update(self, chunk: np.ndarray):
        if chunk is None or len(chunk) < 4:
            return

        d = chunk.astype(np.float32)
        if self._prev is not None and len(self._prev) == len(d):
            d = 0.3 * self._prev + 0.7 * d
        self._prev = d.copy()

        # Stereo data is injected from outside via update_stereo()
        # Default: synthesise from mono when not provided
        if not hasattr(self, '_stereo_L') or self._stereo_L is None:
            delay = len(d) // 4
            self._stereo_L = d.copy()
            self._stereo_R = np.roll(d, delay)

        rms = float(np.sqrt(np.mean(d * d)))
        self._beat(rms)
        
        # Global Boil Update
        self._boil_frame += 1
        fps_throttle = max(1, int(8 / max(0.1, self.p_speed)))
        if self._boil_x is None or self._boil_frame % fps_throttle == 0:
            num_nodes = max(8, int(32 * self.p_comp))
            noise_x = np.random.uniform(-0.015, 0.015, num_nodes)
            noise_y = np.random.uniform(-0.15, 0.15, num_nodes)
            self._boil_x = np.interp(np.linspace(0, 1, 1024), np.linspace(0, 1, num_nodes), noise_x)
            self._boil_y = np.interp(np.linspace(0, 1, 1024), np.linspace(0, 1, num_nodes), noise_y)
            
            # Polar boil (Seamless loop where first and last match perfectly)
            p_noise = np.random.uniform(-0.15, 0.15, num_nodes)
            p_noise[-1] = p_noise[0]
            self._boil_polar = np.interp(np.linspace(0, 1, 1024), np.linspace(0, 1, num_nodes), p_noise)

        m = self.mode
        if   m == VisMode.WAVE:           self._draw_wave(d, rms)
        elif m == VisMode.CIRCLE:         self._draw_circle(d, rms)
        elif m == VisMode.GEOMETRY:       self._draw_geometry(d, rms)
        elif m == VisMode.EQUALIZER:      self._draw_eq(chunk)
        elif m == VisMode.SPECTROGRAM:    self._draw_spec(chunk)
        elif m == VisMode.CUSTOM_SHAPE:   self._draw_custom(d, rms)
        elif m == VisMode.IMAGE_CIRCLE:   self._draw_img_circle(d, rms)
        elif m == VisMode.LISSAJOUS:     self._draw_lissajous_ozone(chunk)
        elif m == VisMode.POLAR_LEVEL:    self._draw_polar_level(chunk)
        elif m == VisMode.ALL_TOGETHER:   self._draw_all(d, chunk, rms)
        
        self._update_colors()
        self._update_bg_rect()

    def _update_colors(self):
        if self.p_color == self._last_color: return
        self._last_color = self.p_color
        
        if self.p_color < 0:
            base = (255, 100, 120)
        else:
            c = pg.hsvColor(self.p_color / 360.0)
            base = (c.red(), c.green(), c.blue())
            
        graphite = (43, 43, 43, 255)
            
        self._wave_curves[0].setPen(pg.mkPen(color=(*base, 180), width=6.0))
        self._wave_curves[1].setPen(pg.mkPen(color=graphite, width=4.0))
        
        for i, c in enumerate(self._circle_rings): c.setPen(pg.mkPen(color=graphite, width=[3.0, 2.0, 1.5][i]))
        for i, c in enumerate(self._circle_trails): c.setPen(pg.mkPen(color=(*base, int(150 - i*40)), width=[4.0, 3.0, 2.0][i]))
        self._circle_fill.setBrush(pg.mkBrush(*base, 40))
        self._circle_chords.setPen(pg.mkPen(color=(*base, 100), width=2.0))
        
        for i, c in enumerate(self._polys): c.setPen(pg.mkPen(color=graphite, width=(3.0 if i==0 else 2.0)))
        for i, c in enumerate(self._geo_trails): c.setPen(pg.mkPen(color=(*base, int(120 - i*30)), width=[3.0, 2.0, 1.5][i]))
        self._geo_web.setPen(pg.mkPen(color=(*base, 100), width=2.0))
        
        self._custom_curve.setPen(pg.mkPen(color=graphite, width=3.0))
        self._custom_chords.setPen(pg.mkPen(color=(*base, 100), width=2.0))
        
        self._eq_fill.setBrush(pg.mkBrush(*base, 90))
        self._eq_line.setPen(pg.mkPen(color=graphite, width=4.0))

    def _update_bg_rect(self):
        # Scale background image to fit the current view range
        if self._bg_img.image is not None:
            rect = self.widget.getViewBox().viewRect()
            self._bg_img.setRect(rect)

    def _beat(self, rms):
        self._avg_e = 0.95 * self._avg_e + 0.05 * rms
        hit = rms > self._avg_e * 1.5 and rms > 0.02
        if hit:
            self._beat_e = min(1.0, rms * 4.0)
        else:
            self._beat_e *= self.p_decay

    def _draw_wave(self, d, rms, ox=0, oy=0, scale=1.0, is_all=False):
        if not is_all: self._hide_all_but('wave')
        step = max(1, len(d) // 512)
        v = d[::step]
        # Map X from -1 to 1 for easier ALL mode integration
        x = np.linspace(-1, 1, len(v), dtype=np.float32) * scale + ox
        amp = (2.0 + self._beat_e * 2.0) * self.p_sens * scale
        
        b_x = self._boil_x[:len(v)] * scale
        b_y = self._boil_y[:len(v)] * scale
        
        base_y = v * amp + oy
        final_x = x + b_x
        final_y = base_y + b_y
        
        # Colored pencil shading slightly offset
        offset_x = (0.005 + (b_x[::-1] * 0.3)) * scale
        offset_y = (-0.05 + (b_y[::-1] * 0.3)) * scale
        
        self._wave_curves[0].setData(final_x + offset_x, final_y + offset_y)
        self._wave_curves[1].setData(final_x, final_y)

        if not is_all:
            self.widget.setXRange(-1, 1, padding=0)
            self.widget.setYRange(-3.5, 3.5, padding=0)

    def _draw_circle(self, d, rms, ox=0, oy=0, scale=1.0, is_all=False):
        if not is_all: self._hide_all_but('circle')
        step = max(1, len(d) // 256)
        v = d[::step][:256] * self.p_sens
        
        self._rot += (0.003 + rms * 0.015) * self.p_speed
        ang = self._angles[:len(v)] + self._rot
        
        base_r = 1.5 + self._beat_e * 0.8
        
        b_r = self._boil_polar[:len(v)] * scale # Polar wiggle applied to radius!
        
        # Number of visible rings controlled by complexity
        num_rings = min(3, max(1, int(self.p_comp * 2)))
        
        # Ring 0: Main outer ring
        rad0 = (base_r + v * (2.0 + rms * 3.0)) * scale + b_r
        cx0 = rad0 * np.cos(ang) + ox
        cy0 = rad0 * np.sin(ang) + oy
        self._circle_rings[0].setData(np.append(cx0, cx0[0]), np.append(cy0, cy0[0]))
        
        # Ring 1: Mid ring
        if num_rings >= 2:
            rad1 = (base_r * 0.7 + np.roll(v, 20) * (1.2 + rms * 1.5)) * scale + b_r
            cx1 = rad1 * np.cos(ang - self._rot * 0.3) + ox
            cy1 = rad1 * np.sin(ang - self._rot * 0.3) + oy
            self._circle_rings[1].setData(np.append(cx1, cx1[0]), np.append(cy1, cy1[0]))
            self._circle_rings[1].setVisible(True)
        else:
            self._circle_rings[1].setVisible(False)
        
        # Ring 2: Inner ring
        if num_rings >= 3:
            rad2 = (base_r * 0.35 + np.abs(v) * 0.5) * scale + b_r
            cx2 = rad2 * np.cos(ang + self._rot * 0.5) + ox
            cy2 = rad2 * np.sin(ang + self._rot * 0.5) + oy
            self._circle_rings[2].setData(np.append(cx2, cx2[0]), np.append(cy2, cy2[0]))
            self._circle_rings[2].setVisible(True)
        else:
            self._circle_rings[2].setVisible(False)
        
        # Glow fill
        self._circle_fill.setData(np.append(cx0, cx0[0]), np.append(cy0, cy0[0]))
        
        # Chords
        ch_x, ch_y = [], []
        if num_rings >= 3:
            skip = max(4, int(16 * self.p_comp))
            for i in range(0, len(cx0), skip):
                if abs(v[i]) > 0.03 or self._beat_e > 0.15:
                    ch_x.extend([cx0[i], cx2[i]])
                    ch_y.extend([cy0[i], cy2[i]])
        self._circle_chords.setData(ch_x, ch_y)
        
        # Trails (afterglow of previous frames)
        self._circle_trail_hist.append((np.append(cx0, cx0[0]).copy(), np.append(cy0, cy0[0]).copy()))
        max_trails = max(1, int(self.p_decay * 5))
        while len(self._circle_trail_hist) > max_trails:
            self._circle_trail_hist.pop(0)
        for i, trail in enumerate(self._circle_trails):
            idx = len(self._circle_trail_hist) - 2 - i
            if idx >= 0:
                tx, ty = self._circle_trail_hist[idx]
                trail.setData(tx, ty)
                trail.setVisible(True)
            else:
                trail.setVisible(False)

        if not is_all:
            self.widget.setXRange(-5, 5, padding=0)
            self.widget.setYRange(-5, 5, padding=0)

    def _draw_geometry(self, d, rms, ox=0, oy=0, scale=1.0, is_all=False):
        if not is_all: self._hide_all_but('geometry')
        # Complexity directly controls polygon sides (3=triangle to 12=dodecagon)
        n_verts = max(3, int(3 + self.p_comp * 5) + int(self._beat_e * 4))
        step = max(1, len(d) // n_verts)
        self._rot -= (0.008 + rms * 0.02) * self.p_speed
        
        # Number of visible layers controlled by complexity
        num_layers = min(5, max(2, int(self.p_comp * 3 + 1)))
        
        b_r = self._boil_polar[:n_verts] * scale # Polar wiggle for vertices
        
        all_cx, all_cy = [], []
        outer_cx, outer_cy = None, None
        for i, poly in enumerate(self._polys):
            if i >= num_layers:
                poly.setVisible(False)
                continue
            poly.setVisible(True)
            layer_scale = (0.5 + (i * 0.6) + (self._beat_e * 0.3 * i)) * scale
            v = np.array([np.mean(np.abs(d[j*step:(j+1)*step])) for j in range(n_verts)]) * self.p_sens
            ang = np.linspace(0, 2 * np.pi, n_verts, endpoint=False) + self._rot * (1 if i%2==0 else -1)
            rad = layer_scale + (v * 2.5 * scale) + b_r
            
            cx = rad * np.cos(ang) + ox
            cy = rad * np.sin(ang) + oy
            poly.setData(np.append(cx, cx[0]), np.append(cy, cy[0]))
            all_cx.append(cx)
            all_cy.append(cy)
            if i == 0:
                outer_cx, outer_cy = np.append(cx, cx[0]).copy(), np.append(cy, cy[0]).copy()
        
        # Web connections
        web_x, web_y = [], []
        for layer in range(len(all_cx) - 1):
            n = min(len(all_cx[layer]), len(all_cx[layer+1]))
            for j in range(0, n, max(1, int(3 * self.p_comp))):
                web_x.extend([all_cx[layer][j], all_cx[layer+1][j]])
                web_y.extend([all_cy[layer][j], all_cy[layer+1][j]])
        self._geo_web.setData(web_x, web_y)
        
        # Trails (afterglow of outermost polygon)
        if outer_cx is not None:
            self._geo_trail_hist.append((outer_cx, outer_cy))
        max_trails = max(1, int(self.p_decay * 5))
        while len(self._geo_trail_hist) > max_trails:
            self._geo_trail_hist.pop(0)
        for i, trail in enumerate(self._geo_trails):
            idx = len(self._geo_trail_hist) - 2 - i
            if idx >= 0:
                tx, ty = self._geo_trail_hist[idx]
                trail.setData(tx, ty)
                trail.setVisible(True)
            else:
                trail.setVisible(False)

        if not is_all:
            self.widget.setXRange(-5, 5, padding=0)
            self.widget.setYRange(-5, 5, padding=0)

    def _get_fft(self, chunk, bins):
        n = min(len(chunk), 4096)
        fft = np.abs(np.fft.rfft(chunk[:n] * np.hanning(n)))
        useful = int(len(fft) * 0.5)
        fft = fft[1:useful]
        
        idx = np.unique(np.logspace(0, np.log10(len(fft)), bins + 1, dtype=int).clip(0, len(fft) - 1))
        actual_bins = len(idx) - 1
        
        bars = np.empty(actual_bins, dtype=np.float32)
        for i in range(actual_bins):
            bars[i] = fft[idx[i]:max(idx[i+1], idx[i]+1)].mean()
            
        # Logarithmic scaling that strictly maps 0 to 0 and gracefully compresses loud peaks
        bars = 30 * np.log10(bars * 5 + 1)
        bars = np.clip(bars, 0, 150)
        
        if actual_bins != bins and actual_bins > 1:
            x_old = np.linspace(0, 1, actual_bins)
            x_new = np.linspace(0, 1, bins)
            bars = np.interp(x_new, x_old, bars)
            actual_bins = bins
            
        return bars, actual_bins

    def _draw_eq(self, chunk, ox=0, oy=0, scale=1.0, is_all=False):
        if not is_all: self._hide_all_but('eq')

        target_bins = 256
        bars, num_bins = self._get_fft(chunk, target_bins)

        # Apply sensitivity offset to dB
        bars = bars + (self.p_sens - 1.0) * 10

        if self._prev_fft is not None and self._prev_fft.shape == bars.shape:
            bars = 0.4 * self._prev_fft + 0.6 * bars
        self._prev_fft = bars.copy()

        kernel_size = max(3, int(15 / self.p_comp))
        kernel = np.ones(kernel_size) / kernel_size
        smooth_bars = np.convolve(bars, kernel, mode='same')
        smooth_bars = smooth_bars + 3.0

        # Map x to [-1, 1] for ALL mode; y is always upward from baseline
        x = np.linspace(-1, 1, num_bins) * scale + ox
        # Bars grow UP from oy (positive y = upward in pyqtgraph)
        baseline = oy
        y_bars = (bars / 100.0) * scale + baseline
        y_smooth = (smooth_bars / 100.0) * scale + baseline

        # fillLevel must match the baseline so the fill goes upward
        self._eq_fill.setFillLevel(baseline)
        self._eq_fill.setData(x, y_bars)
        self._eq_line.setData(x, y_smooth)

        token_indices = np.linspace(kernel_size, num_bins - kernel_size - 1, 7, dtype=int)
        for i, tok in enumerate(self._eq_tokens):
            idx = token_indices[i]
            tok.setData([x[idx]], [y_smooth[idx]])

        if not is_all:
            self.widget.setXRange(-1, 1, padding=0)
            self.widget.setYRange(0, 1.1, padding=0)

    def _draw_spec(self, chunk):
        self._hide_all_but('spec')
        bars, _ = self._get_fft(chunk, self._spec_y_res)
        
        # Normalize for intensity (sensitivity controls brightness)
        bars = bars * self.p_sens * 1.5
        bars = np.clip(bars, 0, 255)
        
        scroll = max(1, int(1 * self.p_speed))
        self._spec_history = np.roll(self._spec_history, -scroll, axis=0)
        self._spec_history[-scroll:] = bars
        
        img = np.clip(self._spec_history, 0, 255).astype(np.ubyte)
        self._spec_img.setImage(img, autoLevels=False)
        
        self.widget.setXRange(0, 400, padding=0)
        self.widget.setYRange(0, self._spec_y_res, padding=0)

    def _draw_lissajous(self, d):
        self._hide_all_but('lissajous')
        delay = int(len(d) * 0.25)
        x = d[:-delay] * (3.0 + self._beat_e) * self.p_sens
        y = d[delay:] * (3.0 + self._beat_e) * self.p_sens
        self._lissajous.setData(x, y)
        self.widget.setXRange(-4, 4, padding=0)
        self.widget.setYRange(-4, 4, padding=0)

    def _draw_lissajous_ozone(self, chunk):
        """Goniometer / Lissajous: Ozone Imager style.
        L on left (-x), R on right (+x), Mono up (+y).
        """
        self._hide_all_but('lissajous')
        self.widget.setBackground('#0d1117')

        L = self._stereo_L.astype(np.float32)
        R = self._stereo_R.astype(np.float32)
        n = min(len(L), len(R))
        L, R = L[:n], R[:n]

        # Mid-Side transform (goniometer axes)
        sq2 = np.sqrt(2.0)
        # R gives +x, L gives -x. Mono (L=R) gives 0.
        x_ms = (R - L) / sq2
        y_ms = (L + R) / sq2

        # Clamp to avoid overflow; scale with sensitivity
        clip = 3.0
        x_ms = np.clip(x_ms * self.p_sens, -clip, clip)
        y_ms = np.clip(y_ms * self.p_sens, -clip, clip)

        # Rolling history for trails (decay-controlled length)
        self._liss_hist.append((x_ms.copy(), y_ms.copy()))
        keep = max(2, min(8, int(self.p_decay * 8)))
        while len(self._liss_hist) > keep:
            self._liss_hist.pop(0)

        for i, trail in enumerate(self._liss_trails):
            idx = len(self._liss_hist) - 1 - i
            if idx >= 0:
                trail.setData(self._liss_hist[idx][0], self._liss_hist[idx][1])
                trail.setVisible(True)
            else:
                trail.setVisible(False)

        # Diamond frame (rotated square) — Ozone's characteristic frame
        r = clip
        self._liss_diamond.setData([0, r, 0, -r, 0], [r, 0, -r, 0, r])
        self._liss_diamond.setVisible(True)
        # Crosshairs
        self._liss_crosshair_h.setData([-r, r], [0, 0])
        self._liss_crosshair_v.setData([0, 0], [-r, r])
        self._liss_crosshair_h.setVisible(True)
        self._liss_crosshair_v.setVisible(True)

        self.widget.setXRange(-r * 1.05, r * 1.05, padding=0)
        self.widget.setYRange(-r * 1.05, r * 1.05, padding=0)

    def _draw_polar_level(self, chunk):
        """Ozone Polar Level: energy distributed around a semicircle.
        Centre-top = mono. Bottom-left = L. Bottom-right = R.
        """
        self._hide_all_but('polar_level')
        self.widget.setBackground('#0d1117')

        L = self._stereo_L.astype(np.float32)
        R = self._stereo_R.astype(np.float32)
        n = min(len(L), len(R))
        L, R = L[:n], R[:n]

        eps = 1e-9
        L_abs = np.abs(L)
        R_abs = np.abs(R)
        mag = np.sqrt(L**2 + R**2)

        # Angle from 0 (pure R) to pi/2 (pure L)
        ang = np.arctan2(L_abs + eps, R_abs + eps)
        # Map to display angle from 0 (Right, +x) to pi (Left, -x)
        display_ang = ang * 2.0

        n_bins = 256
        bin_edges = np.linspace(0, np.pi, n_bins + 1)
        energy = np.zeros(n_bins, dtype=np.float32)
        bin_idx = np.clip(np.digitize(display_ang, bin_edges) - 1, 0, n_bins - 1)
        # Use maximum amplitude per bin to create an envelope
        np.maximum.at(energy, bin_idx, mag)

        # Smooth and temporal decay
        kernel = np.ones(5) / 5
        energy = np.convolve(energy, kernel, mode='same')
        
        if not hasattr(self, '_polar_prev'): self._polar_prev = energy.copy()
        energy = 0.65 * self._polar_prev + 0.35 * energy
        self._polar_prev = energy.copy()

        # Scale for display
        max_r = 3.0 * (1.0 + self._beat_e * 0.2)
        energy = np.clip(energy * 2.5 * self.p_sens, 0, max_r)

        # Build polygon: angle 0→R(bottom-right), pi→L(bottom-left)
        theta = np.linspace(0, np.pi, n_bins)
        # cos(0)=1(R), cos(pi)=-1(L), sin(pi/2)=1(Mono)
        px = energy * np.cos(theta)
        py = energy * np.sin(theta)

        # Close through origin
        px_c = np.concatenate([[0], px, [0]])
        py_c = np.concatenate([[0], py, [0]])
        self._polar_fill.setData(px_c, py_c)
        self._polar_fill.setVisible(True)
        self._polar_outline.setData(px, py)
        self._polar_outline.setVisible(True)

        # Reference arcs and diagonal guide lines
        t_arc = np.linspace(0, np.pi, 200)
        self._polar_arc.setData(max_r * np.cos(t_arc), max_r * np.sin(t_arc))
        self._polar_arc.setVisible(True)
        self._polar_lr_line.setData([-max_r, max_r], [0, 0])
        self._polar_lr_line.setVisible(True)
        
        # 2 Diagonal lines separating L/Mid and R/Mid
        angles = [np.pi/4, 3*np.pi/4]
        for i, guide in enumerate(self._polar_guide_arcs):
            if i < len(angles):
                gx = [0, max_r * np.cos(angles[i])]
                gy = [0, max_r * np.sin(angles[i])]
                guide.setData(gx, gy)
                guide.setVisible(True)

        span = max_r * 1.1
        self.widget.setXRange(-span, span, padding=0)
        self.widget.setYRange(-0.3, span, padding=0)

    def _draw_grid(self, chunk, rms):
        self._hide_all_but('grid')
        
        grid_size = 16
        bars, _ = self._get_fft(chunk, grid_size * grid_size)
        
        # 16x16 grid
        x, y = np.meshgrid(np.arange(grid_size), np.arange(grid_size))
        x = x.flatten()
        y = y.flatten()
        
        # Size based on frequency amplitude + global beat
        sizes = (bars * 4.0) + (self._beat_e * 2.0)
        sizes = np.clip(sizes, 1.0, 20.0)
        
        self._grid_pts.setData(x=x, y=y, size=sizes)
        self.widget.setXRange(-1, grid_size, padding=0)
        self.widget.setYRange(-1, grid_size, padding=0)

    def _draw_custom(self, d, rms, ox=0, oy=0, scale=1.0, is_all=False):
        if not is_all: self._hide_all_but('custom')
        if self._custom_base is None:
            return
            
        step = max(1, len(d) // 256)
        v = d[::step][:256]
        
        if len(v) < len(self._custom_base):
            v = np.pad(v, (0, len(self._custom_base) - len(v)))
        elif len(v) > len(self._custom_base):
            v = v[:len(self._custom_base)]
            
        amp = v * (1.0 + self._beat_e * 1.5) * self.p_sens
        
        b_r = self._boil_polar[:len(v)] * scale # Polar wiggle
        
        pts = self._custom_base * scale + self._custom_normals * ((amp[:, np.newaxis] * scale) + b_r[:, np.newaxis])
        x = pts[:, 0] + ox
        y = pts[:, 1] + oy
        
        self._custom_curve.setData(np.append(x, x[0]), np.append(y, y[0]))
        
        ch_x, ch_y = [], []
        skip = int(17 * self.p_comp)
        if skip > 0:
            for i in range(len(x)):
                next_i = (i + skip) % len(x)
                if abs(v[i]) > 0.05 or self._beat_e > 0.15:
                    ch_x.extend([x[i], x[next_i]])
                    ch_y.extend([y[i], y[next_i]])
        self._custom_chords.setData(ch_x, ch_y)

        if not is_all:
            self.widget.setXRange(-5, 5, padding=0)
            self.widget.setYRange(-5, 5, padding=0)

    def _draw_all(self, d, chunk, rms):
        self._hide_all_but('all')
        W, H = 4.6, 4.6
        self.widget.setXRange(-W, W, padding=0)
        self.widget.setYRange(-H, H, padding=0)

        pad = 0.18   # gap between border and content
        bpad = 0.08  # border inset from centre lines

        # Quadrant cell half-sizes
        cw = W - bpad   # half total width  → each cell = W wide
        ch = H - bpad   # half total height → each cell = H tall
        # Centre of each quadrant
        qx = W / 2
        qy = H / 2

        # Draw sketchbook borders (closed rectangle for each quadrant)
        def _rect(x0, y0, x1, y1):
            return ([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0])

        for i, (qox, qoy) in enumerate([(-qx, qy), (qx, qy), (-qx, -qy), (qx, -qy)]):
            margin = 0.12
            rx0, ry0 = qox - (W/2 - margin), qoy - (H/2 - margin)
            rx1, ry1 = qox + (W/2 - margin), qoy + (H/2 - margin)
            bx, by = _rect(rx0, ry0, rx1, ry1)
            self._all_borders[i].setData(bx, by)
            self._all_borders[i].setVisible(True)

        # Divider cross-hairs
        self._all_div_v.setData([0, 0], [-H, H])
        self._all_div_h.setData([-W, W], [0, 0])
        self._all_div_v.setVisible(True)
        self._all_div_h.setVisible(True)

        # Labels (top-left corner of each quadrant box)
        offsets = [
            (-W + 0.22,  H - 0.38),   # top-left cell  → CIRCLE
            ( 0.22,      H - 0.38),   # top-right cell → GEOMETRY
            (-W + 0.22, -0.38),       # bot-left cell  → EQ
            ( 0.22,     -0.38),       # bot-right cell → WAVE
        ]
        for lbl, (lx, ly) in zip(self._all_labels, offsets):
            lbl.setPos(lx, ly)
            lbl.setVisible(True)

        # Content — clamp sub-vis to stay inside quadrant boundaries
        # Max radius for circle/geometry limited to just under cell half-size
        sc = 0.72
        cell_half = qy - 0.3   # leave 0.3 margin inside border
        self._draw_circle(d, rms,   ox=-qx, oy=qy,  scale=sc * 0.55, is_all=True)
        self._draw_geometry(d, rms, ox=qx,  oy=qy,  scale=sc * 0.55, is_all=True)

        # EQ and Wave: clamp amplitude to cell_half relative to quadrant centre
        eq_scale = min(qx * 0.82, cell_half * 0.90)
        wv_scale = min(qx * 0.82, cell_half * 0.90)
        self._draw_eq(chunk,    ox=-qx, oy=-qy, scale=eq_scale, is_all=True)
        self._draw_wave(d, rms, ox=qx,  oy=-qy, scale=wv_scale, is_all=True)

    def _draw_img_circle(self, d, rms):
        self._hide_all_but('img_circle')
        
        step = max(1, len(d) // 256)
        v = d[::step][:256] * self.p_sens
        
        self._rot += (0.003 + rms * 0.015) * self.p_speed
        ang = self._angles[:len(v)] + self._rot
        
        # The image circle pulses with the beat
        pulse = 1.0 + self._beat_e * 0.15
        base_r = 2.0 * pulse
        
        # Outer wave ring
        rad = base_r + v * (1.0 + rms * 2.0)
        cx = rad * np.cos(ang)
        cy = rad * np.sin(ang)
        self._circle_rings[0].setData(np.append(cx, cx[0]), np.append(cy, cy[0]))
        
        # Scale and position Image Circle (pulsing)
        if self._img_circle_item.image is not None:
            r = base_r * 0.95
            self._img_circle_item.setRect(pg.QtCore.QRectF(-r, -r, r*2.0, r*2.0))
            
        self.widget.setXRange(-5, 5, padding=0)
        self.widget.setYRange(-5, 5, padding=0)


    def _hide_all_but(self, mode_str):
        dark_modes = ('lissajous', 'polar_level')
        self.widget.setBackground('#0d1117' if mode_str in dark_modes else '#f4f4f0')

        is_all = (mode_str == 'all')

        for c in self._wave_curves: c.setVisible(mode_str == 'wave' or is_all)
        for c in self._circle_rings: c.setVisible(mode_str in ('circle', 'img_circle') or is_all)
        self._circle_fill.setVisible(mode_str == 'circle')
        self._circle_chords.setVisible(mode_str == 'circle' or is_all)
        for c in self._circle_trails: c.setVisible(mode_str == 'circle' or is_all)
        for c in self._polys: c.setVisible(mode_str == 'geometry' or is_all)
        self._geo_web.setVisible(mode_str == 'geometry' or is_all)
        for c in self._geo_trails: c.setVisible(mode_str == 'geometry' or is_all)

        self._eq_fill.setVisible(mode_str == 'eq')
        self._eq_line.setVisible(mode_str == 'eq' or is_all)
        for tok in self._eq_tokens: tok.setVisible(mode_str == 'eq' or is_all)

        self._spec_img.setVisible(mode_str == 'spec')
        self._custom_curve.setVisible(mode_str == 'custom')
        self._custom_chords.setVisible(mode_str == 'custom')

        # Ozone Lissajous — mode string is 'lissajous' (matches VisMode.LISSAJOUS)
        is_liss = (mode_str == 'lissajous')
        for t in self._liss_trails: t.setVisible(is_liss)
        self._liss_diamond.setVisible(is_liss)
        self._liss_crosshair_h.setVisible(is_liss)
        self._liss_crosshair_v.setVisible(is_liss)

        # Polar Level
        is_polar = (mode_str == 'polar_level')
        self._polar_fill.setVisible(is_polar)
        self._polar_outline.setVisible(is_polar)
        self._polar_arc.setVisible(is_polar)
        self._polar_lr_line.setVisible(is_polar)
        for a in self._polar_guide_arcs: a.setVisible(is_polar)

        # ALL mode borders / labels
        for b in self._all_borders: b.setVisible(is_all)
        self._all_div_v.setVisible(is_all)
        self._all_div_h.setVisible(is_all)
        for lbl in self._all_labels: lbl.setVisible(is_all)

        self._bg_img.setVisible(mode_str not in ('img_circle', *dark_modes))
        self._img_circle_item.setVisible(mode_str == 'img_circle')

    def _hide_all(self):
        self._hide_all_but('none')
