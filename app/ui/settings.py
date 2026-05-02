import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QLabel, QPushButton, QLineEdit, QFileDialog)
from PySide6.QtCore import Qt
from app.ui.theme import P

class SettingsScreen(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsScreen")
        self.app = app
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(25)

        hdr = QLabel("SYSTEM SETTINGS")
        hdr.setObjectName("Header")
        layout.addWidget(hdr)

        name_box = QWidget()
        name_layout = QVBoxLayout(name_box)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(8)
        
        name_lbl = QLabel("NODE NAME")
        name_lbl.setObjectName("Label")
        name_layout.addWidget(name_lbl)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter node name...")
        name_layout.addWidget(self.name_edit)
        layout.addWidget(name_box)

        pin_box = QWidget()
        pin_layout = QVBoxLayout(pin_box)
        pin_layout.setContentsMargins(0, 0, 0, 0)
        pin_layout.setSpacing(8)
        
        pin_lbl = QLabel("ROOM PASSPHRASE")
        pin_lbl.setObjectName("Label")
        pin_layout.addWidget(pin_lbl)

        self.pin_edit = QLineEdit()
        self.pin_edit.setPlaceholderText("Enter room passphrase...")
        pin_layout.addWidget(self.pin_edit)
        layout.addWidget(pin_box)

        dir_box = QWidget()
        dir_layout = QVBoxLayout(dir_box)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(8)
        
        dir_lbl = QLabel("DOWNLOAD DIRECTORY")
        dir_lbl.setObjectName("Label")
        dir_layout.addWidget(dir_lbl)
        
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        dir_row.addWidget(self.dir_edit)
        
        browse_btn = QPushButton("BROWSE")
        browse_btn.setFixedWidth(80)
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setObjectName("BrowseButton")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        dir_layout.addLayout(dir_row)
        layout.addWidget(dir_box)

        layout.addStretch()

        self.save_btn = QPushButton("SAVE SETTINGS")
        self.save_btn.setObjectName("GoldButton")
        self.save_btn.setFixedHeight(40)
        self.save_btn.clicked.connect(self._save_settings)
        layout.addWidget(self.save_btn)

        self._load_current()

    def _load_current(self):
        if self.app.controller:
            c = self.app.controller
            self.name_edit.setText(c.my_name)
            self.pin_edit.setText(c._room_pin)
            self.dir_edit.setText(c.download_dir)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Download Directory", self.dir_edit.text())
        if path:
            self.dir_edit.setText(path)

    def _save_settings(self):
        if self.app.controller:
            name = self.name_edit.text()
            pin = self.pin_edit.text()
            ddir = self.dir_edit.text()
            
            self.app.controller.update_settings(name, pin, ddir)
            
            self.save_btn.setText("SETTINGS SAVED")
            import PySide6.QtCore as QtCore
            QtCore.QTimer.singleShot(2000, lambda: self.save_btn.setText("SAVE SETTINGS"))
