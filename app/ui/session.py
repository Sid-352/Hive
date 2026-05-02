from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QLabel, QPushButton, QScrollArea, QGraphicsOpacityEffect)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property
from app.ui.theme import P

class PeerRow(QFrame):
    def __init__(self, peer, is_leader=False, parent=None):
        super().__init__(parent)
        from app.ui.app import HexGlyph
        self.setObjectName("PeerCardLeader" if is_leader else "Card")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 15, 8)

        self.glyph = HexGlyph(peer.get("uuid", ""), size=40)
        layout.addWidget(self.glyph)

        info = QVBoxLayout()
        name_str = peer.get("name", "UNKNOWN").upper()
        if is_leader: name_str += " ◈ LEADER"
        
        name_lbl = QLabel(name_str)
        name_lbl.setObjectName("PeerNameLeader" if is_leader else "PeerName")
        
        details_lbl = QLabel(f"{peer.get('ip', '?.?.?.?')}  |  {peer.get('uuid', '')[:16]}")
        details_lbl.setObjectName("PeerDetails")
        
        info.addWidget(name_lbl)
        info.addWidget(details_lbl)
        layout.addLayout(info, 1)

        score = peer.get("score", 0)
        self._score_color = P.ALIVE if score > 70 else P.HONEY if score > 30 else P.SEVERED
        
        vit_box = QVBoxLayout()
        self.vit_val = QLabel(str(score))
        self.vit_val.setObjectName("PeerVitality")
        self.vit_val.setAlignment(Qt.AlignCenter)
        self.vit_val.setStyleSheet(f"color: {self._score_color};")
        
        self.vit_opacity = QGraphicsOpacityEffect(self.vit_val)
        self.vit_val.setGraphicsEffect(self.vit_opacity)
        self.vit_anim = QPropertyAnimation(self.vit_opacity, b"opacity", self)
        self.vit_anim.setDuration(2000)
        self.vit_anim.setStartValue(0.4)
        self.vit_anim.setEndValue(1.0)
        self.vit_anim.setEasingCurve(QEasingCurve.InOutSine)
        self.vit_anim.setLoopCount(-1)
        self.vit_anim.start()

        vit_lbl = QLabel("VIT")
        vit_lbl.setObjectName("PeerVitalityLabel")
        vit_lbl.setAlignment(Qt.AlignCenter)
        
        vit_box.addWidget(self.vit_val)
        vit_box.addWidget(vit_lbl)
        layout.addLayout(vit_box)

    def set_state(self, state):
        if state == "amber":
            self.vit_anim.setDuration(500)
            self.vit_val.setStyleSheet(f"color: {P.SEVERED};")
        else:
            self.vit_anim.setDuration(2000)
            self.vit_val.setStyleSheet(f"color: {self._score_color};")

    def update_score(self, score):
        self._score_color = P.ALIVE if score > 70 else P.HONEY if score > 30 else P.SEVERED
        self.vit_val.setText(str(score))
        self.vit_val.setStyleSheet(f"color: {self._score_color};")

class SessionScreen(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setObjectName("SessionScreen")
        self.app = app
        self.bus = app.bus
        self._peer_rows = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        hdr = QLabel("SESSION")
        hdr.setObjectName("SessionHeader")
        layout.addWidget(hdr)

        matrix = QWidget()
        matrix.setObjectName("TransparentContainer")
        m_layout = QHBoxLayout(matrix)
        m_layout.setContentsMargins(0, 5, 0, 15)

        self.phys_val = self._add_stat(m_layout, "PHYSICAL LINK", "OFFLINE")
        self.phys_val.setObjectName("PhysicalLinkValue")
        
        line = QFrame()
        line.setFixedWidth(1)
        line.setFixedHeight(24)
        line.setObjectName("SectionDivider")
        m_layout.addWidget(line, 0, Qt.AlignCenter)
        
        self.logi_val = self._add_stat(m_layout, "LOGICAL LINK", "—")
        self.logi_val.setObjectName("LogicalLinkValue")
        
        layout.addWidget(matrix)

        list_hdr = QHBoxLayout()
        list_hdr.setContentsMargins(5, 0, 5, 0)
        l_lbl = QLabel("ACTIVE WORKERS")
        l_lbl.setObjectName("SectionLabel")
        list_hdr.addWidget(l_lbl)
        
        self.count_lbl = QLabel("0 nodes")
        self.count_lbl.setObjectName("SectionCount")
        list_hdr.addWidget(self.count_lbl)
        list_hdr.addStretch()
        layout.addLayout(list_hdr)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setObjectName("TransparentScroll")
        
        self.list_container = QWidget()
        self.list_container.setObjectName("TransparentContainer")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll)

        leave_btn = QPushButton("LEAVE SWARM")
        leave_btn.setObjectName("LeaveButton")
        leave_btn.setCursor(Qt.PointingHandCursor)
        leave_btn.clicked.connect(self._do_leave)
        layout.addWidget(leave_btn)

        self._empty_lbl = QLabel("NO PEERS IN SWARM")
        self._empty_lbl.setObjectName("EmptyState")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self.list_layout.insertWidget(0, self._empty_lbl)

        self.bus.peers_updated.connect(self.set_peers)
        self.bus.peer_state_changed.connect(self.set_peer_state)

    def set_peer_state(self, data):
        uuid = data.get("uuid")
        state = data.get("state")
        if uuid in self._peer_rows:
            self._peer_rows[uuid].set_state(state)

    def _add_stat(self, layout, title, val):
        from app.ui.app import FlashLabel
        box = QVBoxLayout()
        box.setSpacing(2)
        t_lbl = QLabel(title)
        t_lbl.setObjectName("StatLabel")
        v_lbl = FlashLabel(val)
        v_lbl.setObjectName("StatValue")
        box.addWidget(t_lbl)
        box.addWidget(v_lbl)
        layout.addLayout(box, 1)
        return v_lbl

    def _do_leave(self):
        if self.app.controller:
            self.app.controller.leave_session()

    def set_peers(self, peers):
        incoming_uuids = {p.get("uuid") for p in peers if p.get("uuid")}
        
        for uuid in list(self._peer_rows.keys()):
            if uuid not in incoming_uuids:
                row = self._peer_rows.pop(uuid)
                row.setParent(None)
        
        for p in peers:
            uuid = p.get("uuid")
            if not uuid: continue
            
            if uuid in self._peer_rows:
                self._peer_rows[uuid].update_score(p.get("score", 0))
            else:
                role = p.get("role", "WORKER")
                is_lead = role in ("HOST", "LEADER")
                row = PeerRow(p, is_leader=is_lead)
                self.list_layout.insertWidget(0, row)
                self._peer_rows[uuid] = row
        
        self.count_lbl.setText(f"{len(peers)} node{'s' if len(peers) != 1 else ''}")
        self._empty_lbl.setVisible(len(peers) == 0)

    def update_network_state(self, state):
        mapping = {"HOST": "GROUP OWNER", "CLIENT": "PEER NODE", "OFFLINE": "OFFLINE"}
        text = mapping.get(state, state)
        color = {"GROUP OWNER": P.GOLD, "PEER NODE": P.AMBER, "OFFLINE": P.TEXT_DIM}.get(text, P.TEXT_SEC)
        self.phys_val.setText(text)
        self.phys_val.setStyleSheet(f"color: {color};")

    def update_swarm_role(self, role):
        mapping = {"HOST": "LEADER", "CLIENT": "WORKER", "NONE": "—"}
        text = mapping.get(role, role)
        color = P.LEADER if text == "LEADER" else P.WORKER if text == "WORKER" else P.TEXT_DIM
        self.logi_val.setText(text)
        self.logi_val.setStyleSheet(f"color: {color};")
