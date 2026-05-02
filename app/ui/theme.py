class P:
    VOID        = "#080808"
    ABYSS       = "#0A0A0A"
    DEEP        = "#111111"
    CELL        = "#161616"
    COMB        = "#1C1C1C"
    PANEL       = "#1F1F1F"

    GOLD        = "#FFC300"
    HONEY       = "#E59400"
    AMBER       = "#D4AF37"
    DIM_GOLD    = "#7A5C00"
    FAINT_GOLD  = "#2A1F00"
    SCAN        = "#B8892A"

    TEXT_PRI    = "#F0D080"
    TEXT_SEC    = "#8A7040"
    TEXT_MID    = "#6A552A" 
    TEXT_DIM    = "#4A3A18"
    TEXT_WHITE  = "#E8E0C8"

    ALIVE       = "#5CFF8A"
    SEVERED     = "#FF4444"
    LEADER      = "#FFC300"
    WORKER      = "#8A7040"

    BORDER      = "#2A2200"
    BORDER_LIT  = "#5A4500"
    BORDER_GOLD = "#FFC300"

class F:
    DATA    = "Consolas"
    UI      = "Segoe UI"

def get_stylesheet():
    return f"""
    QMainWindow {{
        background-color: {P.ABYSS};
        color: {P.TEXT_WHITE};
        font-family: "{F.UI}";
        font-size: 13px;
    }}
    QWidget {{
        color: {P.TEXT_WHITE};
        font-family: "{F.UI}";
        font-size: 13px;
    }}
    QFrame {{
        background: transparent;
    }}

    QStackedWidget,
    QWidget#TransparentContainer,
    DiscoveryScreen,
    SessionScreen,
    TransferScreen,
    SettingsScreen,
    ConsoleScreen {{
        background: transparent;
    }}

    QLabel#Label {{
        font-family: "{F.UI}";
        font-weight: 600;
        color: {P.TEXT_MID};
        letter-spacing: 0.8px;
        text-transform: uppercase;
        font-size: 10px;
        border: none;
        text-decoration: none;
        background: transparent;
    }}
    QLabel#Data {{
        font-family: "{F.DATA}";
        font-weight: normal;
        color: {P.TEXT_PRI};
        border: none;
        text-decoration: none;
        background: transparent;
    }}
    
    QLabel#Header {{
        font-family: "{F.UI}";
        font-size: 15px;
        font-weight: 900;
        color: {P.GOLD};
        letter-spacing: 1.2px;
        text-transform: uppercase;
    }}
    QLabel#Logo {{
        font-size: 22px;
        font-weight: 900;
        color: {P.GOLD};
        padding: 35px 0;
    }}
    QLabel#HeaderSm {{
        font-family: "{F.UI}";
        font-size: 13px;
        font-weight: 800;
        color: {P.GOLD};
        letter-spacing: 1.0px;
        text-transform: uppercase;
        border: none;
    }}

    QLabel#SessionHeader {{
        font-family: "{F.UI}";
        font-size: 18px;
        font-weight: 900;
        color: {P.GOLD};
        letter-spacing: 1.2px;
        text-transform: uppercase;
    }}

    QFrame#Sidebar {{
        background-color: {P.DEEP};
        border-right: 1px solid {P.VOID};
    }}
    QFrame#SidebarEdge {{
        background-color: {P.TEXT_DIM};
    }}
    QFrame#DiagnosticPanel {{
        background-color: {P.DEEP};
        border: none;
    }}
    QFrame#DiagnosticPanel QLabel {{
        background: transparent;
    }}
    QFrame#HostPanel {{
        background: {P.ABYSS};
        border: 1px solid {P.BORDER};
        border-radius: 2px;
    }}

    QPushButton#NavButton {{
        background-color: transparent;
        color: {P.TEXT_DIM};
        text-align: left;
        padding: 12px 20px;
        border: none;
        font-family: "{F.UI}";
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 1.2px;
        text-transform: uppercase;
    }}
    QPushButton#NavButton:hover {{
        background-color: {P.PANEL};
        color: {P.TEXT_SEC};
    }}
    QPushButton#NavButton:checked {{
        background-color: {P.FAINT_GOLD};
        color: {P.GOLD};
        border-left: 2px solid {P.GOLD};
    }}

    QFrame#Card {{
        background-color: {P.CELL};
        border: 1px solid {P.BORDER};
        border-radius: 1px;
    }}
    QFrame#PeerCardLeader {{
        background-color: {P.FAINT_GOLD};
        border: 1px solid {P.GOLD};
    }}
    QFrame#SwarmCard:hover {{
        background-color: {P.COMB};
        border: 1px solid {P.GOLD};
    }}
    QFrame#ProgressPanel {{
        background-color: {P.VOID};
        border: 1px solid {P.BORDER_LIT};
    }}

    QLineEdit {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {P.BORDER_LIT};
        padding: 8px 4px;
        font-family: "{F.DATA}";
        color: {P.TEXT_PRI};
    }}
    QLineEdit:focus {{
        border-bottom: 1px solid {P.GOLD};
    }}

    QComboBox {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {P.BORDER_LIT};
        padding: 4px;
        font-family: "{F.DATA}";
        color: {P.TEXT_PRI};
    }}

    QPushButton#BrowseButton {{
        color: {P.TEXT_SEC};
        font-size: 10px;
        border: 1px solid {P.BORDER};
        padding: 5px;
    }}

    QPushButton#GoldButton {{
        background-color: {P.ABYSS};
        color: {P.GOLD};
        border: 1px solid {P.GOLD};
        padding: 8px 20px;
        font-family: "{F.UI}";
        font-weight: 700;
        font-size: 10px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        border-radius: 1px;
    }}
    QPushButton#GoldButton:hover {{
        background-color: {P.DIM_GOLD};
        border-color: {P.GOLD};
        color: {P.TEXT_WHITE};
    }}
    QPushButton#GoldButton:pressed {{
        background-color: {P.HONEY};
        color: {P.VOID};
    }}
    QPushButton#LeaveButton {{
        color: {P.SEVERED};
        border: 1px solid {P.SEVERED};
        padding: 10px;
        font-weight: bold;
        background: {P.ABYSS};
    }}
    QPushButton#LeaveButton:hover {{
        background: {P.SEVERED};
        color: {P.VOID};
    }}

    QLabel#SwarmName {{
        font-weight: bold;
        color: {P.TEXT_PRI};
        font-size: 14px;
        background: transparent;
    }}
    QLabel#SwarmDetails {{
        color: {P.TEXT_DIM};
        font-size: 11px;
        background: transparent;
    }}

    QLabel#PeerName {{
        color: {P.TEXT_PRI};
        font-size: 13px;
        background: transparent;
    }}
    QLabel#PeerNameLeader {{
        color: {P.GOLD};
        font-size: 13px;
        background: transparent;
    }}
    QLabel#PeerDetails {{
        color: {P.TEXT_DIM};
        font-size: 11px;
        background: transparent;
    }}
    QLabel#PeerVitality {{
        font-size: 16px;
    }}
    QLabel#PeerVitalityLabel {{
        font-size: 9px;
        color: {P.TEXT_MID};
    }}
    QLabel#SectionLabel {{
        font-size: 10px;
        letter-spacing: 1px;
        color: {P.TEXT_MID};
        background: transparent;
    }}
    QLabel#SectionCount {{
        font-size: 10px;
        color: {P.TEXT_DIM};
        background: transparent;
    }}
    QLabel#StatLabel {{
        font-size: 9px;
        letter-spacing: 0.5px;
        color: {P.TEXT_MID};
        background: transparent;
    }}
    QLabel#StatValue {{
        font-size: 14px;
        color: {P.TEXT_PRI};
        background: transparent;
    }}
    QLabel#EmptyState {{
        padding: 40px;
        color: {P.TEXT_DIM};
        background: transparent;
    }}
    QFrame#SectionDivider {{
        background-color: {P.BORDER};
    }}
    QLabel#PhysicalLinkValue {{
        font-family: "{F.DATA}";
        font-weight: bold;
        font-size: 14px;
        color: {P.TEXT_PRI};
    }}
    QLabel#LogicalLinkValue {{
        font-family: "{F.DATA}";
        font-weight: bold;
        font-size: 14px;
        color: {P.TEXT_PRI};
    }}

    QScrollArea#PeerListScroll {{
        background-color: {P.VOID};
        border: 1px solid {P.BORDER};
    }}
    QWidget#PeerListContainer {{
        background-color: {P.VOID};
    }}

    QScrollArea#TransparentScroll {{
        background: transparent;
    }}


    QAbstractButton#PlainToggle {{
        border: none;
    }}

    QProgressBar {{
        background-color: {P.VOID};
        border: 1px solid {P.BORDER};
        text-align: center;
        height: 10px;
        border-radius: 1px;
        font-family: "{F.DATA}";
        font-size: 9px;
    }}
    QProgressBar::chunk {{
        background-color: {P.GOLD};
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 4px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {P.BORDER_LIT};
        min-height: 20px;
        border-radius: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {P.AMBER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QTextEdit#ConsoleOutput {{
        background-color: {P.VOID};
        color: {P.TEXT_PRI};
        font-family: "{F.DATA}";
        font-size: 11px;
        border: 1px solid {P.BORDER};
    }}

    QFrame#StatusBar {{
        background-color: {P.VOID};
    }}
    QLabel#StatusLabel {{
        font-size: 9px;
        color: #444;
    }}
    QLabel#StatusValue {{
        font-size: 10px;
        color: {P.AMBER};
        letter-spacing: 1px;
    }}

    QLabel#TransferTitle {{
        color: {P.GOLD};
        font-size: 14px;
    }}
    QLabel#TransferTitle[state="error"] {{
        color: {P.SEVERED};
    }}
    QLabel#TransferTitle[state="ok"] {{
        color: {P.ALIVE};
    }}
    QLabel#TransferSpeed {{
        font-size: 11px;
    }}
    QLabel#TransferStatus[state="error"] {{
        color: {P.SEVERED};
    }}
    QLabel#TransferStatus[state="ok"] {{
        color: {P.ALIVE};
    }}

    QLabel#PulseIcon {{
        background: transparent;
        color: {P.GOLD};
        font-size: 16px;
    }}
    """
