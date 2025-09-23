import ctypes
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Tuple, Optional, List

import obspython as obs

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

HAS_PYSIDE = False
HAS_QTSOUND = False
try:
    from PySide2.QtWidgets import QApplication, QWidget
    from PySide2.QtCore import (Qt, QTimer, QPoint, QRect, QObject, Signal,
                                QPointF, QRectF, QMetaObject, QUrl)
    from PySide2.QtGui import (QPainter, QColor, QBrush, QPen, QPainterPath,
                               QGuiApplication, QPaintEvent)

    try:
        from PySide2.QtMultimedia import QSoundEffect
        HAS_QTSOUND = True
    except ImportError:
        log.warning("PySide2.QtMultimedia not found. Sound effects will not be played.")

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
    "checkmark_duration": 1.5,
    "flash_on_save": False, "flash_color": 0xFFFFFF, "flash_duration": 0.2,
    "rec_border_enabled": False, "rec_pause_border_enabled": True,
    "rec_border_color": 0xFF5555, "rec_pause_border_color": 0xFFAA00,
    "buf_border_enabled": False, "buf_save_border_enabled": True,
    "buf_border_color": 0x55FF55, "buf_save_border_color": 0x5555FF,
    "border_width": 5,
    "save_sound_path": "Saved.wav",
    "save_sound_volume": 100,
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
    "flash_on_save": "Flash on Save", "flash_color": "Flash Color", "flash_duration": "Flash Duration (s)",
    "borders_group": "Borders",
    "rec_border_enabled": "Enable Recording Border",
    "rec_pause_border_enabled": "Enable Pause Border (if main is off)",
    "rec_border_color": "Border Color (Active)",
    "rec_pause_border_color": "Border Color (Paused)",
    "buf_border_enabled": "Enable Replay Buffer Border",
    "buf_save_border_enabled": "Enable Save Border (if main is off)",
    "buf_border_color": "Border Color (Active)",
    "buf_save_border_color": "Border Color (Saved)",
    "border_width": "Border Width (px)",
    "save_sound_path": "Save Sound Path",
    "save_sound_volume": "Save Sound Volume (%)",
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


def ease_in_out_cubic(t: float) -> float:
    t *= 2
    if t < 1:
        return 0.5 * t * t * t
    t -= 2
    return 0.5 * (t * t * t + 2)


def ease_out_cubic(t: float) -> float:
    t -= 1.0
    return t * t * t + 1.0


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
        name: str
        active: bool = False
        visibility: AnimatedValue = field(default_factory=AnimatedValue)
        position: QPointF = field(default_factory=QPointF)
        target_position: QPointF = field(default_factory=QPointF)


    @dataclass
    class RecordingState(IndicatorState):
        name: str = "rec"
        paused: bool = False
        pause_icon: AnimatedValue = field(default_factory=AnimatedValue)
        border_width: AnimatedValue = field(default_factory=AnimatedValue)


    @dataclass
    class BufferState(IndicatorState):
        name: str = "buf"
        saved: bool = False
        saved_time: float = 0.0
        checkmark_icon: AnimatedValue = field(default_factory=AnimatedValue)
        dim_effect: AnimatedValue = field(default_factory=lambda: AnimatedValue(current=1.0, target=1.0))
        flash_effect: AnimatedValue = field(default_factory=AnimatedValue)
        flash_start_time: float = 0.0
        border_width: AnimatedValue = field(default_factory=AnimatedValue)
        save_border_width: AnimatedValue = field(default_factory=AnimatedValue)


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
            self.positions_cache: Dict[Tuple[str, int], QPoint] = {}
            self.current_screen_geometry = QRect()

            self.rec_state = RecordingState()
            self.buf_state = BufferState()
            self.save_sound: Optional[QSoundEffect] = None

            self._init_ui()
            self._setup_signals()
            self._setup_timers()
            self._setup_sound()

        def _init_ui(self) -> None:
            self.setWindowTitle("OBS Status Overlay")
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
            self._update_geometry()
            self._setup_platform_specifics()

        def _setup_platform_specifics(self) -> None:
            if os.name == 'nt':
                try:
                    hwnd = int(self.winId())
                    ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
                    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                    ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style | 0x00080000 | 0x00000020)
                except Exception as e:
                    log.warning(f"Failed to set window attributes for click-through: {e}")
            else:
                self.setAttribute(Qt.WA_TransparentForMouseEvents)
                is_wayland = 'wayland' in os.environ.get('XDG_SESSION_TYPE', '').lower() or \
                             'WAYLAND_DISPLAY' in os.environ
                if not is_wayland:
                    current_flags = self.windowFlags()
                    self.setWindowFlags(current_flags | Qt.X11BypassWindowManagerHint)

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

        def _setup_sound(self) -> None:
            if not HAS_QTSOUND: return
            self.save_sound = QSoundEffect(self)
            self._update_sound()

        def _update_sound(self) -> None:
            if not self.save_sound: return
            path = self.settings.get("save_sound_path", "")
            volume = self.settings.get("save_sound_volume", 100) / 100.0
            
            if path and not os.path.isabs(path):
                try:
                    # obs.script_path() is the intended way, but __file__ is a reliable fallback
                    script_dir = os.path.dirname(obs.script_path() or __file__)
                    path = os.path.join(script_dir, path)
                except (NameError, AttributeError):
                    # Fallback if both fail
                    pass

            if path and os.path.exists(path):
                self.save_sound.setSource(QUrl.fromLocalFile(path))
                self.save_sound.setVolume(volume)
            else:
                self.save_sound.setSource(QUrl())

        def closeEvent(self, event: QPaintEvent) -> None:
            self.closing = True
            self.animation_timer.stop()
            self.geometry_timer.stop()
            self.deleteLater()
            super().closeEvent(event)

        def on_rec_status_changed(self, active: bool, paused: bool) -> None:
            if self.closing: return
            self.rec_state.active = active
            self.rec_state.paused = paused

        def on_buf_status_changed(self, active: bool, saved: bool) -> None:
            if self.closing: return
            if saved:
                self.buf_state.active = True
                self.buf_state.saved = True
                self.buf_state.saved_time = time.monotonic()
                if self.settings["flash_on_save"]:
                    self.buf_state.flash_start_time = time.monotonic()
                    self.buf_state.flash_effect.set_target(1.0)
                if self.save_sound and self.save_sound.isLoaded():
                    self.save_sound.play()
            else:
                self.buf_state.active = active

        def on_settings_updated(self, new_settings: Dict[str, Any]) -> None:
            if self.closing: return
            self.settings = new_settings
            self.positions_cache.clear()
            self._update_geometry()
            self._update_sound()
            self.update()

        def _update_geometry(self) -> None:
            if self.closing: return
            screen = QGuiApplication.primaryScreen()
            if not screen:
                log.warning("Primary screen not found.")
                return

            if (screen_geometry := screen.geometry()) != self.current_screen_geometry:
                self.setGeometry(screen_geometry)
                self.current_screen_geometry = screen_geometry
                self.positions_cache.clear()
                self.update()

        def _calculate_position(self, corner: str, index: int = 0) -> Optional[QPoint]:
            if not self.current_screen_geometry.isValid() or corner == Corner.OFF.value:
                return None

            cache_key = (corner, index)
            if cache_key in self.positions_cache:
                return self.positions_cache[cache_key]

            size = self.settings["size"]
            margin = self.settings["margin"]
            bg_size = int(size * self.settings["bg_size_percent"] / 100)
            radius = bg_size // 2
            offset = index * (bg_size + margin)
            width, height = self.width(), self.height()

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

            # Update targets
            self.rec_state.visibility.set_target(self.rec_state.active)
            self.rec_state.pause_icon.set_target(self.rec_state.paused)

            if self.buf_state.saved and time.monotonic() - self.buf_state.saved_time > self.settings["checkmark_duration"]:
                self.buf_state.saved = False
                self.buf_state.saved_time = 0.0

            self.buf_state.visibility.set_target(self.buf_state.active)
            self.buf_state.checkmark_icon.set_target(self.buf_state.saved)

            dim_target = Draw.DIM_OPACITY if self.rec_state.active and self.rec_state.paused else 1.0
            self.buf_state.dim_effect.set_target(dim_target)

            if self.buf_state.flash_start_time > 0:
                if time.monotonic() - self.buf_state.flash_start_time > self.settings["flash_duration"]:
                    self.buf_state.flash_effect.set_target(0.0)
                    if self.buf_state.flash_effect.current < Animation.SNAP_THRESHOLD:
                        self.buf_state.flash_start_time = 0.0

            # Border logic
            rec_border_on = self.settings["rec_border_enabled"] and self.rec_state.active
            buf_border_on = self.settings["buf_border_enabled"] and self.buf_state.active

            pause_border_on = (not self.settings["rec_border_enabled"] and
                               self.settings["rec_pause_border_enabled"] and
                               self.rec_state.active and self.rec_state.paused)

            save_border_on = (not self.settings["buf_border_enabled"] and
                              self.settings["buf_save_border_enabled"] and
                              self.buf_state.saved)

            target_rec_border_width = self.settings["border_width"] if rec_border_on or pause_border_on else 0
            self.rec_state.border_width.set_target(target_rec_border_width)

            self.buf_state.border_width.set_target(self.settings["border_width"] if buf_border_on else 0)
            self.buf_state.save_border_width.set_target(self.settings["border_width"] if save_border_on else 0)


            # Update positions
            self._update_indicator_position(self.rec_state)
            self._update_indicator_position(self.buf_state)

            # Update animated values
            updated = False
            for state in [self.rec_state, self.buf_state]:
                updated |= state.visibility.update(Animation.SPEED, self.settings["fade_effect"])
                updated |= self._update_position_animation(state)

            updated |= self.rec_state.pause_icon.update(Animation.SPEED, self.settings["animate_pause"])
            updated |= self.buf_state.checkmark_icon.update(Animation.SPEED, self.settings["animate_checkmark"])
            updated |= self.buf_state.dim_effect.update(Animation.SPEED, self.settings["fade_effect"])
            flash_speed_multiplier = 4.0 if self.buf_state.flash_effect.target == 1.0 else 1.0
            updated |= self.buf_state.flash_effect.update(Animation.SPEED * flash_speed_multiplier, True)
            updated |= self.rec_state.border_width.update(Animation.SPEED, True)
            updated |= self.buf_state.border_width.update(Animation.SPEED, True)
            updated |= self.buf_state.save_border_width.update(Animation.SPEED, True)

            if updated:
                self.update()

        def _update_indicator_position(self, state: IndicatorState) -> None:
            corner_setting = self.settings[f"corner_{state.name}"]
            if corner_setting == Corner.OFF.value:
                state.target_position = QPointF()
                return

            is_rec_active_on_same_corner = (
                    self.rec_state.active and
                    self.settings["corner_rec"] == self.settings["corner_buf"] and
                    self.settings["corner_rec"] != Corner.OFF.value
            )
            index = 1 if state.name == "buf" and is_rec_active_on_same_corner else 0

            if target_pos_qpoint := self._calculate_position(corner_setting, index):
                target_pos = QPointF(target_pos_qpoint)
                if state.target_position != target_pos:
                    state.target_position = target_pos
                    if state.position.isNull():
                        state.position = target_pos

        def _update_position_animation(self, state: IndicatorState) -> bool:
            if state.position == state.target_position:
                return False

            if not self.settings["smooth_position"] or state.target_position.isNull():
                state.position = state.target_position
                return True

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
            self._paint_borders(painter)
            self._paint_flash(painter)
            self._paint_indicator(painter, self.rec_state)
            self._paint_indicator(painter, self.buf_state)

        def _paint_flash(self, painter: QPainter) -> None:
            if self.buf_state.flash_effect.current < Animation.SNAP_THRESHOLD:
                return
            alpha = self.buf_state.flash_effect.current
            if self.buf_state.flash_effect.target == 0.0:
                alpha = ease_out_cubic(alpha)
            color = QColor(self.settings["flash_color"])
            color.setAlphaF(alpha)
            painter.fillRect(self.rect(), color)

        def _paint_borders(self, painter: QPainter) -> None:
            painter.save()
            # Regular recording border
            if self.rec_state.border_width.current > Animation.SNAP_THRESHOLD:
                width = self.rec_state.border_width.current
                color_key = "rec_pause_border_color" if self.rec_state.paused else "rec_border_color"
                color = QColor(self.settings[color_key])
                self._draw_border(painter, width, color)

            # Regular buffer border
            if self.buf_state.border_width.current > Animation.SNAP_THRESHOLD:
                width = self.buf_state.border_width.current
                color_key = "buf_save_border_color" if self.buf_state.saved else "buf_border_color"
                color = QColor(self.settings[color_key])
                self._draw_border(painter, width, color)

            # Special save border
            if self.buf_state.save_border_width.current > Animation.SNAP_THRESHOLD:
                width = self.buf_state.save_border_width.current
                color = QColor(self.settings["buf_save_border_color"])
                self._draw_border(painter, width, color)
            painter.restore()

        def _draw_border(self, painter: QPainter, width: float, color: QColor) -> None:
            if width < 1 or color.alphaF() == 0.0:
                return
            pen = QPen(color)
            pen.setWidthF(width)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            inset = width / 2
            rect = self.rect().adjusted(inset, inset, -inset, -inset)
            painter.drawRect(rect)

        def _paint_indicator(self, painter: QPainter, state: IndicatorState) -> None:
            if state.visibility.current < Animation.SNAP_THRESHOLD:
                return

            pos = state.position.toPoint()
            master_anim = state.visibility.current

            dim_factor = state.dim_effect.current if isinstance(state, BufferState) else 1.0
            self._draw_background(painter, pos, master_anim * dim_factor)

            if isinstance(state, RecordingState):
                pause_progress = state.pause_icon.current
                main_opacity = 1.0 - pause_progress

                if pause_progress > Animation.SNAP_THRESHOLD:
                    self._draw_pause_icon(painter, pos, pause_progress, master_anim, self.settings["rec_pause_color"])
                if main_opacity > Animation.SNAP_THRESHOLD:
                    self._draw_indicator(painter, pos, master_anim, self.settings["rec_color"], main_opacity)

            elif isinstance(state, BufferState):
                checkmark_progress = state.checkmark_icon.current
                main_opacity = 1.0 - checkmark_progress

                if main_opacity > Animation.SNAP_THRESHOLD:
                    self._draw_indicator(painter, pos, master_anim, self.settings["buf_color"],
                                         main_opacity * dim_factor)
                if checkmark_progress > Animation.SNAP_THRESHOLD:
                    self._draw_checkmark(painter, pos, checkmark_progress, master_anim,
                                         self.settings["buf_saved_color"], dim_factor)

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

            bg_alpha = self.settings["bg_opacity"] / 100.0
            alpha = int(255 * anim_value * bg_alpha)
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

            eased_progress = ease_in_out_cubic(icon_progress)
            base_alpha = master_anim * (self.settings["opacity"] / 100.0)
            final_alpha = int(255 * base_alpha * icon_progress)
            color = QColor(rgb_color)
            color.setAlpha(max(0, min(final_alpha, 255)))
            if color.alpha() < 1: return

            pen_width = max(2, int(size * Draw.PAUSE_PEN_WIDTH_RATIO))
            bar_height = size * Draw.PAUSE_BAR_HEIGHT_RATIO
            bar_spacing = size * Draw.PAUSE_BAR_SPACING_RATIO * eased_progress

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
                            rgb_color: int, dim_factor: float) -> None:
            size = self.settings["size"]
            eased_progress = ease_in_out_cubic(icon_progress)
            is_appearing = self.buf_state.checkmark_icon.target == 1.0

            base_alpha = master_anim * (self.settings["opacity"] / 100.0)
            final_alpha = int(255 * base_alpha * dim_factor * eased_progress)
            color = QColor(rgb_color)
            color.setAlpha(max(0, min(final_alpha, 255)))
            if color.alpha() < 1: return

            painter.save()
            pen_width = max(2, int(size * Draw.CHECKMARK_PEN_WIDTH_RATIO))
            pen = QPen(color, pen_width, cap=Qt.RoundCap, join=Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.translate(pos)

            pop_scale = 1.0 + math.sin(eased_progress * math.pi) * 0.1
            painter.scale(pop_scale, pop_scale)

            p1, p2, p3 = (p * size for p in (Draw.CHECKMARK_P1, Draw.CHECKMARK_P2, Draw.CHECKMARK_P3))
            path = QPainterPath()
            path.moveTo(p1)

            if is_appearing:
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

    def add_group(id_str: str, title: str, parent: Any = props) -> Any:
        grp = obs.obs_properties_create()
        obs.obs_properties_add_group(parent, id_str, title, obs.OBS_GROUP_NORMAL, grp)
        return grp

    app_grp = add_group("appearance", "Appearance")
    obs.obs_properties_add_int(app_grp, "size", STRINGS["size"], 5, 100, 1)
    obs.obs_properties_add_int(app_grp, "margin", STRINGS["margin"], 0, 100, 1)
    obs.obs_properties_add_int_slider(app_grp, "opacity", STRINGS["opacity"], 1, 100, 1)
    obs.obs_properties_add_int_slider(app_grp, "bg_opacity", STRINGS["bg_opacity"], 0, 100, 1)
    shape_list = obs.obs_properties_add_list(app_grp, "indicator_shape", STRINGS["indicator_shape"],
                                             obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(shape_list, STRINGS["shape_opts"])
    bg_shape_list = obs.obs_properties_add_list(app_grp, "bg_shape", STRINGS["bg_shape"], obs.OBS_COMBO_TYPE_LIST,
                                                obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(bg_shape_list, STRINGS["shape_opts"])
    obs.obs_properties_add_int_slider(app_grp, "bg_size_percent", STRINGS["bg_size_percent"], 100, 500, 5)

    rec_grp = add_group("recording", "Recording Indicator")
    corner_list_rec = obs.obs_properties_add_list(rec_grp, "corner_rec", "Position", obs.OBS_COMBO_TYPE_LIST,
                                                  obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(corner_list_rec, STRINGS["corner_opts"])
    obs.obs_properties_add_color(rec_grp, "rec_color", STRINGS["rec_color"])
    obs.obs_properties_add_color(rec_grp, "rec_pause_color", STRINGS["rec_pause_color"])

    buf_grp = add_group("buffer", "Replay Buffer Indicator")
    corner_list_buf = obs.obs_properties_add_list(buf_grp, "corner_buf", "Position", obs.OBS_COMBO_TYPE_LIST,
                                                  obs.OBS_COMBO_FORMAT_STRING)
    _add_list_options(corner_list_buf, STRINGS["corner_opts"])
    obs.obs_properties_add_color(buf_grp, "buf_color", STRINGS["buf_color"])
    obs.obs_properties_add_color(buf_grp, "buf_saved_color", STRINGS["buf_saved_color"])
    obs.obs_properties_add_float_slider(buf_grp, "checkmark_duration", STRINGS["checkmark_duration"], 0.5, 5.0, 0.1)
    obs.obs_properties_add_path(buf_grp, "save_sound_path", STRINGS["save_sound_path"], obs.OBS_PATH_FILE, "Sound files (*.wav *.mp3 *.ogg *.flac)", None)
    obs.obs_properties_add_int_slider(buf_grp, "save_sound_volume", STRINGS["save_sound_volume"], 0, 200, 1)

    fx_grp = add_group("effects", "Effects & Animations")
    obs.obs_properties_add_bool(fx_grp, "fade_effect", STRINGS["fade_effect"])
    obs.obs_properties_add_bool(fx_grp, "smooth_position", STRINGS["smooth_position"])
    obs.obs_properties_add_bool(fx_grp, "animate_pause", STRINGS["animate_pause"])
    obs.obs_properties_add_bool(fx_grp, "animate_checkmark", STRINGS["animate_checkmark"])
    obs.obs_properties_add_bool(fx_grp, "flash_on_save", STRINGS["flash_on_save"])
    obs.obs_properties_add_color(fx_grp, "flash_color", STRINGS["flash_color"])
    obs.obs_properties_add_float_slider(fx_grp, "flash_duration", STRINGS["flash_duration"], 0.1, 2.0, 0.1)

    border_grp = add_group("borders", STRINGS["borders_group"])
    obs.obs_properties_add_int(border_grp, "border_width", STRINGS["border_width"], 1, 50, 1)
    rec_border_grp = add_group("rec_border", "Recording Border", border_grp)
    obs.obs_properties_add_bool(rec_border_grp, "rec_border_enabled", STRINGS["rec_border_enabled"])
    obs.obs_properties_add_color(rec_border_grp, "rec_border_color", STRINGS["rec_border_color"])
    obs.obs_properties_add_color(rec_border_grp, "rec_pause_border_color", STRINGS["rec_pause_border_color"])
    obs.obs_properties_add_bool(rec_border_grp, "rec_pause_border_enabled", STRINGS["rec_pause_border_enabled"])
    buf_border_grp = add_group("buf_border", "Replay Buffer Border", border_grp)
    obs.obs_properties_add_bool(buf_border_grp, "buf_border_enabled", STRINGS["buf_border_enabled"])
    obs.obs_properties_add_color(buf_border_grp, "buf_border_color", STRINGS["buf_border_color"])
    obs.obs_properties_add_color(buf_border_grp, "buf_save_border_color", STRINGS["buf_save_border_color"])
    obs.obs_properties_add_bool(buf_border_grp, "buf_save_border_enabled", STRINGS["buf_save_border_enabled"])

    return props


def script_defaults(settings_obj: Any) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        if key.endswith("_color"):
            obs.obs_data_set_default_int(settings_obj, key, rgb_to_obs_color(value))
        elif isinstance(value, bool):
            obs.obs_data_set_default_bool(settings_obj, key, value)
        elif isinstance(value, float):
            obs.obs_data_set_default_double(settings_obj, key, value)
        elif isinstance(value, int):
            obs.obs_data_set_default_int(settings_obj, key, value)
        elif isinstance(value, str):
            obs.obs_data_set_default_string(settings_obj, key, value)


def get_settings_from_obs(settings_obj: Any) -> Dict[str, Any]:
    s = {}
    for key, value in DEFAULT_SETTINGS.items():
        if key.endswith("_color"):
            s[key] = obs_color_to_rgb(obs.obs_data_get_int(settings_obj, key))
        elif isinstance(value, bool):
            s[key] = obs.obs_data_get_bool(settings_obj, key)
        elif isinstance(value, float):
            s[key] = obs.obs_data_get_double(settings_obj, key)
        elif isinstance(value, int):
            s[key] = obs.obs_data_get_int(settings_obj, key)
        elif isinstance(value, str):
            s[key] = obs.obs_data_get_string(settings_obj, key)
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
