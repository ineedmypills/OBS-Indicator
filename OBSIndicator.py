import obspython as obs
import threading
import sys
import os
import time
import ctypes
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional, List

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

HAS_PYSIDE = False
try:
    from PySide2.QtWidgets import QApplication, QWidget
    from PySide2.QtCore import (Qt, QTimer, QPoint, QRect, QObject, Signal,
                                QPointF, QRectF, QMetaObject)
    from PySide2.QtGui import (QPainter, QColor, QBrush, QPen, QPainterPath,
                               QGuiApplication, QPaintEvent, QWindow)
    HAS_PYSIDE = True
except ImportError:
    log.warning("PySide2 library not found. The overlay will not be displayed.")
    pass

overlay_app: Optional['OverlayApp'] = None
gui_thread: Optional[threading.Thread] = None

class Corner(Enum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"
    OFF = "off"

class Shape(Enum):
    CIRCLE = "circle"
    SQUARE = "square"
    ROUNDED = "rounded"

class Animation:
    SPEED = 0.15
    FRAME_INTERVAL_MS = 16
    SNAP_THRESHOLD = 0.01
    POSITION_SNAP_THRESHOLD = 0.5

class Timeouts:
    THREAD_JOIN = 2.0
    INITIAL_STATE_DELAY_MS = 200
    SCREEN_GEOMETRY_CHECK_MS = 1000

class Draw:
    BG_ROUNDED_RECT_RADIUS_RATIO = 0.3
    INDICATOR_ROUNDED_RECT_RADIUS_RATIO = 0.3
    PAUSE_PEN_WIDTH_RATIO = 0.18
    PAUSE_BAR_HEIGHT_RATIO = 0.65
    PAUSE_BAR_SPACING_RATIO = 0.35
    CHECKMARK_PEN_WIDTH_RATIO = 0.2
    CHECKMARK_P1 = QPointF(-0.30, 0.05)
    CHECKMARK_P2 = QPointF(-0.10, 0.25)
    CHECKMARK_P3 = QPointF(0.30, -0.25)
    CHECKMARK_ANIM_SPLIT = 0.35
    DIM_OPACITY = 0.3

DEFAULT_SETTINGS = {
    "corner_rec": Corner.TOP_RIGHT.value,
    "corner_buf": Corner.TOP_RIGHT.value,
    "size": 10, "margin": 10, "opacity": 50,
    "rec_color": 0xFF5555, "rec_pause_color": 0xFFAA00,
    "buf_color": 0x55FF55, "buf_saved_color": 0x5555FF,
    "bg_opacity": 50, "bg_size_percent": 300,
    "indicator_shape": Shape.CIRCLE.value, "bg_shape": Shape.CIRCLE.value,
    "fade_effect": True, "smooth_position": True,
    "animate_pause": True, "animate_checkmark": True,
    "checkmark_duration": 1.5
}

STRINGS = {
    "description": "Animated indicators for recording and replay buffer.",
    "size": "Indicator Size", "margin": "Margin from Edge", "opacity": "Opacity (%)",
    "rec_color": "Color (Active)", "rec_pause_color": "Color (Paused)",
    "buf_color": "Color (Active)", "buf_saved_color": "Color (Saved)",
    "bg_opacity": "Background Opacity (%)", "bg_size_percent": "Background Size (%)",
    "indicator_shape": "Indicator Shape", "bg_shape": "Background Shape",
    "fade_effect": "Fade Effect", "smooth_position": "Smooth Movement",
    "animate_pause": "Animate Pause Icon", "animate_checkmark": "Animate Checkmark Icon",
    "checkmark_duration": "Checkmark Duration (s)",
    "shape_opts": [("Circle", Shape.CIRCLE.value), ("Square", Shape.SQUARE.value), ("Rounded", Shape.ROUNDED.value)],
    "corner_opts": [
        ("Top Left", Corner.TOP_LEFT.value), ("Top Right", Corner.TOP_RIGHT.value),
        ("Bottom Left", Corner.BOTTOM_LEFT.value), ("Bottom Right", Corner.BOTTOM_RIGHT.value),
        ("Off", Corner.OFF.value)
    ]
}

def obs_color_to_rgb(obs_color: int) -> int:
    return ((obs_color & 0xFF) << 16) | (obs_color & 0xFF00) | ((obs_color >> 16) & 0xFF)

def rgb_to_obs_color(rgb_color: int) -> int:
    return (0xFF << 24) | ((rgb_color & 0xFF) << 16) | (rgb_color & 0xFF00) | ((rgb_color >> 16) & 0xFF)

def lerp(start: float, end: float, alpha: float) -> float:
    return start + (end - start) * alpha

def cubic_bezier_ease(t: float) -> float:
    return 1 - (1 - t) ** 3

if HAS_PYSIDE:
    @dataclass
    class AnimatedValue:
        current: float = 0.0
        target: float = 0.0

        def set_target(self, new_target: float, immediate: bool = False) -> None:
            self.target = float(new_target)
            if immediate:
                self.current = self.target

        def update(self, speed: float, enabled: bool) -> bool:
            if self.current == self.target:
                return False
            if not enabled or abs(self.current - self.target) < Animation.SNAP_THRESHOLD:
                self.current = self.target
            else:
                self.current = lerp(self.current, self.target, speed)
            return True

    @dataclass
    class IndicatorState:
        active: bool = False
        visibility: AnimatedValue = field(default_factory=AnimatedValue)
        position: QPointF = field(default_factory=QPointF)
        target_position: QPointF = field(default_factory=QPointF)

    @dataclass
    class RecordingState(IndicatorState):
        paused: bool = False
        pause_icon: AnimatedValue = field(default_factory=AnimatedValue)

    @dataclass
    class BufferState(IndicatorState):
        saved: bool = False
        saved_time: float = 0.0
        checkmark_icon: AnimatedValue = field(default_factory=AnimatedValue)
        dim_effect: AnimatedValue = field(default_factory=lambda: AnimatedValue(current=1.0, target=1.0))

if HAS_PYSIDE:
    class SignalEmitter(QObject):
        rec_status_changed = Signal(bool, bool)
        buf_status_changed = Signal(bool, bool)
        settings_updated = Signal(dict)

    class OverlayWindow(QWidget):
        def __init__(self, emitter: SignalEmitter, initial_settings: Dict[str, Any]):
            super().__init__()
            self.emitter = emitter
            self.settings = initial_settings
            self.closing = False
            self.positions_cache: Dict[str, QPoint] = {}
            self.current_screen_geometry = QRect()

            self.rec_state = RecordingState()
            self.buf_state = BufferState()

            self._init_ui()
            self._setup_signals()
            self._setup_timers()

        def _init_ui(self) -> None:
            self.setWindowTitle("OBS Status Overlay")
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
            self.setWindowOpacity(self.settings["opacity"] / 100.0)
            self._update_geometry()
            self._setup_win32_attributes()

        def _setup_win32_attributes(self) -> None:
            if os.name != 'nt':
                return
            try:
                HWND_TOPMOST = -1
                SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
                GWL_EXSTYLE = -20
                WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x00080000, 0x00000020

                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            except Exception as e:
                log.warning(f"Failed to set window attributes for click-through: {e}")

        def _setup_signals(self) -> None:
            self.emitter.rec_status_changed.connect(self.on_rec_status_changed, Qt.QueuedConnection)
            self.emitter.buf_status_changed.connect(self.on_buf_status_changed, Qt.QueuedConnection)
            self.emitter.settings_updated.connect(self.on_settings_updated, Qt.QueuedConnection)

        def _setup_timers(self) -> None:
            self.animation_timer = QTimer(self)
            self.animation_timer.timeout.connect(self.update_animations)
            self.animation_timer.start(Animation.FRAME_INTERVAL_MS)

            self.geometry_timer = QTimer(self)
            self.geometry_timer.timeout.connect(self._update_geometry)
            self.geometry_timer.start(Timeouts.SCREEN_GEOMETRY_CHECK_MS)

        def closeEvent(self, event: QPaintEvent) -> None:
            self.closing = True
            self.animation_timer.stop()
            self.geometry_timer.stop()
            self.deleteLater()
            super().closeEvent(event)

        def on_rec_status_changed(self, active: bool, paused: bool) -> None:
            if self.closing or not self.isVisible(): return
            self.rec_state.active = active
            self.rec_state.paused = paused

        def on_buf_status_changed(self, active: bool, saved: bool) -> None:
            if self.closing or not self.isVisible(): return
            if saved:
                self.buf_state.active = True
                self.buf_state.saved = True
                self.buf_state.saved_time = time.monotonic()
            else:
                self.buf_state.active = active

        def on_settings_updated(self, new_settings: Dict[str, Any]) -> None:
            if self.closing or not self.isVisible(): return
            self.settings = new_settings
            self.setWindowOpacity(self.settings["opacity"] / 100.0)
            self.positions_cache.clear()
            self._update_geometry()
            self.update()

        def _update_geometry(self) -> None:
            if self.closing: return

            screen = QGuiApplication.primaryScreen()
            if not screen:
                log.warning("Primary screen not found. Overlay position may be incorrect.")
                return

            if (screen_geometry := screen.geometry()) != self.current_screen_geometry:
                self.setGeometry(screen_geometry)
                self.current_screen_geometry = screen_geometry
                self.positions_cache.clear()
                self.update()

        def _calculate_position(self, corner: str, index: int = 0) -> Optional[QPoint]:
            if not self.current_screen_geometry.isValid(): return None

            size = self.settings["size"]
            margin = self.settings["margin"]
            bg_size = int(size * self.settings["bg_size_percent"] / 100)
            radius = bg_size // 2
            if not radius: return None

            cache_key = f"{corner}_{index}_{size}_{margin}_{self.settings['bg_size_percent']}"
            if cache_key in self.positions_cache:
                return self.positions_cache[cache_key]

            width, height = self.width(), self.height()
            offset = index * (bg_size + margin)

            pos_map = {
                Corner.TOP_LEFT.value: QPoint(margin + radius + offset, margin + radius),
                Corner.TOP_RIGHT.value: QPoint(width - margin - radius - offset, margin + radius),
                Corner.BOTTOM_LEFT.value: QPoint(margin + radius + offset, height - margin - radius),
                Corner.BOTTOM_RIGHT.value: QPoint(width - margin - radius - offset, height - margin - radius)
            }
            if pos := pos_map.get(corner):
                self.positions_cache[cache_key] = pos
            return pos

        def update_animations(self) -> None:
            if self.closing: return

            self.rec_state.visibility.set_target(self.rec_state.active)
            self.rec_state.pause_icon.set_target(self.rec_state.paused)

            self.buf_state.visibility.set_target(self.buf_state.active)

            if self.buf_state.saved and time.monotonic() - self.buf_state.saved_time > self.settings["checkmark_duration"]:
                self.buf_state.saved = False
                self.buf_state.saved_time = 0.0
            self.buf_state.checkmark_icon.set_target(self.buf_state.saved)

            dim_target = Draw.DIM_OPACITY if self.rec_state.active and self.rec_state.paused else 1.0
            self.buf_state.dim_effect.set_target(dim_target)

            updated = False
            updated |= self.rec_state.visibility.update(Animation.SPEED, self.settings["fade_effect"])
            updated |= self.rec_state.pause_icon.update(Animation.SPEED, self.settings["animate_pause"])
            updated |= self.buf_state.visibility.update(Animation.SPEED, self.settings["fade_effect"])
            updated |= self.buf_state.checkmark_icon.update(Animation.SPEED, self.settings["animate_checkmark"])
            updated |= self.buf_state.dim_effect.update(Animation.SPEED, self.settings["fade_effect"])
            updated |= self._update_position_animation(self.buf_state)
            if updated:
                self.update()

        def _update_position_animation(self, state: IndicatorState) -> bool:
            if not self.settings["smooth_position"]:
                if state.position != state.target_position:
                    state.position = state.target_position
                    return True
                return False

            if state.target_position.isNull() or state.position == state.target_position:
                return False

            new_x = lerp(state.position.x(), state.target_position.x(), Animation.SPEED)
            new_y = lerp(state.position.y(), state.target_position.y(), Animation.SPEED)

            if (abs(new_x - state.target_position.x()) < Animation.POSITION_SNAP_THRESHOLD and
                    abs(new_y - state.target_position.y()) < Animation.POSITION_SNAP_THRESHOLD):
                new_pos = state.target_position
            else:
                new_pos = QPointF(new_x, new_y)

            if new_pos != state.position:
                state.position = new_pos
                return True
            return False

        def paintEvent(self, event: QPaintEvent) -> None:
            if self.closing: return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            self._paint_recording_indicator(painter)
            self._paint_buffer_indicator(painter)

        def _paint_recording_indicator(self, painter: QPainter) -> None:
            if self.settings["corner_rec"] == Corner.OFF.value or self.rec_state.visibility.current < Animation.SNAP_THRESHOLD:
                return

            if not (pos := self._calculate_position(self.settings["corner_rec"])):
                return

            master_anim = self.rec_state.visibility.current
            self._draw_background(painter, pos, master_anim)

            pause_progress = self.rec_state.pause_icon.current
            main_opacity = 1.0 - pause_progress

            if self.rec_state.active and main_opacity > Animation.SNAP_THRESHOLD:
                self._draw_indicator(painter, pos, master_anim, self.settings["rec_color"], main_opacity)

            if pause_progress > Animation.SNAP_THRESHOLD:
                self._draw_pause_icon(painter, pos, pause_progress, master_anim, self.settings["rec_pause_color"])

        def _paint_buffer_indicator(self, painter: QPainter) -> None:
            if self.settings["corner_buf"] == Corner.OFF.value or self.buf_state.visibility.current < Animation.SNAP_THRESHOLD:
                if not self.buf_state.position.isNull():
                    self.buf_state.position = QPointF()
                    self.buf_state.target_position = QPointF()
                return

            is_shared_corner = (self.rec_state.active and
                                self.settings["corner_rec"] == self.settings["corner_buf"] and
                                self.settings["corner_rec"] != Corner.OFF.value)
            index = 1 if is_shared_corner else 0

            if not (target_pos_qpoint := self._calculate_position(self.settings["corner_buf"], index)):
                return

            target_pos = QPointF(target_pos_qpoint)
            self.buf_state.target_position = target_pos
            if self.buf_state.position.isNull():
                self.buf_state.position = target_pos

            current_pos = self.buf_state.position.toPoint()
            master_anim = self.buf_state.visibility.current
            dim_factor = self.buf_state.dim_effect.current

            self._draw_background(painter, current_pos, master_anim * dim_factor)

            checkmark_progress = self.buf_state.checkmark_icon.current
            main_opacity = 1.0 - checkmark_progress

            if self.buf_state.active and main_opacity > Animation.SNAP_THRESHOLD:
                self._draw_indicator(painter, current_pos, master_anim, self.settings["buf_color"],
                                     main_opacity * dim_factor)

            if checkmark_progress > Animation.SNAP_THRESHOLD:
                self._draw_checkmark(painter, current_pos, checkmark_progress, master_anim,
                                     self.settings["buf_saved_color"], dim_factor * checkmark_progress)

        def _draw_shape(self, painter: QPainter, rect: QRect, shape: str, color: QColor, rounded_ratio: float) -> None:
            if color.alpha() < 1: return
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)

            if shape == Shape.CIRCLE.value:
                painter.drawEllipse(rect)
            elif shape == Shape.SQUARE.value:
                painter.drawRect(rect)
            else:
                radius = min(rect.width(), rect.height()) * rounded_ratio
                painter.drawRoundedRect(rect, radius, radius)

        def _draw_background(self, painter: QPainter, pos: QPoint, anim_value: float) -> None:
            bg_size = int(self.settings["size"] * self.settings["bg_size_percent"] / 100)
            if bg_size <= 0: return

            alpha = int(255 * anim_value * (self.settings["bg_opacity"] / 100.0))
            color = QColor(0, 0, 0, max(0, min(alpha, 255)))
            rect = QRect(pos.x() - bg_size // 2, pos.y() - bg_size // 2, bg_size, bg_size)

            self._draw_shape(painter, rect, self.settings["bg_shape"], color, Draw.BG_ROUNDED_RECT_RADIUS_RATIO)

        def _draw_indicator(self, painter: QPainter, pos: QPoint, master_anim: float, rgb_color: int,
                            opacity_multiplier: float) -> None:
            size = self.settings["size"]
            if size <= 0: return

            base_alpha = master_anim * (self.settings["opacity"] / 100.0)
            final_alpha = int(255 * base_alpha * opacity_multiplier)
            color = QColor(rgb_color)
            color.setAlpha(max(0, min(final_alpha, 255)))
            rect = QRect(pos.x() - size // 2, pos.y() - size // 2, size, size)

            self._draw_shape(painter, rect, self.settings["indicator_shape"], color,
                             Draw.INDICATOR_ROUNDED_RECT_RADIUS_RATIO)

        def _draw_pause_icon(self, painter: QPainter, pos: QPoint, icon_progress: float, master_anim: float,
                             rgb_color: int) -> None:
            size = self.settings["size"]
            if size <= 0: return

            eased_progress = cubic_bezier_ease(icon_progress)
            base_alpha = master_anim * (self.settings["opacity"] / 100.0)
            final_alpha = int(255 * base_alpha)
            color = QColor(rgb_color)
            color.setAlpha(max(0, min(final_alpha, 255)))
            if color.alpha() < 1: return

            pen_width = max(2, int(size * Draw.PAUSE_PEN_WIDTH_RATIO))
            bar_height = size * Draw.PAUSE_BAR_HEIGHT_RATIO
            bar_spacing = size * Draw.PAUSE_BAR_SPACING_RATIO

            pen = QPen(color, pen_width, cap=Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            center_x, center_y = pos.x(), pos.y()
            left_x, right_x = center_x - bar_spacing / 2, center_x + bar_spacing / 2
            animated_half_height = (bar_height * eased_progress) / 2

            path = QPainterPath()
            path.moveTo(left_x, center_y - animated_half_height)
            path.lineTo(left_x, center_y + animated_half_height)
            path.moveTo(right_x, center_y - animated_half_height)
            path.lineTo(right_x, center_y + animated_half_height)
            painter.drawPath(path)

        def _draw_checkmark(self, painter: QPainter, pos: QPoint, icon_progress: float, master_anim: float,
                            rgb_color: int, opacity_multiplier: float) -> None:
            size = self.settings["size"]
            eased_progress = cubic_bezier_ease(icon_progress)

            base_alpha = master_anim * (self.settings["opacity"] / 100.0)
            final_alpha = int(255 * base_alpha * opacity_multiplier)
            color = QColor(rgb_color)
            color.setAlpha(max(0, min(final_alpha, 255)))
            if color.alpha() < 1: return

            painter.save()
            pen_width = max(2, int(size * Draw.CHECKMARK_PEN_WIDTH_RATIO))
            pen = QPen(color, pen_width, cap=Qt.RoundCap, join=Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.translate(pos)

            p1, p2, p3 = (p * size for p in (Draw.CHECKMARK_P1, Draw.CHECKMARK_P2, Draw.CHECKMARK_P3))

            path = QPainterPath()
            path.moveTo(p1)

            if self.buf_state.checkmark_icon.target == 1.0:
                split = Draw.CHECKMARK_ANIM_SPLIT
                if eased_progress < split:
                    t = eased_progress / split
                    path.lineTo(p1 + t * (p2 - p1))
                else:
                    path.lineTo(p2)
                    t = (eased_progress - split) / (1.0 - split)
                    path.lineTo(p2 + t * (p3 - p2))
            else:
                path.lineTo(p2)
                path.lineTo(p3)

            painter.drawPath(path)
            painter.restore()

    class OverlayApp:
        def __init__(self, initial_settings: Dict[str, Any]):
            self.app: Optional[QApplication] = None
            self.overlay: Optional[OverlayWindow] = None
            self.emitter = SignalEmitter()
            self.initial_settings = initial_settings

        def run(self) -> None:
            self.app = QApplication.instance() or QApplication([])
            self.app.setQuitOnLastWindowClosed(True)
            self.overlay = OverlayWindow(self.emitter, self.initial_settings)
            self.overlay.show()
            self.app.exec_()

        def stop(self) -> None:
            if self.overlay:
                QMetaObject.invokeMethod(self.overlay, "close", Qt.QueuedConnection)

def event_handler(event: int) -> None:
    if not HAS_PYSIDE or not overlay_app or not overlay_app.emitter: return

    event_map = {
        obs.OBS_FRONTEND_EVENT_RECORDING_STARTING: lambda: overlay_app.emitter.rec_status_changed.emit(True, False),
        obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED: lambda: overlay_app.emitter.rec_status_changed.emit(False, False),
        obs.OBS_FRONTEND_EVENT_RECORDING_PAUSED: lambda: overlay_app.emitter.rec_status_changed.emit(True, True),
        obs.OBS_FRONTEND_EVENT_RECORDING_UNPAUSED: lambda: overlay_app.emitter.rec_status_changed.emit(True, False),
        obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED: lambda: overlay_app.emitter.buf_status_changed.emit(True, False),
        obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED: lambda: overlay_app.emitter.buf_status_changed.emit(False, False),
        obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED: lambda: overlay_app.emitter.buf_status_changed.emit(True, True),
    }

    if action := event_map.get(event):
        action()

def script_description() -> str:
    return STRINGS["description"]

def _add_list_options(prop_list: Any, options: List[Tuple[str, str]]) -> None:
    for label, value in options:
        obs.obs_property_list_add_string(prop_list, label, value)

def script_properties() -> Any:
    props = obs.obs_properties_create()

    def add_group(parent: Any, id_str: str, title: str) -> Any:
        grp = obs.obs_properties_create()
        obs.obs_properties_add_group(parent, id_str, title, obs.OBS_GROUP_NORMAL, grp)
        return grp

    app_grp = add_group(props, "appearance", "Appearance")
    obs.obs_properties_add_int(app_grp, "size", STRINGS["size"], 5, 100, 1)
    obs.obs_properties_add_int(app_grp, "margin", STRINGS["margin"], 0, 100, 1)
    obs.obs_properties_add_int_slider(app_grp, "opacity", STRINGS["opacity"], 1, 100, 1)
    shape_list = obs.obs_properties_add_list(app_grp, "indicator_shape", STRINGS["indicator_shape"], obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(shape_list, STRINGS["shape_opts"])
    bg_shape_list = obs.obs_properties_add_list(app_grp, "bg_shape", STRINGS["bg_shape"], obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(bg_shape_list, STRINGS["shape_opts"])
    obs.obs_properties_add_int_slider(app_grp, "bg_opacity", STRINGS["bg_opacity"], 0, 100, 1)
    obs.obs_properties_add_int_slider(app_grp, "bg_size_percent", STRINGS["bg_size_percent"], 100, 500, 5)

    rec_grp = add_group(props, "recording", "Recording Indicator")
    corner_list_rec = obs.obs_properties_add_list(rec_grp, "corner_rec", "Position", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(corner_list_rec, STRINGS["corner_opts"])
    obs.obs_properties_add_color(rec_grp, "rec_color", STRINGS["rec_color"])
    obs.obs_properties_add_color(rec_grp, "rec_pause_color", STRINGS["rec_pause_color"])

    buf_grp = add_group(props, "buffer", "Replay Buffer Indicator")
    corner_list_buf = obs.obs_properties_add_list(buf_grp, "corner_buf", "Position", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(corner_list_buf, STRINGS["corner_opts"])
    obs.obs_properties_add_color(buf_grp, "buf_color", STRINGS["buf_color"])
    obs.obs_properties_add_color(buf_grp, "buf_saved_color", STRINGS["buf_saved_color"])
    obs.obs_properties_add_float_slider(buf_grp, "checkmark_duration", STRINGS["checkmark_duration"], 0.5, 5.0, 0.1)

    fx_grp = add_group(props, "effects", "Effects")
    obs.obs_properties_add_bool(fx_grp, "fade_effect", STRINGS["fade_effect"])
    obs.obs_properties_add_bool(fx_grp, "smooth_position", STRINGS["smooth_position"])
    obs.obs_properties_add_bool(fx_grp, "animate_pause", STRINGS["animate_pause"])
    obs.obs_properties_add_bool(fx_grp, "animate_checkmark", STRINGS["animate_checkmark"])

    return props

def script_defaults(settings_obj: Any) -> None:
    setter_map = {
        bool: obs.obs_data_set_default_bool,
        float: obs.obs_data_set_default_double,
        int: obs.obs_data_set_default_int,
        str: obs.obs_data_set_default_string,
    }
    for key, value in DEFAULT_SETTINGS.items():
        if key.endswith("_color"):
            obs.obs_data_set_default_int(settings_obj, key, rgb_to_obs_color(value))
        elif setter_func := setter_map.get(type(value)):
            setter_func(settings_obj, key, value)

def get_settings_from_obs(settings_obj: Any) -> Dict[str, Any]:
    s = {}
    getter_map = {
        bool: obs.obs_data_get_bool,
        float: obs.obs_data_get_double,
        int: obs.obs_data_get_int,
        str: obs.obs_data_get_string,
    }
    for key, value in DEFAULT_SETTINGS.items():
        if key.endswith("_color"):
            s[key] = obs_color_to_rgb(obs.obs_data_get_int(settings_obj, key))
        elif getter_func := getter_map.get(type(value)):
            s[key] = getter_func(settings_obj, key)
    return s

def script_update(settings_obj: Any) -> None:
    if HAS_PYSIDE and overlay_app and overlay_app.emitter:
        current_settings = get_settings_from_obs(settings_obj)
        overlay_app.emitter.settings_updated.emit(current_settings)

def script_load(settings_obj: Any) -> None:
    global overlay_app, gui_thread
    if not HAS_PYSIDE:
        return

    initial_settings = get_settings_from_obs(settings_obj)
    obs.obs_frontend_add_event_callback(event_handler)

    overlay_app = OverlayApp(initial_settings)
    gui_thread = threading.Thread(target=overlay_app.run, daemon=True)
    gui_thread.start()

    obs.timer_add(_send_initial_state, Timeouts.INITIAL_STATE_DELAY_MS)

def _send_initial_state() -> None:
    if overlay_app and overlay_app.emitter:
        rec_active = obs.obs_frontend_recording_active()
        rec_paused = obs.obs_frontend_recording_paused() if rec_active else False
        buf_active = obs.obs_frontend_replay_buffer_active()
        overlay_app.emitter.rec_status_changed.emit(rec_active, rec_paused)
        overlay_app.emitter.buf_status_changed.emit(buf_active, False)

def script_unload() -> None:
    global overlay_app, gui_thread
    obs.obs_frontend_remove_event_callback(event_handler)
    if HAS_PYSIDE and overlay_app:
        overlay_app.stop()
        if gui_thread:
            gui_thread.join(Timeouts.THREAD_JOIN)
        overlay_app = None
        gui_thread = None
    log.info("OBS Indicator script unloaded.")