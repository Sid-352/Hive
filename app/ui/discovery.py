import math
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QLabel, QPushButton, QScrollArea, QCheckBox, 
                             QGraphicsDropShadowEffect, QAbstractButton, QGraphicsOpacityEffect,
                             QLineEdit)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QRectF, QSequentialAnimationGroup
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QLinearGradient
from app.ui.theme import P


class HiveCheckBox(QAbstractButton):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setFixedWidth(130)
        self.setFixedHeight(24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        checked = self.isChecked()
        color = QColor(P.GOLD if checked else P.TEXT_DIM)
        
        rect = QRectF(2, 6, 12, 12)
        painter.setPen(QPen(color, 1.5))
        if checked:
            painter.setBrush(color)
        else:
            painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        painter.setPen(QColor(P.HONEY if self.underMouse() or checked else P.TEXT_DIM))
        painter.drawText(22, 16, self.text())


class ScanHexWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 120)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(222)

    def _step(self):
        self._phase = (self._phase + 1) % 6
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        
        spacing = 30
        for i in range(3):
            active = (self._phase % 3 == i)
            size = 12 if active else 8
            opacity = 1.0 if active else 0.3
            
            x = cx + (i - 1) * spacing
            path = self._hex_path(x, cy, size)
            
            color = QColor(P.GOLD)
            painter.setOpacity(opacity)
            painter.setPen(QPen(color, 1.5))
            if active:
                painter.setBrush(color)
            else:
                painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

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


class IdleHexWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._ripples = []
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(16)
        
        self._base_size = 25

    def _step(self):
        self._phase += 1
        
        if self._phase % 120 == 0:
            self._ripples.append({'radius': self._base_size, 'opacity': 0.8})
            
        for r in self._ripples[:]:
            r['radius'] += 0.5
            r['opacity'] -= 0.015
            if r['opacity'] <= 0:
                self._ripples.remove(r)
        
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        
        path = self._hex_path(cx, cy, self._base_size)
        painter.setPen(QPen(QColor(P.GOLD), 2))
        painter.setBrush(QColor(P.FAINT_GOLD))
        painter.setOpacity(0.4)
        painter.drawPath(path)

        painter.setBrush(Qt.NoBrush)
        for r in self._ripples:
            painter.setOpacity(r['opacity'])
            r_path = self._hex_path(cx, cy, r['radius'])
            painter.drawPath(r_path)

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


class SwarmCard(QFrame):
    def __init__(self, group, on_join, parent=None):
        super().__init__(parent)
        self.setObjectName("SwarmCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.group = group
        self.on_join = on_join
        self.setFixedHeight(72)
        self.setAttribute(Qt.WA_Hover, True)
        
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(10)
        self.shadow.setOffset(0)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(self.shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(60, 10, 15, 10)

        info = QVBoxLayout()
        name_lbl = QLabel(group.get("name", "UNKNOWN SWARM").upper())
        name_lbl.setObjectName("SwarmName")
        
        details_lbl = QLabel(f"{group.get('ssid', '')}  |  {group.get('uuid', '')[:16]}")
        details_lbl.setObjectName("SwarmDetails")
        
        info.addWidget(name_lbl)
        info.addWidget(details_lbl)
        layout.addLayout(info, 1)

        btn = QPushButton("JOIN")
        btn.setObjectName("GoldButton")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self.on_join(self.group["uuid"]))
        layout.addWidget(btn)

    def enterEvent(self, event):
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(P.GOLD))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.shadow.setBlurRadius(10)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        grad = QLinearGradient(0, 0, 48, 0)
        grad.setColorAt(0, QColor(P.FAINT_GOLD))
        grad.setColorAt(1, QColor(P.VOID))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, 0, 48, self.height())

        size = 14
        cx, cy = 24, 36
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = cx + size * math.cos(angle)
            y = cy + size * math.sin(angle)
            if i == 0: path.moveTo(x, y)
            else: path.lineTo(x, y)
        path.closeSubpath()

        painter.fillPath(path, QColor(P.GOLD))


class DiscoveryScreen(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("DiscoveryScreen")
        self.app = app
        self.bus = app.bus
        self.cards = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        hdr = QHBoxLayout()
        title = QLabel("DISCOVERY")
        title.setObjectName("Header")
        hdr.addWidget(title)
        
        hdr.addStretch()
        
        d_lbl = QLabel("SEC:")
        d_lbl.setObjectName("Label")
        hdr.addWidget(d_lbl)
        
        self.duration_edit = QLineEdit("10")
        self.duration_edit.setFixedWidth(30)
        self.duration_edit.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self.duration_edit)
        
        self.scan_btn = QPushButton("SCAN SWARMS")
        self.scan_btn.setObjectName("GoldButton")
        self.scan_btn.clicked.connect(self._do_scan)
        hdr.addWidget(self.scan_btn)
        layout.addLayout(hdr)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setObjectName("TransparentScroll")
        
        self.list_container = QWidget()
        self.list_container.setObjectName("TransparentContainer")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        
        self._empty_state = QWidget()
        self._empty_state.setObjectName("TransparentContainer")
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(5)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scan_anim = ScanHexWidget()
        empty_layout.addWidget(self.scan_anim, 0, Qt.AlignCenter)
        self.scan_anim.hide()

        self.idle_icon = IdleHexWidget()
        empty_layout.addWidget(self.idle_icon, 0, Qt.AlignCenter)

        self.empty_lbl = QLabel("NO SWARMS DETECTED")
        self.empty_lbl.setObjectName("Label")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_lbl)
        
        self.list_layout.addStretch(1)
        self.list_layout.addWidget(self._empty_state)
        self.list_layout.addStretch(1)
        
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll)

        host_panel = QFrame()
        host_panel.setObjectName("HostPanel")
        host_layout = QHBoxLayout(host_panel)
        host_layout.setContentsMargins(15, 12, 15, 12)

        h_title = QLabel("HOST SWARM")
        h_title.setObjectName("HeaderSm")
        host_layout.addWidget(h_title)
        host_layout.addStretch()

        self.ruthless_check = HiveCheckBox("FORCE 2.4 GHz")
        self.ruthless_check.setObjectName("PlainToggle")
        host_layout.addWidget(self.ruthless_check)

        host_btn = QPushButton("HOST")
        host_btn.setObjectName("GoldButton")
        host_btn.clicked.connect(self._do_host)
        host_layout.addWidget(host_btn)
        
        layout.addWidget(host_panel)

        self.bus.groups_discovered.connect(self.set_groups)

    def _do_scan(self):
        if self.app.controller:
            try:
                duration = int(self.duration_edit.text())
            except ValueError:
                duration = 10
            self.app.controller.scan_groups(duration=duration)
            self.scan_btn.setText("SCANNING...")
            self.scan_btn.setEnabled(False)
            
            self.idle_icon.hide()
            self.scan_anim.show()
            self.empty_lbl.setText("SCANNING FOR SWARMS...")
            
            QTimer.singleShot(duration * 1000, self._scan_timeout)

    def _scan_timeout(self):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("SCAN SWARMS")
        if not self.cards:
            self.scan_anim.hide()
            self.idle_icon.show()
            self.empty_lbl.setText("NO SWARMS DETECTED")

    def _do_host(self):
        if self.app.controller:
            self.app.controller.host_group(ruthless=self.ruthless_check.isChecked())

    def _do_join(self, uuid):
        if self.app.controller:
            self.app.controller.join_group(uuid)

    def set_groups(self, groups):
        self.scan_anim.hide()
        for c in self.cards:
            c.setParent(None)
        self.cards.clear()
        
        if not groups:
            self._empty_state.show()
            self.idle_icon.show()
            self.empty_lbl.setText("SCAN COMPLETE — 0 FOUND")
            return

        self._empty_state.hide()
        for g in groups:
            card = SwarmCard(g, self._do_join)
            self.list_layout.insertWidget(0, card)
            self.cards.append(card)
