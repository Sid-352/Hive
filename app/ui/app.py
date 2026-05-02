import sys
import math
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QFrame, QLabel, QPushButton, QStackedWidget, QMessageBox, 
                             QGraphicsDropShadowEffect, QGraphicsOpacityEffect)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, Property, QTimer, QPoint
from PySide6.QtCore import QEvent
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QIcon, QPixmap, QShortcut, QKeySequence, QRadialGradient

from app.ui.theme import P, F
from app.ui.signals import QtSignalBus
from app.core.events import HiveEvent


class NavButton(QPushButton):
    def __init__(self, text: str, screen_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setText(f"      {text}")
        self.screen_name = screen_name
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(48)
        self._hover_opacity = 0
        self._hover_anim = QPropertyAnimation(self, b"hoverOpacity")
        self._hover_anim.setDuration(200)

    def mousePressEvent(self, event):
        if self.isChecked():
            return
        super().mousePressEvent(event)

    @Property(float)
    def hoverOpacity(self): return self._hover_opacity
    @hoverOpacity.setter
    def hoverOpacity(self, v): self._hover_opacity = v; self.update()

    def enterEvent(self, event):
        self._hover_anim.setEndValue(1.0); self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.setEndValue(0.0); self._hover_anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = 7; cx, cy = 24, 24
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = cx + size * math.cos(angle); y = cy + size * math.sin(angle)
            if i == 0: path.moveTo(x, y)
            else: path.lineTo(x, y)
        path.closeSubpath()
        is_active = self.isChecked()
        if self._hover_opacity > 0 and not is_active:
            col = QColor(P.GOLD); col.setAlphaF(self._hover_opacity * 0.15)
            painter.fillPath(path, col)
        color = QColor(P.GOLD if is_active else P.TEXT_DIM)
        if is_active: painter.fillPath(path, color)
        else:
            painter.setPen(QPen(color, 1.2)); painter.drawPath(path)

class PulseLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__("⬢", parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("PulseIcon")
        self.effect = QGraphicsDropShadowEffect(self)
        self.effect.setBlurRadius(0); self.effect.setColor(QColor(P.GOLD)); self.effect.setOffset(0)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"blurRadius")
        self.anim.setDuration(600); self.anim.setStartValue(0); self.anim.setEndValue(18)
        self.anim.setEasingCurve(QEasingCurve.OutBack)
    def pulse(self): self.anim.stop(); self.anim.start()

class FlashLabel(QLabel):
    def __init__(self, text="—", parent=None):
        super().__init__(text, parent)
        self._flash = 0
        self._anim = QPropertyAnimation(self, b"flash")
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    @Property(float)
    def flash(self): return self._flash
    @flash.setter
    def flash(self, v): self._flash = v; self.update()

    def setText(self, text):
        if text != self.text():
            super().setText(text)
            self._anim.setStartValue(1.0); self._anim.setEndValue(0.0)
            self._anim.start()
        else:
            super().setText(text)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._flash > 0:
            painter = QPainter(self)
            painter.setOpacity(self._flash * 0.4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(P.GOLD))
            painter.drawRect(self.rect())

class OdometerLabel(QLabel):
    def __init__(self, text="0", parent=None):
        super().__init__(text, parent)
        self._value = 0
        self._display_value = 0.0
        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(1000)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    @Property(float)
    def displayValue(self): return self._display_value
    @displayValue.setter
    def displayValue(self, v):
        self._display_value = v
        self.setText(str(int(v)))

    def setValue(self, val):
        try:
            target = int(val)
            if target != self._value:
                self._value = target
                self._anim.stop()
                self._anim.setStartValue(self._display_value)
                self._anim.setEndValue(float(target))
                self._anim.start()
        except (ValueError, TypeError):
            self.setText(str(val))

class HexGlyph(QWidget):
    def __init__(self, uuid_str: str, size=48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.uuid_hash = hash(uuid_str)
        self.size_val = size

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = self.width() * 0.4
        
        path = self._hex_path(cx, cy, radius)
        painter.setPen(QPen(QColor(P.GOLD), 1.5))
        painter.setBrush(QColor(P.VOID))
        painter.drawPath(path)
        
        painter.setPen(QPen(QColor(P.AMBER), 1.0))
        h = self.uuid_hash
        for i in range(6):
            if (h >> i) & 1:
                angle = math.radians(60 * i - 30)
                px = cx + radius * math.cos(angle)
                py = cy + radius * math.sin(angle)
                painter.drawLine(QPoint(cx, cy), QPoint(px, py))
            
            if (h >> (i + 6)) & 1:
                sub_r = radius * 0.4
                angle = math.radians(60 * i - 30)
                px = cx + sub_r * math.cos(angle)
                py = cy + sub_r * math.sin(angle)
                painter.drawEllipse(QPoint(px, py), 2, 2)

    def _hex_path(self, cx, cy, size):
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            px = cx + size * math.cos(angle)
            py = cy + size * math.sin(angle)
            if i == 0: path.moveTo(px, py)
            else: path.lineTo(px, py)
        path.closeSubpath()
        return path

class VelocitySparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.history = []
        self.max_history = 60
        self.max_val = 1.0

    def add_value(self, val):
        self.history.append(val)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        self.max_val = max(max(self.history) if self.history else 1.0, 1.0)
        self.update()

    def clear(self):
        self.history = []
        self.max_val = 1.0
        self.update()

    def paintEvent(self, event):
        if not self.history: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        step = w / (self.max_history - 1)
        
        path = QPainterPath()
        for i, val in enumerate(self.history):
            x = i * step
            norm = val / self.max_val
            y = h - (norm * h * 0.8) - (h * 0.1)
            if i == 0: path.moveTo(x, y)
            else: path.lineTo(x, y)
            
        painter.setPen(QPen(QColor(P.GOLD), 1.5))
        painter.drawPath(path)
        
        path.lineTo(w, h); path.lineTo(0, h); path.closeSubpath()
        painter.setOpacity(0.1)
        painter.fillPath(path, QColor(P.GOLD))

class DiagnosticPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiagnosticPanel")
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 15, 20, 15); layout.setSpacing(6)
        hdr_row = QHBoxLayout()
        header = QLabel("DIAGNOSTIC"); header.setObjectName("Label")
        hdr_row.addWidget(header); hdr_row.addStretch()
        self.pulse_icon = PulseLabel(); hdr_row.addWidget(self.pulse_icon); layout.addLayout(hdr_row)
        layout.addSpacing(4)
        self.agent_val = self._add_row(layout, "AGENT")
        self.net_val = self._add_row(layout, "P-LINK")
        self.net_val.setObjectName("PhysicalLinkValue")
        self.role_val = self._add_row(layout, "L-LINK")
        self.role_val.setObjectName("LogicalLinkValue")
        self.vitality_val = self._add_row(layout, "VIT", is_odometer=True)
        self.set_vitality(0)

    def _add_row(self, layout, key, is_odometer=False):
        row = QHBoxLayout()
        key_lbl = QLabel(f"{key}:"); key_lbl.setObjectName("Label"); key_lbl.setFixedWidth(50)
        key_font = key_lbl.font()
        key_font.setUnderline(False)
        key_font.setOverline(False)
        key_font.setStrikeOut(False)
        key_lbl.setFont(key_font)
        val_lbl = OdometerLabel("0") if is_odometer else FlashLabel("—")
        val_lbl.setObjectName("Data")
        val_font = val_lbl.font()
        val_font.setUnderline(False)
        val_font.setOverline(False)
        val_font.setStrikeOut(False)
        val_lbl.setFont(val_font)
        row.addWidget(key_lbl); row.addWidget(val_lbl); layout.addLayout(row)
        return val_lbl

    def set_agent(self, name): self.agent_val.setText(name.upper())
    def set_network_state(self, state):
        mapping = {
            "HOST": "GROUP OWNER", 
            "CLIENT": "PEER NODE", 
            "OFFLINE": "OFFLINE",
            "ASSOCIATING": "ASSOCIATING..."
        }
        text = mapping.get(state, state)
        color = { 
            "GROUP OWNER": P.GOLD, 
            "PEER NODE": P.AMBER, 
            "OFFLINE": P.TEXT_DIM,
            "ASSOCIATING...": P.HONEY 
        }.get(text, P.TEXT_DIM)
        self.net_val.setText(text); self.net_val.setStyleSheet(f"color: {color};")
    def set_swarm_role(self, role):
        mapping = {"HOST": "LEADER", "CLIENT": "WORKER", "NONE": "—"}
        text = mapping.get(role, role)
        color = P.LEADER if text == "LEADER" else P.WORKER if text == "WORKER" else P.TEXT_DIM
        self.role_val.setText(text); self.role_val.setStyleSheet(f"color: {color};")
    def set_vitality(self, score):
        if hasattr(self.vitality_val, "setValue"):
            self.vitality_val.setValue(score)
        else:
            self.vitality_val.setText(str(score))
        connected = score > 0
        color = P.ALIVE if connected else P.SEVERED
        self.vitality_val.setStyleSheet(f"color: {color};")
    def telemetry_pulse(self): self.pulse_icon.pulse()


class HiveRootWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RootWidget")
        self.setMouseTracking(True)
        self._shift_y = 0.0
        self._bg_pixmap = None
        self._particles = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
        self._timer.start(16)

    def _update_animation(self):
        self._shift_y += 0.4
        for p in self._particles[:]:
            p['opacity'] -= 0.015
            p['size'] += 0.15
            if p['opacity'] <= 0:
                self._particles.remove(p)
        self.update()

    def mouseMoveEvent(self, event):
        if event.pos().x() > 190:
            if not self._particles or (event.pos() - self._particles[-1]['pos']).manhattanLength() > 20:
                self._particles.append({'pos': event.pos(), 'opacity': 0.35, 'size': 5.0})
        super().mouseMoveEvent(event)

    def resizeEvent(self, event):
        self._bg_pixmap = None
        super().resizeEvent(event)

    def _render_full_bg(self):
        radius = 35; w = radius * 1.5; h = radius * math.sqrt(3)
        pix = QPixmap(self.width(), int(self.height() + h + 2))
        pix.fill(Qt.transparent)
        
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(P.GOLD)); pen.setWidth(2)
        painter.setOpacity(0.05); painter.setPen(pen)

        content_center = 190 + (self.width() - 190) / 2
        global_shift_x = content_center % w
        
        for row in range(-1, int(pix.height() / h) + 1):
            y = row * h
            for col in range(-1, int(pix.width() / w) + 1):
                x = col * w + global_shift_x
                final_y = y + (h / 2 if col % 2 else 0)
                self._draw_hex(painter, x, final_y, radius)
        
        painter.end()
        return pix

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(P.ABYSS))

        if not self._bg_pixmap or self._bg_pixmap.size().width() != self.width():
            self._bg_pixmap = self._render_full_bg()

        radius = 35; h = radius * math.sqrt(3)
        offset_y = self._shift_y % h
        
        painter.drawPixmap(0, int(offset_y - h), self._bg_pixmap)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(P.GOLD), 1.0))
        for p in self._particles:
            painter.setOpacity(p['opacity'])
            self._draw_hex(painter, p['pos'].x(), p['pos'].y(), p['size'])
        painter.setOpacity(1.0)

    def _draw_hex(self, painter, cx, cy, size):
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i)
            px = cx + size * math.cos(angle); py = cy + size * math.sin(angle)
            if i == 0: path.moveTo(px, py)
            else: path.lineTo(px, py)
        path.closeSubpath()
        painter.drawPath(path)

class BreathingLogo(QLabel):
    def __init__(self, parent=None):
        super().__init__("HIVE", parent)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("Logo")

class ConsoleScreen(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("ConsoleScreen")
        from PySide6.QtWidgets import QTextEdit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        hdr = QLabel("SYSTEM CONSOLE")
        hdr.setObjectName("Header")
        layout.addWidget(hdr)
        
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFrameStyle(QFrame.NoFrame)
        self.output.setObjectName("ConsoleOutput")
        layout.addWidget(self.output)
        
        app.bus.log_message.connect(self.append_log)
        
    def append_log(self, msg):
        self.output.append(msg)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

class HiveMainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.bus = QtSignalBus.get()
        self._event_adapter = None
        self._anims = []
        self._fade_anims = {} 
        self._vitality_color = P.TEXT_DIM
        
        self.setWindowTitle("HIVE  //  P2P NETWORK")
        self.setWindowIcon(self._generate_icon())
        self.resize(1000, 680); self.setMinimumSize(900, 600)
        
        self.setWindowOpacity(0.0)
        self._entrance_anim = QPropertyAnimation(self, b"windowOpacity")
        self._entrance_anim.setDuration(500)
        self._entrance_anim.setStartValue(0.0)
        self._entrance_anim.setEndValue(1.0)
        self._entrance_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._build_ui()
        self._setup_signals()
        self._setup_shortcuts()
        
        if self.controller:
            self.controller.bind_ui(self); self.diag.set_agent(self.controller.my_name)
            from app.core.events import HiveEvent
            self.controller.bus.subscribe(HiveEvent.LOG_MESSAGE, self._on_core_log)
            from app.ui.event_adapter import UiEventAdapter
            self._event_adapter = UiEventAdapter(self, self.controller.bus)
        
        self.show_screen("discovery")
        self._entrance_anim.start()

    def _on_core_log(self, event, data):
        self.log_message(str(data))

    def log_message(self, msg):
        self.bus.log_message.emit(msg)

    def _generate_icon(self):
        pix = QPixmap(128, 128)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        cx, cy, size = 64, 64, 55
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = cx + size * math.cos(angle); y = cy + size * math.sin(angle)
            if i == 0: path.moveTo(x, y)
            else: path.lineTo(x, y)
        path.closeSubpath()
        painter.fillPath(path, QColor(P.GOLD))
        painter.end()
        return QIcon(pix)

    def update_status(self, text):
        self.log_message(f"STATUS: {text}")
        if not hasattr(self, 'status_bar_val'): return
        
        current_status = self.status_bar_val.text()
        if current_status in ("CONNECTED", "HOST", "CLIENT") and text in ("READY", "AGENT READY", "IDLE"):
            return
            
        self.status_bar_val.setText(text.upper())
        if text in ("CONNECTED", "GROUP_CREATED", "HOST", "CLIENT"):
            self.show_screen("session")

    def set_network_state(self, state):
        self.diag.set_network_state(state)
        self.screens["session"].update_network_state(state)
        self.bus.network_state_changed.emit(state)

        mapping = {
            "HOST": P.GOLD,
            "CLIENT": P.AMBER,
            "OFFLINE": P.TEXT_DIM,
            "ASSOCIATING": P.HONEY,
            "SCANNING": P.SCAN,
        }
        self._vitality_color = mapping.get(state, P.TEXT_DIM)
        if hasattr(self, "sidebar_edge"):
            self.sidebar_edge.setStyleSheet(f"background-color: {self._vitality_color};")
        self.update_status(state)

    def set_swarm_role(self, role):
        self.diag.set_swarm_role(role)
        self.screens["session"].update_swarm_role(role)
        self.bus.swarm_role_changed.emit(role)

    def set_vitality(self, score):
        self.diag.set_vitality(score)

    def telemetry_pulse(self):
        self.diag.telemetry_pulse()

    def set_agent(self, name):
        self.diag.set_agent(name)

    def _build_ui(self):
        self.root_widget = HiveRootWidget()
        self.setCentralWidget(self.root_widget)
        
        outer_layout = QVBoxLayout(self.root_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        main_hbox = QHBoxLayout()
        main_hbox.setContentsMargins(0, 0, 0, 0)
        main_hbox.setSpacing(0)
        outer_layout.addLayout(main_hbox, 1)

        self.sidebar = QFrame(); self.sidebar.setObjectName("Sidebar"); self.sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(self.sidebar); sidebar_layout.setContentsMargins(0, 0, 0, 0); sidebar_layout.setSpacing(0)
        
        self.logo = BreathingLogo()
        sidebar_layout.addWidget(self.logo)

        self.nav_group = []
        nav_defs = [("DISCOVERY", "discovery"), ("SESSION", "session"), ("TRANSFERS", "transfer"), ("CONSOLE", "console"), ("SETTINGS", "settings")]
        for text, name in nav_defs:
            btn = NavButton(text, name); btn.clicked.connect(lambda checked=False, n=name: self.show_screen(n))
            sidebar_layout.addWidget(btn); self.nav_group.append(btn)
        sidebar_layout.addStretch()
        self.diag = DiagnosticPanel(); sidebar_layout.addWidget(self.diag); main_hbox.addWidget(self.sidebar)

        self.sidebar_edge = QFrame(self.root_widget)
        self.sidebar_edge.setObjectName("SidebarEdge")
        self.sidebar_edge.setFixedWidth(2)
        self.sidebar_edge.raise_()
        self.sidebar_edge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.sidebar_edge.setGeometry(0, 0, 0, 0)
        self.sidebar.installEventFilter(self)
        QTimer.singleShot(0, self._layout_sidebar_edge)

        self.stack = QStackedWidget(); main_hbox.addWidget(self.stack, 1)
        from app.ui.discovery import DiscoveryScreen
        from app.ui.session import SessionScreen
        from app.ui.transfer import TransferScreen
        from app.ui.settings import SettingsScreen
        self.screens = {
            "discovery": DiscoveryScreen(self), 
            "session": SessionScreen(self), 
            "transfer": TransferScreen(self),
            "console": ConsoleScreen(self),
            "settings": SettingsScreen(self)
        }
        for screen in self.screens.values(): self.stack.addWidget(screen)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("StatusBar")
        self.status_bar.setFixedHeight(22)
        sb_layout = QHBoxLayout(self.status_bar)
        sb_layout.setContentsMargins(15, 0, 15, 0)
        
        sb_lbl = QLabel("SYSTEM STATE:")
        sb_lbl.setObjectName("StatusLabel")
        sb_layout.addWidget(sb_lbl)
        
        self.status_bar_val = QLabel("IDLE")
        self.status_bar_val.setObjectName("StatusValue")
        sb_layout.addWidget(self.status_bar_val)
        sb_layout.addStretch()
        
        outer_layout.addWidget(self.status_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event); self.root_widget.resize(self.size())
        self._layout_sidebar_edge()

    def eventFilter(self, obj, event):
        if obj is self.sidebar and event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
            self._layout_sidebar_edge()
        return super().eventFilter(obj, event)

    def _layout_sidebar_edge(self):
        if not hasattr(self, "sidebar_edge"):
            return
        sidebar_geom = self.sidebar.geometry()
        self.sidebar_edge.setGeometry(
            sidebar_geom.x() + sidebar_geom.width() - self.sidebar_edge.width(),
            sidebar_geom.y(),
            self.sidebar_edge.width(),
            sidebar_geom.height(),
        )
        self.sidebar_edge.raise_()

    def set_discovery_groups(self, groups):
        self.screens["discovery"].set_groups(groups)

    def set_session_peers(self, peers):
        self.bus.peers_updated.emit(peers)
        self.screens["session"].set_peers(peers)
        self.screens["transfer"].set_targets(peers)

    def set_transfer_targets(self, peers):
        self.screens["transfer"].set_targets(peers)

    def set_data_plane_state(self, active):
        pass

    def report_transfer_error(self, m):
        self.screens["transfer"].show_error(m)
        self.bus.transfer_error.emit(m)

    def send_complete(self): self.bus.send_complete.emit()
    def receive_complete(self): self.bus.receive_complete.emit()
    def mark_received(self, size): self.bus.incoming_transfer.emit(size)

    def update_transfer_progress(self, current, total):
        self.bus.transfer_progress.emit(current, total)

    def _setup_signals(self):
        if self.controller and self.controller.bus:
            bus = self.controller.bus
            bus.subscribe(HiveEvent.PEER_DISCOVERED, self._on_core_peers)
            bus.subscribe(HiveEvent.PEER_LEFT, self._on_core_peers)
            bus.subscribe(HiveEvent.HOST_ELECTED, self._on_core_host_elected)
        
        self.bus.incoming_transfer.connect(lambda size: self.show_screen("transfer"))

    def _on_core_peers(self, event, data):
        if self.controller:
            if not self.controller.network:
                self.set_session_peers([])
                return
            host_uuid = self.controller.network.host_uuid
            peers = []
            for uid, info in self.controller.network.peers.items():
                peers.append({
                    "uuid": uid,
                    "name": info.get("name", uid[:8]),
                    "ip": info.get("ip", ""),
                    "score": info.get("score", 0),
                    "role": "HOST" if uid == host_uuid else "CONNECTED",
                })
            self.set_session_peers(peers)
            self.set_transfer_targets(peers)

    def _on_core_host_elected(self, event, data): 
        role = "HOST" if self.controller and data == self.controller.my_uuid else "CLIENT"
        self.set_swarm_role(role)
        self._on_core_peers(event, data)
    
    def _setup_shortcuts(self):
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("F5"), self, self._accel_scan)
        QShortcut(QKeySequence("Escape"), self, self._accel_back)

    def _accel_scan(self):
        self.show_screen("discovery")
        self.screens["discovery"]._do_scan()

    def _accel_back(self):
        current = self.stack.currentWidget()
        if current == self.screens["session"]:
            self.screens["session"]._do_leave()
        else:
            self.show_screen("discovery")

    def show_screen(self, name):
        name = name.lower()
        if name in self.screens:
            for btn in self.nav_group: 
                btn.setChecked(btn.screen_name == name)

            target = self.screens[name]
            if self.stack.currentWidget() == target:
                return
            
            self.stack.setCurrentWidget(target)
            
            from PySide6.QtCore import QParallelAnimationGroup
            group = QParallelAnimationGroup(self)
            
            eff = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(eff)
            fade = QPropertyAnimation(eff, b"opacity")
            fade.setDuration(350); fade.setStartValue(0); fade.setEndValue(1)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            group.addAnimation(fade)
            
            pos = QPropertyAnimation(target, b"pos")
            pos.setDuration(450)
            
            from PySide6.QtCore import QPoint
            current_pos = target.pos()
            start_pos = current_pos + QPoint(0, 30)
            
            pos.setStartValue(start_pos)
            pos.setEndValue(current_pos)
            pos.setEasingCurve(QEasingCurve.OutCubic)
            group.addAnimation(pos)
            
            self._anims.append(group)
            group.finished.connect(lambda: self._anims.remove(group) if group in self._anims else None)
            group.start()

    def confirm_resume(self, f, e, t):
        dialog = QMessageBox(self); dialog.setWindowTitle("HIVE — Resume Transfer")
        dialog.setText(f"Partial file found — resume download?\n\n  File   : {f}\n  Stored : {e:,} bytes\n  Total  : {t:,} bytes")
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return dialog.exec() == QMessageBox.Yes

    def after(self, ms, func, *args):
        delay = 0 if ms <= 0 else ms
        QTimer.singleShot(delay, self, lambda: func(*args))
    def closeEvent(self, event):
        if self.controller:
            self.controller.shutdown()
        event.accept()
