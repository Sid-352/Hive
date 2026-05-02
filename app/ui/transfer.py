import time
import os
import subprocess
import sys
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QLabel, QPushButton, QLineEdit, QComboBox, 
                             QProgressBar, QFileDialog, QGraphicsOpacityEffect)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from app.ui.theme import P
from app.ui.app import OdometerLabel, VelocitySparkline

class TransferScreen(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("TransferScreen")
        self.app = app
        self.bus = app.bus
        self._start_time = 0
        self._last_update = 0
        self._last_bytes = 0
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(25)

        hdr = QLabel("TRANSFERS")
        hdr.setObjectName("Header")
        layout.addWidget(hdr)

        f_box = QWidget()
        f_box.setObjectName("TransparentContainer")
        f_layout = QVBoxLayout(f_box)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(8)
        
        f_lbl = QLabel("FILE BROADCAST")
        f_lbl.setObjectName("Label")
        f_layout.addWidget(f_lbl)
        
        f_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select a file...")
        f_row.addWidget(self.path_edit)
        
        browse_btn = QPushButton("BROWSE")
        browse_btn.setFixedWidth(80)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setObjectName("BrowseButton")
        browse_btn.clicked.connect(self._browse)
        f_row.addWidget(browse_btn)
        f_layout.addLayout(f_row)
        layout.addWidget(f_box)

        t_box = QWidget()
        t_box.setObjectName("TransparentContainer")
        t_layout = QVBoxLayout(t_box)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(8)
        
        t_lbl = QLabel("TARGET DRONE")
        t_lbl.setObjectName("Label")
        t_layout.addWidget(t_lbl)
        
        t_row = QHBoxLayout()
        self.target_combo = QComboBox()
        self.target_combo.addItem("NO DRONES AVAILABLE")
        self.target_combo.currentIndexChanged.connect(self._update_send_btn)
        t_row.addWidget(self.target_combo, 1)
        
        self.send_btn = QPushButton("SEND")
        self.send_btn.setObjectName("GoldButton")
        self.send_btn.setFixedWidth(100)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._do_send)
        self.send_btn.setEnabled(False)
        t_row.addWidget(self.send_btn)
        t_layout.addLayout(t_row)
        layout.addWidget(t_box)

        self.p_panel = QFrame()
        self.p_panel.setObjectName("ProgressPanel")
        p_layout = QVBoxLayout(self.p_panel)
        self.p_panel.hide()
        
        self.p_opacity = QGraphicsOpacityEffect(self.p_panel)
        self.p_panel.setGraphicsEffect(self.p_opacity)
        self.p_anim = QPropertyAnimation(self.p_opacity, b"opacity")
        self.p_anim.setDuration(400)
        self.p_anim.setStartValue(0); self.p_anim.setEndValue(1)
        self.p_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.p_title = QLabel("TRANSFERRING...")
        self.p_title.setObjectName("TransferTitle")
        self.p_title.setProperty("state", "idle")
        p_layout.addWidget(self.p_title)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        p_layout.addWidget(self.progress)

        s_row = QHBoxLayout()
        self.status_lbl = QLabel("Awaiting start...")
        self.status_lbl.setObjectName("TransferStatus")
        s_row.addWidget(self.status_lbl)
        
        self.speed_lbl = QLabel("")
        self.speed_lbl.setObjectName("TransferSpeed")
        s_row.addWidget(self.speed_lbl, 1)
        
        self.sparkline = VelocitySparkline()
        self.sparkline.setFixedHeight(30)
        s_row.addWidget(self.sparkline, 2)
        p_layout.addLayout(s_row)

        self.p_actions = QWidget()
        self.p_actions.hide()
        act_layout = QHBoxLayout(self.p_actions)
        act_layout.setContentsMargins(0, 10, 0, 0)
        
        self.open_btn = QPushButton("OPEN DOWNLOAD FOLDER")
        self.open_btn.setObjectName("GoldButton")
        self.open_btn.clicked.connect(self._open_downloads)
        act_layout.addWidget(self.open_btn)
        
        p_layout.addWidget(self.p_actions)
        
        layout.addWidget(self.p_panel)

        self.idle_state = QLabel("AWAITING PAYLOAD INSTRUCTIONS")
        self.idle_state.setObjectName("Label")
        self.idle_state.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.idle_state, 1)

        self.bus.transfer_progress.connect(self.update_progress)
        self.bus.transfer_error.connect(self.show_error)
        self.bus.send_complete.connect(self.on_send_complete)
        self.bus.receive_complete.connect(self.on_receive_complete)
        self.bus.incoming_transfer.connect(self.on_mark_received)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.path_edit.setText(files[0])
            self._update_send_btn()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select File to Send")
        if path:
            self.path_edit.setText(path)
            self._update_send_btn()

    def _update_send_btn(self, *args):
        has_path = bool(self.path_edit.text())
        has_target = self.target_combo.currentText() != "NO DRONES AVAILABLE"
        self.send_btn.setEnabled(has_path and has_target)

    def _do_send(self):
        path = self.path_edit.text()
        target = self.target_combo.currentText()
        if not path or target == "NO DRONES AVAILABLE": return
        self._show_progress("INITIATING...")
        if self.app.controller:
            self.app.controller.send_file(path, target)

    def _show_progress(self, text):
        self.idle_state.hide()
        self.p_actions.hide()
        self.p_title.setText(text)
        self.p_title.setProperty("state", "idle")
        self.p_title.style().unpolish(self.p_title)
        self.p_title.style().polish(self.p_title)
        self.status_lbl.setProperty("state", "idle")
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)
        if self.p_panel.isHidden():
            self.p_panel.show()
            self.p_anim.start()
        self.progress.setValue(0)
        self.speed_lbl.setText("")
        self.sparkline.clear()
        self._start_time = 0

    def _open_downloads(self):
        if not self.app.controller: return
        path = self.app.controller.download_dir
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])

    def set_targets(self, peers):
        self.target_combo.clear()
        names = [p.get("name") for p in peers if p.get("name")]
        if not names:
            self.target_combo.addItem("NO DRONES AVAILABLE")
        else:
            self.target_combo.addItems(names)
            if len(names) == 1:
                self.target_combo.setCurrentIndex(0)
        self._update_send_btn()

    def update_progress(self, current, total):
        if self.p_panel.isHidden():
            self._show_progress("TRANSFERRING...")
        now = time.time()
        if self._start_time == 0:
            self._start_time = now; self._last_update = now; self._last_bytes = current
        percent = int((current / max(1, total)) * 100)
        self.progress.setValue(percent)
        self.status_lbl.setText(f"{percent}% COMPLETE")
        dt = now - self._last_update
        if dt >= 0.5 or current == total:
            db = current - self._last_bytes; speed = db / dt if dt > 0 else 0
            self._last_update = now; self._last_bytes = current
            s_str = f"{speed/1024/1024:.1f} MB/s" if speed > 1024*1024 else f"{speed/1024:.1f} KB/s"
            eta = (total-current)/speed if speed > 0 else 0
            self.speed_lbl.setText(f"{s_str}  |  ETA {int(eta//60):02d}:{int(eta%60):02d}")
            self.sparkline.add_value(speed)

    def show_error(self, m):
        self.p_title.setText("FAILED")
        self.p_title.setProperty("state", "error")
        self.p_title.style().unpolish(self.p_title)
        self.p_title.style().polish(self.p_title)
        self.status_lbl.setText(m)
        self.status_lbl.setProperty("state", "error")
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def on_send_complete(self):
        self.p_title.setText("SENT")
        self.p_title.setProperty("state", "ok")
        self.p_title.style().unpolish(self.p_title)
        self.p_title.style().polish(self.p_title)
        self.status_lbl.setText("Data plane closed")
        self.status_lbl.setProperty("state", "ok")
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)
        QTimer.singleShot(5000, self._hide_progress)

    def on_receive_complete(self):
        self.p_title.setText("RECEIVED")
        self.p_title.setProperty("state", "ok")
        self.p_title.style().unpolish(self.p_title)
        self.p_title.style().polish(self.p_title)
        self.status_lbl.setText("File saved successfully")
        self.status_lbl.setProperty("state", "ok")
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)
        self.p_actions.show()
        QTimer.singleShot(10000, self._hide_progress)

    def _hide_progress(self):
        if not self.p_actions.isVisible():
            self.p_panel.hide()
            self.idle_state.show()

    def on_mark_received(self, size):
        self._show_progress("INCOMING")
        self.status_lbl.setText(f"Receiving {size} bytes")
