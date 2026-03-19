import sys
import csv
import vlc
import ast
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QWidget, QFileDialog, QSlider, QListWidget, 
                               QLabel, QLineEdit, QFormLayout, QFrame, QMessageBox, 
                               QComboBox, QDialog, QDialogButtonBox, QScrollArea)
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QColor, QCursor, QKeySequence, QShortcut

# ---------- CONFIG ----------
COLORS = {
    "Management": "#F3D97B",
    "Therapeutic": "#4A90E2",
    "Rapport": "#82CD47",
    "Other": "#D3D3D3"
}

CLINICAL_PROMPTS = {
    "Management": ["Environment Setup", "Task Complexity", "Safety/Risk Factors", "Posture/Positioning"],
    "Therapeutic": ["Technique/Strategy", "Client Response", "Level of Cueing", "Accuracy/Outcome"],
    "Rapport": ["Engagement Level", "Verbal Reinforcement", "Eye Contact", "Joint Attention"],
    "Other": ["General Observations", "External Distractions"]
}

STYLESHEET = f"""
QMainWindow {{ background-color: #F8F9FA; }}
QLabel {{ color: #333; font-weight: 600; font-size: 13px; }}

QPushButton.CategoryBtn {{
    border-radius: 12px;
    padding: 12px;
    font-size: 12px;
    font-weight: bold;
    border: 2px solid transparent;
    color: #000;
}}
QPushButton#Management {{ background-color: {COLORS["Management"]}; }}
QPushButton#Therapeutic {{ background-color: {COLORS["Therapeutic"]}; }}
QPushButton#Rapport {{ background-color: {COLORS["Rapport"]}; }}
QPushButton#Other {{ background-color: {COLORS["Other"]}; }}
QPushButton.CategoryBtn:checked {{ border: 3px solid #333; }}

QPushButton#PrimaryBtn {{
    background-color: #4A90E2;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px;
    font-weight: bold;
}}
QPushButton#PrimaryBtn:hover {{ background-color: #357ABD; }}

QPushButton#ActionBtn {{
    background-color: #FFFFFF;
    border: 1px solid #D1D1D1;
    border-radius: 8px;
    padding: 8px;
}}

QPushButton#DeleteBtn {{
    color: #C0392B;
    border: 1px solid #C0392B;
    border-radius: 8px;
    padding: 8px;
    background: white;
}}
QPushButton#DeleteBtn:hover {{ background-color: #FDEDEC; }}

QLineEdit {{ border: 1px solid #DDD; border-radius: 4px; padding: 6px; }}
QListWidget {{ border: 1px solid #EEE; border-radius: 8px; background: #FAFAFA; }}
"""

def format_time_full(ms):
    s = ms / 1000
    m = int(s // 60)
    sec = int(s % 60)
    remainder_ms = int(ms % 1000)
    return f"{m:02}:{sec:02}.{remainder_ms:03}"

# ---------- IMPROVED EDIT DIALOG ----------
class EditTagDialog(QDialog):
    def __init__(self, tag_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Clinical Tag")
        self.resize(600, 500)
        self.setStyleSheet(STYLESHEET)
        
        layout = QVBoxLayout(self)

        # Time Inputs
        time_layout = QHBoxLayout()
        self.start_in = QLineEdit(str(tag_data['Start']))
        self.end_in = QLineEdit(str(tag_data['End']))
        time_layout.addWidget(QLabel("Start (ms):"))
        time_layout.addWidget(self.start_in)
        time_layout.addWidget(QLabel("End (ms):"))
        time_layout.addWidget(self.end_in)
        layout.addLayout(time_layout)

        # Categories
        layout.addWidget(QLabel("<b>Categories</b>"))
        self.cat_btns = {}
        cat_layout = QHBoxLayout()
        for name in COLORS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("class", "CategoryBtn")
            btn.setObjectName(name)
            if name in tag_data['Categories']:
                btn.setChecked(True)
            btn.clicked.connect(self.refresh_edit_prompts)
            self.cat_btns[name] = btn
            cat_layout.addWidget(btn)
        layout.addLayout(cat_layout)

        # Prompts
        layout.addWidget(QLabel("<b>Prompts</b>"))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.prompt_widget = QWidget()
        self.prompt_layout = QFormLayout(self.prompt_widget)
        self.scroll.setWidget(self.prompt_widget)
        layout.addWidget(self.scroll)

        self.prompt_inputs = {}
        self.initial_prompts = tag_data['Prompts']
        self.refresh_edit_prompts()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def refresh_edit_prompts(self):
        for i in reversed(range(self.prompt_layout.count())):
            item = self.prompt_layout.itemAt(i)
            if item.widget(): item.widget().setParent(None)
        self.prompt_inputs.clear()

        for name, btn in self.cat_btns.items():
            if btn.isChecked():
                for q in CLINICAL_PROMPTS[name]:
                    key = f"{name}_{q}"
                    val = self.initial_prompts.get(key, "")
                    le = QLineEdit(val)
                    self.prompt_layout.addRow(QLabel(q), le)
                    self.prompt_inputs[key] = le

    def get_data(self):
        selected_cats = [n for n, b in self.cat_btns.items() if b.isChecked()]
        prompts = {k: v.text() for k, v in self.prompt_inputs.items()}
        return int(self.start_in.text()), int(self.end_in.text()), selected_cats, prompts

# ---------- CUSTOM SLIDER ----------
class StripedSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.tags = []

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.maximum() > 0:
            for tag in self.tags:
                cats = tag['Categories']
                start_px = int((tag['Start'] / self.maximum()) * self.width())
                end_px = int((tag['End'] / self.maximum()) * self.width())
                if len(cats) > 1:
                    stripe_w, curr_x, idx = 10, start_px, 0
                    while curr_x < end_px:
                        painter.setBrush(QColor(COLORS.get(cats[idx % len(cats)], "#D3D3D3")))
                        painter.setPen(Qt.PenStyle.NoPen)
                        w = min(stripe_w, end_px - curr_x)
                        painter.drawRect(QRect(curr_x, 6, w, self.height() - 12))
                        curr_x += w
                        idx += 1
                else:
                    painter.setBrush(QColor(COLORS.get(cats[0], "#D3D3D3")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(QRect(start_px, 6, end_px - start_px, self.height() - 12))
        painter.end()
        super().paintEvent(event)

# ---------- MAIN WINDOW ----------
class VideoTagger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPOT-C | Clinical Annotation Tool")
        self.resize(1280, 850)
        self.setStyleSheet(STYLESHEET)

        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()

        self.all_tags = []
        self.start_time = None
        self.prompt_widgets = {}

        self.init_ui()
        self.setup_shortcuts()
        
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui_state)
        self.timer.start()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        top_h_split = QHBoxLayout()

        # Left: Player
        player_side = QVBoxLayout()
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background: #000; border-radius: 15px;")
        player_side.addWidget(self.video_frame, stretch=5)
        
        if sys.platform.startswith('darwin'):
            self.video_frame.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
            self.mediaplayer.set_nsobject(int(self.video_frame.winId()))
        else:
            self.mediaplayer.set_hwnd(int(self.video_frame.winId()))

        self.slider = StripedSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.set_video_position)
        player_side.addWidget(self.slider)

        ctrl_bar = QHBoxLayout()
        self.play_btn = QPushButton("Play / Pause")
        self.play_btn.setObjectName("PrimaryBtn")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.speed_box = QComboBox()
        self.speed_box.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.speed_box.setCurrentIndex(1)
        self.speed_box.currentTextChanged.connect(self.change_speed)
        ctrl_bar.addWidget(self.play_btn)
        ctrl_bar.addWidget(QLabel("Speed:"))
        ctrl_bar.addWidget(self.speed_box)
        player_side.addLayout(ctrl_bar)

        # Right: Sidebar
        sidebar = QVBoxLayout()
        load_btn = QPushButton("📁 Load Clinical Recording")
        load_btn.setObjectName("PrimaryBtn")
        load_btn.clicked.connect(self.load_video)
        sidebar.addWidget(load_btn)

        sidebar.addWidget(QLabel("\nTAG CATEGORIES"))
        self.cat_btns = {}
        cat_grid = QHBoxLayout()
        for name in COLORS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("class", "CategoryBtn")
            btn.setObjectName(name)
            btn.clicked.connect(self.refresh_prompts)
            self.cat_btns[name] = btn
            cat_grid.addWidget(btn)
        sidebar.addLayout(cat_grid)

        self.mark_btn = QPushButton("⏱ Mark Start")
        self.mark_btn.setObjectName("ActionBtn")
        self.mark_btn.clicked.connect(self.mark_start)
        sidebar.addWidget(self.mark_btn)

        sidebar.addWidget(QLabel("\nCLINICAL PROMPTS"))
        self.prompt_area = QWidget()
        self.prompt_layout = QFormLayout(self.prompt_area)
        sidebar.addWidget(self.prompt_area)

        save_btn = QPushButton("✅ Save Full Entry")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.clicked.connect(self.save_tag)
        sidebar.addWidget(save_btn)
        sidebar.addStretch()

        top_h_split.addLayout(player_side, stretch=2)
        top_h_split.addLayout(sidebar, stretch=1)

        layout.addLayout(top_h_split, stretch=4)
        layout.addWidget(QLabel("<b>SESSION LOG</b> (Double-click to Edit Tag)"))
        self.log = QListWidget()
        self.log.itemDoubleClicked.connect(self.handle_log_click)
        layout.addWidget(self.log, stretch=1)

        footer = QHBoxLayout()
        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_csv)
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setObjectName("DeleteBtn")
        delete_btn.clicked.connect(self.delete_selected)
        exit_btn = QPushButton("Exit Tool")
        exit_btn.clicked.connect(self.close)
        
        footer.addWidget(export_btn)
        footer.addWidget(delete_btn)
        footer.addStretch()
        footer.addWidget(exit_btn)
        layout.addLayout(footer)

    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Videos (*.mp4 *.mov *.avi)")
        if path:
            media = self.instance.media_new(path)
            self.mediaplayer.set_media(media)
            self.mediaplayer.play()
            QTimer.singleShot(200, self.mediaplayer.pause)

    def toggle_playback(self):
        self.mediaplayer.pause() if self.mediaplayer.is_playing() else self.mediaplayer.play()

    def change_speed(self, val):
        self.mediaplayer.set_rate(float(val.replace("x", "")))

    def update_ui_state(self):
        if self.mediaplayer.get_state() not in [vlc.State.NothingSpecial, vlc.State.Stopped]:
            t = self.mediaplayer.get_time()
            d = self.mediaplayer.get_length()
            if d > 0:
                self.slider.setRange(0, d)
                self.slider.setValue(t)

    def set_video_position(self, pos):
        self.mediaplayer.set_time(pos)

    def refresh_prompts(self):
        for i in reversed(range(self.prompt_layout.count())):
            item = self.prompt_layout.itemAt(i)
            if item.widget(): item.widget().setParent(None)
        self.prompt_widgets.clear()
        for name, btn in self.cat_btns.items():
            if btn.isChecked():
                for q in CLINICAL_PROMPTS[name]:
                    le = QLineEdit()
                    self.prompt_layout.addRow(QLabel(q), le)
                    self.prompt_widgets[f"{name}_{q}"] = le

    def mark_start(self):
        self.start_time = self.mediaplayer.get_time()
        self.mark_btn.setText(f"In: {format_time_full(self.start_time)}")

    def save_tag(self):
        cats = [n for n, b in self.cat_btns.items() if b.isChecked()]
        if self.start_time is None or not cats: return
        tag = {
            "Start": self.start_time, "End": self.mediaplayer.get_time(),
            "Categories": cats, "Prompts": {k: v.text() for k, v in self.prompt_widgets.items()}
        }
        self.all_tags.append(tag)
        self.slider.tags = self.all_tags
        self.slider.update()
        self.log.addItem(f"[{', '.join(cats)}] {format_time_full(tag['Start'])} - {format_time_full(tag['End'])}")
        self.start_time = None
        self.mark_btn.setText("⏱ Mark Start")
        for b in self.cat_btns.values(): b.setChecked(False)
        self.refresh_prompts()

    def handle_log_click(self, item):
        idx = self.log.row(item)
        dlg = EditTagDialog(self.all_tags[idx], self)
        if dlg.exec():
            s, e, cats, prompts = dlg.get_data()
            self.all_tags[idx] = {"Start": s, "End": e, "Categories": cats, "Prompts": prompts}
            self.log.item(idx).setText(f"[{', '.join(cats)}] {format_time_full(s)} - {format_time_full(e)}")
            self.slider.update()

    def delete_selected(self):
        row = self.log.currentRow()
        if row >= 0:
            self.log.takeItem(row)
            self.all_tags.pop(row)
            self.slider.update()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", "CSV (*.csv)")
        if path:
            with open(path, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(["Start_ms", "End_ms", "Categories", "Responses"])
                for t in self.all_tags:
                    w.writerow([t['Start'], t['End'], "|".join(t['Categories']), str(t['Prompts'])])

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Space"), self, self.toggle_playback)
        QShortcut(QKeySequence("S"), self, self.mark_start)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoTagger()
    window.show()
    sys.exit(app.exec())