import obspython as obs
import threading
import sys
import os
import time
import math
from enum import Enum
import ctypes

# PyQt5 availability check
HAS_PYQT5 = False
try:
    from PyQt5.QtWidgets import QApplication, QWidget
    from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QObject, pyqtSignal, QMutex, QMutexLocker, QPointF
    from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QGuiApplication

    HAS_PYQT5 = True
except ImportError:
    pass

# Глобальная переменная overlay_app
overlay_app = None


# Constants and enums
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


ANIMATION_SPEED = 0.15
TRANSITION_SPEED = 0.3
THREAD_JOIN_TIMEOUT = 2.0

DEFAULT_SETTINGS = {
    "corner_rec": "top-right",
    "corner_buf": "top-right",
    "size": 10,
    "margin": 10,
    "opacity": 50,
    "rec_color": 0xFF5555,  # Красный в формате RRGGBB
    "rec_pause_color": 0xFFAA00,  # Оранжевый
    "buf_color": 0x55FF55,  # Зеленый
    "buf_saved_color": 0x5555FF,  # Синий
    "bg_opacity": 50,
    "bg_size_percent": 300,
    "indicator_shape": "circle",
    "bg_shape": "circle",
    "pulse_effect": True,
    "fade_effect": True,
    "smooth_position": True
}

# Global state
settings = DEFAULT_SETTINGS.copy()

rec_status = {
    "active": False,
    "paused": False,
    "anim": 0.0,
}

buf_status = {
    "active": False,
    "saved": False,
    "saved_time": 0.0,
    "anim": 0.0,
    "current_pos": (0.0, 0.0),
    "target_pos": (0.0, 0.0),
    "checkmark_anim": 0.0,
    "transition_anim": 0.0,
    "prev_state": None
}

# String resources
STRINGS = {
    "description": "Recording and replay buffer indicators with animations",
    "size": "Indicator Size",
    "margin": "Margin",
    "opacity": "Opacity (%)",
    "rec_color": "Active Color",
    "rec_pause_color": "Paused Color",
    "buf_color": "Active Color",
    "buf_saved_color": "Saved Color",
    "bg_opacity": "Background Opacity (%)",
    "bg_size_percent": "Background Size (%)",
    "indicator_shape": "Shape",
    "bg_shape": "Background Shape",
    "pulse_effect": "Pulse Effect",
    "fade_effect": "Fade Effect",
    "smooth_position": "Smooth Position Animation",
    "shape_opts": [("Circle", "circle"), ("Square", "square"), ("Rounded", "rounded")],
    "corner_opts": [
        ("Top Left", "top-left"),
        ("Top Right", "top-right"),
        ("Bottom Left", "bottom-left"),
        ("Bottom Right", "bottom-right"),
        ("Off", "off")
    ]
}


# Helper functions
def obs_color_to_rgb(obs_color):
    """Convert OBS color (0xAABBGGRR) to RGB integer (0xRRGGBB)"""
    # Extract components
    aa = (obs_color >> 24) & 0xFF
    bb = (obs_color >> 16) & 0xFF
    gg = (obs_color >> 8) & 0xFF
    rr = obs_color & 0xFF

    # Rebuild as 0xRRGGBB
    return (rr << 16) | (gg << 8) | bb


def int_to_hex(color_int):
    """Convert RGB integer to hex string (#RRGGBB)"""
    return f"#{(color_int >> 16) & 0xFF:02X}{(color_int >> 8) & 0xFF:02X}{color_int & 0xFF:02X}"


def ease_in_out_sine(t):
    return -(math.cos(math.pi * t) - 1) / 2


def lerp(start, end, alpha):
    return start + (end - start) * alpha


# Custom easing function for checkmark
def cubic_bezier_ease(t):
    """Cubic bezier easing function"""
    return 1 - (1 - t) ** 3


# PyQt5 components
if HAS_PYQT5:
    class SignalEmitter(QObject):
        rec_status_changed = pyqtSignal(bool, bool)
        buf_status_changed = pyqtSignal(bool, bool)
        settings_updated = pyqtSignal()


    class OverlayWindow(QWidget):
        def __init__(self, emitter):
            super().__init__()
            self.emitter = emitter
            self.animation_timer = QTimer(self)
            self.update_timer = QTimer(self)
            self.closing = False
            self.positions_cache = {}
            self.current_screen_geometry = QRect()

            self.init_ui()
            self.setup_signals()

        def init_ui(self):
            self.setWindowTitle("OBS Status Overlay")
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)

            self.setWindowOpacity(settings["opacity"] / 100.0)
            self.update_position()
            self.setup_win32_attributes()

        def setup_win32_attributes(self):
            if os.name != 'nt':
                return

            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)

                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                WS_EX_TRANSPARENT = 0x00000020
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            except Exception:
                pass

        def setup_signals(self):
            self.emitter.rec_status_changed.connect(self.update_rec_status)
            self.emitter.buf_status_changed.connect(self.update_buf_status)
            self.emitter.settings_updated.connect(self.reload_settings)

            self.animation_timer.timeout.connect(self.update_animations)
            self.animation_timer.start(16)

            self.update_timer.timeout.connect(self.update_position)
            self.update_timer.start(1000)

        def update_rec_status(self, active, paused):
            if self.closing:
                return

            rec_status["active"] = active
            rec_status["paused"] = paused
            rec_status["anim"] = 0.0 if active and settings["fade_effect"] else 1.0

        def update_buf_status(self, active, saved):
            if self.closing:
                return

            # Сохраняем предыдущее состояние для плавного перехода
            prev_active = buf_status["active"]
            prev_saved = buf_status["saved"]

            buf_status["active"] = active
            buf_status["saved"] = saved

            # Если состояние изменилось, запускаем анимацию перехода
            if active != prev_active or saved != prev_saved:
                buf_status["prev_state"] = {
                    "active": prev_active,
                    "saved": prev_saved
                }
                buf_status["transition_anim"] = 0.0

            if saved:
                buf_status["saved_time"] = time.time()
                buf_status["checkmark_anim"] = 0.0

            buf_status["anim"] = 0.0 if (active or saved) and settings["fade_effect"] else 1.0

        def reload_settings(self):
            if self.closing:
                return

            self.setWindowOpacity(settings["opacity"] / 100.0)
            self.positions_cache.clear()
            self.update_position()

        def update_position(self):
            if self.closing:
                return

            screen = QGuiApplication.primaryScreen()
            if not screen:
                return

            screen_geometry = screen.geometry()
            if screen_geometry != self.current_screen_geometry:
                self.setGeometry(screen_geometry)
                self.current_screen_geometry = screen_geometry
                self.positions_cache.clear()

        def paintEvent(self, event):
            if self.closing:
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw recording indicator
            if settings["corner_rec"] != "off" and rec_status["anim"] > 0.005:
                pos = self.calculate_position(settings["corner_rec"])
                if pos:
                    self.draw_background(painter, pos, rec_status["anim"], settings)
                    color_hex = settings["rec_pause_color"] if rec_status["paused"] else settings["rec_color"]
                    self.draw_indicator(painter, pos, rec_status, color_hex, settings)

            # Draw buffer indicator
            if settings["corner_buf"] != "off" and buf_status["anim"] > 0.005:
                index = 1 if (rec_status["active"] and
                              settings["corner_rec"] == settings["corner_buf"] and
                              settings["corner_rec"] != "off") else 0

                target_pos = self.calculate_position(settings["corner_buf"], index)
                if target_pos:
                    buf_status["target_pos"] = (target_pos.x(), target_pos.y())
                    if buf_status["current_pos"] == (0.0, 0.0):
                        buf_status["current_pos"] = buf_status["target_pos"]

                    current_pos = QPoint(*map(int, buf_status["current_pos"]))

                    # Рисуем фон
                    self.draw_background(painter, current_pos, buf_status["anim"], settings)

                    # Если есть предыдущее состояние, рисуем его с плавным переходом
                    if buf_status["prev_state"] and buf_status["transition_anim"] < 1.0:
                        # Рисуем предыдущее состояние
                        if buf_status["prev_state"]["saved"] and (time.time() - buf_status["saved_time"] < 1.0):
                            saved_color = settings["buf_saved_color"]
                            self.draw_checkmark(painter, current_pos, buf_status["checkmark_anim"], saved_color,
                                                settings, 1.0 - buf_status["transition_anim"])
                        else:
                            color_hex = settings["buf_color"]
                            self.draw_indicator(painter, current_pos, buf_status, color_hex, settings,
                                                1.0 - buf_status["transition_anim"])

                    # Рисуем текущее состояние
                    if buf_status["saved"] and (time.time() - buf_status["saved_time"] < 1.0):
                        saved_color = settings["buf_saved_color"]
                        self.draw_checkmark(painter, current_pos, buf_status["checkmark_anim"], saved_color, settings,
                                            buf_status["transition_anim"])
                    else:
                        color_hex = settings["buf_color"]
                        self.draw_indicator(painter, current_pos, buf_status, color_hex, settings,
                                            buf_status["transition_anim"])
            else:
                buf_status["current_pos"] = (0.0, 0.0)

        def calculate_position(self, corner, index=0):
            if not self.current_screen_geometry.isValid():
                return None

            size = settings["size"]
            margin = settings["margin"]
            bg_size = int(size * settings["bg_size_percent"] / 100)
            radius = bg_size // 2

            if not radius:
                return None

            cache_key = f"{corner}_{index}_{self.width()}x{self.height()}"
            if cache_key in self.positions_cache:
                return self.positions_cache[cache_key]

            width = self.width()
            height = self.height()
            offset = index * (bg_size + margin)

            if corner == "top-left":
                pos = QPoint(margin + radius + offset, margin + radius)
            elif corner == "top-right":
                pos = QPoint(width - margin - radius - offset, margin + radius)
            elif corner == "bottom-left":
                pos = QPoint(margin + radius + offset, height - margin - radius)
            elif corner == "bottom-right":
                pos = QPoint(width - margin - radius - offset, height - margin - radius)
            else:
                return None

            self.positions_cache[cache_key] = pos
            return pos

        def draw_background(self, painter, pos, anim_value, current_settings):
            if not pos:
                return

            size = current_settings["size"]
            if size <= 0:
                return

            bg_size = int(size * current_settings["bg_size_percent"] / 100)
            if bg_size <= 0:
                return

            if current_settings["pulse_effect"]:
                pulse_scale = ease_in_out_sine((anim_value * 2) % 1)
                pulse_factor = 0.1 + 0.05 * pulse_scale
                bg_size = int(bg_size * (1 + pulse_factor))

            bg_radius = bg_size // 2

            alpha = int(255 * anim_value * (current_settings["bg_opacity"] / 100.0))
            alpha = max(0, min(alpha, 255))
            draw_color = QColor(0, 0, 0, alpha)

            painter.setBrush(QBrush(draw_color))
            painter.setPen(Qt.NoPen)

            rect = QRect(pos.x() - bg_radius, pos.y() - bg_radius, bg_size, bg_size)

            if current_settings["bg_shape"] == "circle":
                painter.drawEllipse(rect)
            elif current_settings["bg_shape"] == "square":
                painter.drawRect(rect)
            else:
                roundness = min(rect.width(), rect.height()) * 0.3
                painter.drawRoundedRect(rect, roundness, roundness)

        def draw_indicator(self, painter, pos, status, color_int, current_settings, opacity_mult=1.0):
            if not pos:
                return

            size = current_settings["size"]
            if size <= 0:
                return

            radius = size // 2

            color_hex = int_to_hex(color_int)
            draw_color = QColor(color_hex)
            if not draw_color.isValid():
                draw_color = QColor(255, 0, 255)

            final_alpha = int(255 * status["anim"] * (current_settings["opacity"] / 100.0) * opacity_mult)
            final_alpha = max(0, min(final_alpha, 255))
            draw_color.setAlpha(final_alpha)

            painter.setBrush(QBrush(draw_color))
            painter.setPen(Qt.NoPen)

            rect = QRect(pos.x() - radius, pos.y() - radius, size, size)

            if current_settings["indicator_shape"] == "circle":
                painter.drawEllipse(rect)
            elif current_settings["indicator_shape"] == "square":
                painter.drawRect(rect)
            else:
                roundness = min(rect.width(), rect.height()) * 0.3
                painter.drawRoundedRect(rect, roundness, roundness)

        def draw_checkmark(self, painter, pos, progress, color_int, current_settings, opacity_mult=1.0):
            """Draw a smooth, beautiful checkmark with custom easing"""
            if progress <= 0.0:
                return

            # Apply cubic bezier easing for smooth animation
            eased_progress = cubic_bezier_ease(progress)

            # Larger checkmark size
            check_size = current_settings["size"] * 1.8

            # Thicker line
            pen_width = max(3, int(current_settings["size"] * 0.25))

            # Get color
            color_hex = int_to_hex(color_int)
            draw_color = QColor(color_hex)
            if not draw_color.isValid():
                return

            # Set opacity
            base_alpha = buf_status["anim"] * (current_settings["opacity"] / 100.0) * opacity_mult
            alpha = int(255 * base_alpha)
            draw_color.setAlpha(alpha)

            # Create pen with round caps and joins
            pen = QPen(draw_color, pen_width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)

            # Define checkmark points (relative to center)
            points = [
                QPointF(-0.25 * check_size, 0.0),  # Start point
                QPointF(0.0, 0.25 * check_size),  # Middle point
                QPointF(0.4 * check_size, -0.25 * check_size)  # End point
            ]

            # Adjust points to absolute position
            center = QPointF(pos.x(), pos.y())
            absolute_points = [center + p for p in points]

            # Create a path for smooth curves
            path = QPainterPath()
            path.moveTo(absolute_points[0])

            # Draw the checkmark in two parts with easing
            if eased_progress < 0.5:
                # First segment: from start to middle point
                segment_progress = eased_progress / 0.5
                end_point = absolute_points[0] + segment_progress * (absolute_points[1] - absolute_points[0])
                path.lineTo(end_point)
            else:
                # Draw full first segment
                path.lineTo(absolute_points[1])

                # Second segment: from middle to end point
                segment_progress = (eased_progress - 0.5) / 0.5
                end_point = absolute_points[1] + segment_progress * (absolute_points[2] - absolute_points[1])
                path.lineTo(end_point)

            # Draw the path
            painter.drawPath(path)

        def update_animations(self):
            if self.closing:
                return

            updated = False

            # Recording animation
            target_anim = 1.0 if rec_status["active"] else 0.0
            if settings["fade_effect"]:
                rec_status["anim"] = lerp(rec_status["anim"], target_anim, ANIMATION_SPEED)
                updated |= abs(rec_status["anim"] - target_anim) > 0.005
            else:
                updated |= rec_status["anim"] != target_anim
                rec_status["anim"] = target_anim

            # Buffer animation
            target_anim = 1.0 if buf_status["active"] or buf_status["saved"] else 0.0
            if settings["fade_effect"]:
                buf_status["anim"] = lerp(buf_status["anim"], target_anim, ANIMATION_SPEED)
                updated |= abs(buf_status["anim"] - target_anim) > 0.005
            else:
                updated |= buf_status["anim"] != target_anim
                buf_status["anim"] = target_anim

            # Position animation
            if settings["smooth_position"]:
                new_x = lerp(buf_status["current_pos"][0], buf_status["target_pos"][0], ANIMATION_SPEED)
                new_y = lerp(buf_status["current_pos"][1], buf_status["target_pos"][1], ANIMATION_SPEED)
                buf_status["current_pos"] = (new_x, new_y)
                updated |= (abs(new_x - buf_status["target_pos"][0]) > 0.5 or
                            abs(new_y - buf_status["target_pos"][1]) > 0.5)

            # Transition animation
            if buf_status["prev_state"]:
                buf_status["transition_anim"] = min(1.0, buf_status["transition_anim"] + TRANSITION_SPEED)
                updated = True

                # Если переход завершен, сбрасываем предыдущее состояние
                if buf_status["transition_anim"] >= 1.0:
                    buf_status["prev_state"] = None

            # Checkmark animation
            if buf_status["saved"] and buf_status["saved_time"] > 0:
                elapsed = time.time() - buf_status["saved_time"]
                if elapsed < 1.0:
                    new_progress = min(elapsed / 1.0, 1.0)
                    if abs(new_progress - buf_status["checkmark_anim"]) > 0.01:
                        buf_status["checkmark_anim"] = new_progress
                        updated = True
                else:
                    # Когда анимация завершена, сбрасываем состояние сохранения
                    if buf_status["checkmark_anim"] != 0.0:
                        buf_status["checkmark_anim"] = 0.0
                        buf_status["saved"] = False
                        updated = True

            if updated:
                self.update()


    class OverlayApp:
        def __init__(self):
            self.app = None
            self.overlay = None
            self.emitter = SignalEmitter()

        def run(self):
            self.app = QApplication(sys.argv)
            self.overlay = OverlayWindow(self.emitter)
            self.overlay.show()
            self.app.exec_()

        def stop(self):
            if self.overlay:
                self.overlay.close()
            if self.app:
                self.app.quit()


# OBS event handling
def event_handler(event):
    if not HAS_PYQT5 or overlay_app is None:
        return

    if event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTING:
        overlay_app.emitter.rec_status_changed.emit(True, False)
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED:
        overlay_app.emitter.rec_status_changed.emit(False, False)
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_PAUSED:
        overlay_app.emitter.rec_status_changed.emit(True, True)
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_UNPAUSED:
        overlay_app.emitter.rec_status_changed.emit(True, False)
    elif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED:
        overlay_app.emitter.buf_status_changed.emit(True, False)
    elif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED:
        overlay_app.emitter.buf_status_changed.emit(obs.obs_frontend_replay_buffer_active(), True)
    elif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED:
        overlay_app.emitter.buf_status_changed.emit(False, False)


# OBS script interface
def script_description():
    return STRINGS["description"]


def script_properties():
    props = obs.obs_properties_create()

    # Appearance settings
    grp = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "appearance", "Appearance", obs.OBS_GROUP_NORMAL, grp)
    obs.obs_properties_add_int(grp, "size", STRINGS["size"], 5, 100, 1)
    obs.obs_properties_add_int(grp, "margin", STRINGS["margin"], 0, 100, 1)
    obs.obs_properties_add_int_slider(grp, "opacity", STRINGS["opacity"], 1, 100, 1)

    shape_list = obs.obs_properties_add_list(grp, "indicator_shape", STRINGS["indicator_shape"],
                                             obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    for label, value in STRINGS["shape_opts"]:
        obs.obs_property_list_add_string(shape_list, label, value)

    bg_shape_list = obs.obs_properties_add_list(grp, "bg_shape", STRINGS["bg_shape"],
                                                obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    for label, value in STRINGS["shape_opts"]:
        obs.obs_property_list_add_string(bg_shape_list, label, value)

    obs.obs_properties_add_int_slider(grp, "bg_opacity", STRINGS["bg_opacity"], 0, 100, 1)
    obs.obs_properties_add_int_slider(grp, "bg_size_percent", STRINGS["bg_size_percent"], 100, 300, 5)

    # Recording settings
    grp = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "recording", "Recording Indicator", obs.OBS_GROUP_NORMAL, grp)

    corner_list = obs.obs_properties_add_list(grp, "corner_rec", "Position",
                                              obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    for label, value in STRINGS["corner_opts"]:
        obs.obs_property_list_add_string(corner_list, label, value)

    obs.obs_properties_add_color(grp, "rec_color", STRINGS["rec_color"])
    obs.obs_properties_add_color(grp, "rec_pause_color", STRINGS["rec_pause_color"])

    # Buffer settings
    grp = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "buffer", "Replay Buffer Indicator", obs.OBS_GROUP_NORMAL, grp)

    corner_list = obs.obs_properties_add_list(grp, "corner_buf", "Position",
                                              obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    for label, value in STRINGS["corner_opts"]:
        obs.obs_property_list_add_string(corner_list, label, value)

    obs.obs_properties_add_color(grp, "buf_color", STRINGS["buf_color"])
    obs.obs_properties_add_color(grp, "buf_saved_color", STRINGS["buf_saved_color"])

    # Effects
    grp = obs.obs_properties_create()
    obs.obs_properties_add_group(props, "effects", "Effects", obs.OBS_GROUP_NORMAL, grp)
    obs.obs_properties_add_bool(grp, "pulse_effect", STRINGS["pulse_effect"])
    obs.obs_properties_add_bool(grp, "fade_effect", STRINGS["fade_effect"])
    obs.obs_properties_add_bool(grp, "smooth_position", STRINGS["smooth_position"])

    return props


def script_defaults(settings_obj):
    for key, value in DEFAULT_SETTINGS.items():
        if key.endswith("_color"):
            # Конвертируем цвет из RRGGBB в AABBGGRR с альфа=FF
            rr = (value >> 16) & 0xFF
            gg = (value >> 8) & 0xFF
            bb = value & 0xFF
            obs_color = (0xFF << 24) | (bb << 16) | (gg << 8) | rr
            obs.obs_data_set_int(settings_obj, key, obs_color)
        elif isinstance(value, bool):
            obs.obs_data_set_bool(settings_obj, key, value)
        elif isinstance(value, int):
            obs.obs_data_set_int(settings_obj, key, value)
        elif isinstance(value, str):
            obs.obs_data_set_string(settings_obj, key, value)


def script_update(settings_obj):
    # Update settings from OBS
    settings["corner_rec"] = obs.obs_data_get_string(settings_obj, "corner_rec") or DEFAULT_SETTINGS["corner_rec"]
    settings["corner_buf"] = obs.obs_data_get_string(settings_obj, "corner_buf") or DEFAULT_SETTINGS["corner_buf"]
    settings["size"] = obs.obs_data_get_int(settings_obj, "size") or DEFAULT_SETTINGS["size"]
    settings["margin"] = obs.obs_data_get_int(settings_obj, "margin") or DEFAULT_SETTINGS["margin"]
    settings["opacity"] = obs.obs_data_get_int(settings_obj, "opacity") or DEFAULT_SETTINGS["opacity"]
    settings["bg_opacity"] = obs.obs_data_get_int(settings_obj, "bg_opacity") or DEFAULT_SETTINGS["bg_opacity"]
    settings["bg_size_percent"] = obs.obs_data_get_int(settings_obj, "bg_size_percent") or DEFAULT_SETTINGS[
        "bg_size_percent"]
    settings["indicator_shape"] = obs.obs_data_get_string(settings_obj, "indicator_shape") or DEFAULT_SETTINGS[
        "indicator_shape"]
    settings["bg_shape"] = obs.obs_data_get_string(settings_obj, "bg_shape") or DEFAULT_SETTINGS["bg_shape"]
    settings["pulse_effect"] = obs.obs_data_get_bool(settings_obj, "pulse_effect")
    settings["fade_effect"] = obs.obs_data_get_bool(settings_obj, "fade_effect")
    settings["smooth_position"] = obs.obs_data_get_bool(settings_obj, "smooth_position")

    # Update colors with conversion
    color_keys = ["rec_color", "rec_pause_color", "buf_color", "buf_saved_color"]
    for key in color_keys:
        obs_color = obs.obs_data_get_int(settings_obj, key)
        settings[key] = obs_color_to_rgb(obs_color) if obs_color != 0 else DEFAULT_SETTINGS[key]

    # Notify GUI if available
    if HAS_PYQT5 and overlay_app is not None:
        overlay_app.emitter.settings_updated.emit()


def script_load(settings_obj):
    global overlay_app

    # First update settings
    script_update(settings_obj)

    # Register event handler
    obs.obs_frontend_add_event_callback(event_handler)

    # Initialize overlay if PyQt5 is available
    if HAS_PYQT5:
        overlay_app = OverlayApp()

        # Start GUI in separate thread
        def run_gui():
            overlay_app.run()

        threading.Thread(target=run_gui, daemon=True).start()

        # Initialize current status after short delay
        time.sleep(0.2)
        rec_active = obs.obs_frontend_recording_active()
        rec_paused = obs.obs_frontend_recording_paused() if rec_active else False
        buf_active = obs.obs_frontend_replay_buffer_active()

        overlay_app.emitter.rec_status_changed.emit(rec_active, rec_paused)
        overlay_app.emitter.buf_status_changed.emit(buf_active, False)


def script_unload():
    global overlay_app

    # Unregister event handler
    obs.obs_frontend_remove_event_callback(event_handler)

    # Cleanup overlay
    if HAS_PYQT5 and overlay_app is not None:
        overlay_app.stop()
        overlay_app = None