import sys
import csv
import vlc
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QWidget, QFileDialog, QSlider, QListWidget, 
                               QLabel, QLineEdit, QFormLayout, QFrame, QMessageBox, 
                               QComboBox, QDialog, QDialogButtonBox, QScrollArea, QGridLayout)
from PySide6.QtCore import Qt, QTimer, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QCursor, QKeySequence, QShortcut

# ---------- CONFIG ----------
COLORS = {
    "Management": "#F3D97B",
    "Therapeutic": "#4A90E2",
    "Rapport": "#82CD47",
    "Other": "#B2BABB"
}

CLINICAL_PROMPTS = {
    "Management": ["Environment Setup", "Task Complexity", "Safety/Risk Factors", "Posture/Positioning"],
    "Therapeutic": ["Technique/Strategy", "Client Response", "Level of Cueing", "Accuracy/Outcome"],
    "Rapport": ["Engagement Level", "Verbal Reinforcement", "Eye Contact", "Joint Attention"],
    "Other": ["General Observations", "External Distractions"]
}

# ---------- MODERN STYLESHEET ----------
STYLESHEET = f"""
QMainWindow {{ background-color: #F0F2F5; }}
QFrame#SidebarFrame, QFrame#DashboardFrame {{
    background-color: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #DDE1E7;
}}
QFrame#VideoContainer {{ background-color: #000000; border-radius: 15px; }}

QPushButton.CategoryBtn {{
    border-radius: 8px; padding: 12px 5px; min-width: 90px;
    font-weight: bold; border: 2px solid transparent; color: #2C3E50; font-size: 11px;
}}
QPushButton.CategoryBtn:checked {{ border: 2px solid #2C3E50; }}
QPushButton#Management {{ background-color: {COLORS["Management"]}; }}
QPushButton#Therapeutic {{ background-color: {COLORS["Therapeutic"]}; color: white; }}
QPushButton#Rapport {{ background-color: {COLORS["Rapport"]}; }}
QPushButton#Other {{ background-color: {COLORS["Other"]}; }}

QPushButton#PrimaryBtn {{ background-color: #3498DB; color: white; border-radius: 8px; padding: 10px; font-weight: bold; border: none; }}
QPushButton#SecondaryBtn {{ background-color: #FFFFFF; border: 1px solid #D1D1D1; border-radius: 8px; padding: 8px; color: #555; }}
QPushButton#DeleteBtn {{ color: #E74C3C; border: 1px solid #E74C3C; border-radius: 8px; padding: 8px; background: white; }}

QScrollArea {{ border: none; background-color: transparent; }}
QLineEdit {{ border: 1px solid #DDE1E7; border-radius: 6px; padding: 8px; }}
QListWidget {{ background-color: white; border-radius: 10px; border: 1px solid #DDE1E7; padding: 5px; }}

/* Stats Styles */
QLabel#StatHeader {{ font-weight: bold; color: #2C3E50; font-size: 14px; border-bottom: 2px solid #3498DB; padding-bottom: 5px; }}
QLabel#StatVal {{ font-family: 'Courier New'; font-weight: bold; color: #34495E; }}
"""

def format_time_full(ms):
    s = ms / 1000
    m = int(s // 60)
    sec = int(s % 60)
    remainder_ms = int(ms % 1000)
    return f"{m:02}:{sec:02}.{remainder_ms:03}"

# ---------- STRIPED SLIDER ----------
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
                    stripe_w, curr_x, idx = 12, start_px, 0
                    while curr_x < end_px:
                        painter.setBrush(QColor(COLORS.get(cats[idx % len(cats)], "#D3D3D3")))
                        painter.setPen(Qt.PenStyle.NoPen)
                        w = min(stripe_w, end_px - curr_x)
                        painter.drawRect(QRect(curr_x, 8, w, self.height() - 16))
                        curr_x += w
                        idx += 1
                else:
                    painter.setBrush(QColor(COLORS.get(cats[0], "#D3D3D3")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(QRect(start_px, 8, end_px - start_px, self.height() - 16))
        painter.end()
        super().paintEvent(event)

# ---------- EDIT DIALOG ----------
class EditTagDialog(QDialog):
    def __init__(self, tag_data, player_ref, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Clinical Observation")
        self.resize(550, 650)
        self.setStyleSheet(STYLESHEET)
        self.player = player_ref
        layout = QVBoxLayout(self)
        
        time_group = QFrame()
        time_group.setStyleSheet("background: #F8F9FA; border-radius: 8px;")
        time_layout = QHBoxLayout(time_group)
        self.start_in = QLineEdit(str(tag_data['Start']))
        self.end_in = QLineEdit(str(tag_data['End']))
        preview_btn = QPushButton("Seek to Start")
        preview_btn.setObjectName("SecondaryBtn")
        preview_btn.clicked.connect(lambda: self.player.set_time(int(self.start_in.text())))

        time_layout.addWidget(QLabel("Start (ms):"))
        time_layout.addWidget(self.start_in)
        time_layout.addWidget(QLabel("End (ms):"))
        time_layout.addWidget(self.end_in)
        time_layout.addWidget(preview_btn)
        layout.addWidget(time_group)

        layout.addWidget(QLabel("<b>Modify Categories</b>"))
        self.cat_btns = {}
        cat_grid = QGridLayout()
        for i, name in enumerate(COLORS):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("class", "CategoryBtn")
            btn.setObjectName(name)
            if name in tag_data['Categories']: btn.setChecked(True)
            btn.clicked.connect(self.refresh_edit_prompts)
            self.cat_btns[name] = btn
            cat_grid.addWidget(btn, i // 2, i % 2)
        layout.addLayout(cat_grid)

        layout.addWidget(QLabel("<b>Clinical Prompts</b>"))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.prompt_widget = QWidget()
        self.prompt_layout = QFormLayout(self.prompt_widget)
        self.scroll.setWidget(self.prompt_widget)
        layout.addWidget(self.scroll)

        self.prompt_inputs = {}
        self.existing_notes = tag_data.get('Prompts', {})
        self.refresh_edit_prompts()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def refresh_edit_prompts(self):
        while self.prompt_layout.count():
            child = self.prompt_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.prompt_inputs.clear()
        for name, btn in self.cat_btns.items():
            if btn.isChecked():
                for q in CLINICAL_PROMPTS[name]:
                    key = f"{name}_{q}"
                    le = QLineEdit(self.existing_notes.get(key, ""))
                    self.prompt_layout.addRow(QLabel(q), le)
                    self.prompt_inputs[key] = le

    def get_data(self):
        selected_cats = [n for n, b in self.cat_btns.items() if b.isChecked()]
        prompts = {k: v.text() for k, v in self.prompt_inputs.items()}
        return int(self.start_in.text()), int(self.end_in.text()), selected_cats, prompts

# ---------- MAIN WINDOW ----------
class VideoTagger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPOT-C | Clinical Annotation Suite")
        self.resize(1400, 950)
        self.setStyleSheet(STYLESHEET)

        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.all_tags = []
        self.start_time = None
        self.current_video_name = "session_data"

        self.init_ui()
        self.setup_shortcuts()
        
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.update_ui_state)
        self.timer.start()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- TOP ROW (Video + Sidebar) ---
        top_h_split = QHBoxLayout()

        player_side = QVBoxLayout()
        self.video_container = QFrame()
        self.video_container.setObjectName("VideoContainer")
        self.video_container.setMinimumSize(750, 480)
        player_side.addWidget(self.video_container)
        
        if sys.platform.startswith('darwin'):
            self.video_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
            self.mediaplayer.set_nsobject(int(self.video_container.winId()))
        else:
            self.mediaplayer.set_hwnd(int(self.video_container.winId()))

        self.slider = StripedSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(lambda pos: self.mediaplayer.set_time(pos))
        player_side.addWidget(self.slider)

        player_ctrls = QHBoxLayout()
        self.play_btn = QPushButton("Play / Pause")
        self.play_btn.setObjectName("PrimaryBtn")
        self.play_btn.setFixedWidth(120)
        self.play_btn.clicked.connect(self.toggle_playback)
        self.speed_box = QComboBox()
        self.speed_box.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.speed_box.setCurrentIndex(1)
        self.speed_box.currentTextChanged.connect(lambda val: self.mediaplayer.set_rate(float(val.replace("x", ""))))
        player_ctrls.addWidget(self.play_btn)
        player_ctrls.addStretch()
        player_ctrls.addWidget(QLabel("Speed:"))
        player_ctrls.addWidget(self.speed_box)
        player_side.addLayout(player_ctrls)

        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("SidebarFrame")
        sidebar_frame.setFixedWidth(400)
        sidebar = QVBoxLayout(sidebar_frame)

        load_btn = QPushButton("Load Clinical Recording")
        load_btn.setObjectName("PrimaryBtn")
        load_btn.clicked.connect(self.load_video)
        sidebar.addWidget(load_btn)

        sidebar.addWidget(QLabel("\n<b>TAG CATEGORIES</b>"))
        cat_grid = QGridLayout()
        self.cat_btns = {}
        for i, name in enumerate(COLORS):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("class", "CategoryBtn")
            btn.setObjectName(name)
            btn.clicked.connect(self.refresh_prompts)
            self.cat_btns[name] = btn
            cat_grid.addWidget(btn, i // 2, i % 2)
        sidebar.addLayout(cat_grid)

        self.mark_btn = QPushButton("Mark Start Position")
        self.mark_btn.setObjectName("SecondaryBtn")
        self.mark_btn.clicked.connect(self.mark_start)
        sidebar.addWidget(self.mark_btn)

        sidebar.addWidget(QLabel("\n<b>CLINICAL PROMPTS</b>"))
        self.prompt_scroll = QScrollArea()
        self.prompt_scroll.setWidgetResizable(True)
        self.prompt_widget = QWidget()
        self.prompt_layout = QFormLayout(self.prompt_widget)
        self.prompt_scroll.setWidget(self.prompt_widget)
        sidebar.addWidget(self.prompt_scroll, stretch=1)

        self.save_entry_btn = QPushButton("Save Full Entry")
        self.save_entry_btn.setObjectName("PrimaryBtn")
        self.save_entry_btn.clicked.connect(self.save_tag)
        sidebar.addWidget(self.save_entry_btn)

        top_h_split.addLayout(player_side, stretch=2)
        top_h_split.addWidget(sidebar_frame, stretch=1)
        main_layout.addLayout(top_h_split, stretch=5)

        # --- BOTTOM ROW (Log + Dashboard) ---
        bottom_h_split = QHBoxLayout()

        # Log Panel
        log_side = QVBoxLayout()
        log_side.addWidget(QLabel("<b>SESSION ACTIVITY LOG</b> (Double-click to Edit)"))
        self.log = QListWidget()
        self.log.itemDoubleClicked.connect(self.handle_log_click)
        log_side.addWidget(self.log)
        bottom_h_split.addLayout(log_side, 1)

        # Stats Dashboard Panel
        self.dash_frame = QFrame()
        self.dash_frame.setObjectName("DashboardFrame")
        dash_layout = QVBoxLayout(self.dash_frame)
        dash_layout.addWidget(QLabel("<b>CLINICAL INSIGHTS DASHBOARD</b>"), alignment=Qt.AlignCenter)
        
        self.stats_grid = QGridLayout()
        self.stat_widgets = {}
        for i, cat in enumerate(COLORS):
            label = QLabel(f"<b>{cat}</b>")
            data = QLabel("Count: 0 | Time: 0s (0%)")
            data.setObjectName("StatVal")
            self.stats_grid.addWidget(label, i, 0)
            self.stats_grid.addWidget(data, i, 1)
            self.stat_widgets[cat] = data
        dash_layout.addLayout(self.stats_grid)
        dash_layout.addStretch()
        
        bottom_h_split.addWidget(self.dash_frame, 1)
        main_layout.addLayout(bottom_h_split, 2)

        # Footer
        footer = QHBoxLayout()
        self.save_btn = QPushButton("Save Session"); self.save_btn.setObjectName("SecondaryBtn")
        self.save_btn.clicked.connect(lambda: self.export_csv(False))
        self.save_exit_btn = QPushButton("Save & Exit"); self.save_exit_btn.setObjectName("SecondaryBtn")
        self.save_exit_btn.clicked.connect(lambda: self.export_csv(True))
        self.del_btn = QPushButton("Delete Selected"); self.del_btn.setObjectName("DeleteBtn")
        self.del_btn.clicked.connect(self.delete_selected)
        
        footer.addWidget(self.save_btn); footer.addWidget(self.save_exit_btn)
        footer.addWidget(self.del_btn); footer.addStretch()
        exit_btn = QPushButton("Exit Tool"); exit_btn.setObjectName("SecondaryBtn")
        exit_btn.clicked.connect(self.close); footer.addWidget(exit_btn)
        main_layout.addLayout(footer)

    # --- LOGIC ---
    def refresh_prompts(self):
        while self.prompt_layout.count():
            child = self.prompt_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.prompt_inputs = {}
        for name, btn in self.cat_btns.items():
            if btn.isChecked():
                for q in CLINICAL_PROMPTS[name]:
                    le = QLineEdit()
                    self.prompt_layout.addRow(QLabel(q), le)
                    self.prompt_inputs[f"{name}_{q}"] = le

    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video")
        if path:
            self.current_video_name = os.path.splitext(os.path.basename(path))[0]
            self.mediaplayer.set_media(self.instance.media_new(path))
            self.mediaplayer.play()
            QTimer.singleShot(200, self.mediaplayer.pause)

    def toggle_playback(self):
        if self.mediaplayer.is_playing(): self.mediaplayer.pause()
        else: self.mediaplayer.play()

    def update_ui_state(self):
        if self.mediaplayer.get_state() not in [vlc.State.NothingSpecial, vlc.State.Stopped]:
            t, d = self.mediaplayer.get_time(), self.mediaplayer.get_length()
            if d > 0: self.slider.setRange(0, d); self.slider.setValue(t)

    def mark_start(self):
        self.start_time = self.mediaplayer.get_time()
        self.mark_btn.setText(f"In: {format_time_full(self.start_time)}")

    def save_tag(self):
        cats = [n for n, b in self.cat_btns.items() if b.isChecked()]
        if self.start_time is None or not cats: return
        tag = {"Start": self.start_time, "End": self.mediaplayer.get_time(), "Categories": cats, "Prompts": {k: v.text() for k, v in self.prompt_inputs.items()}}
        self.all_tags.append(tag)
        self.slider.tags = self.all_tags
        self.slider.update()
        self.log.addItem(f"{format_time_full(tag['Start'])} - {format_time_full(tag['End'])} | {', '.join(cats)}")
        self.update_stats()
        self.start_time = None; self.mark_btn.setText("Mark Start Position")
        for b in self.cat_btns.values(): b.setChecked(False)
        self.refresh_prompts()

    def handle_log_click(self, item):
        idx = self.log.row(item)
        dlg = EditTagDialog(self.all_tags[idx], self.mediaplayer, self)
        if dlg.exec():
            s, e, cats, prompts = dlg.get_data()
            self.all_tags[idx] = {"Start": s, "End": e, "Categories": cats, "Prompts": prompts}
            self.log.item(idx).setText(f"{format_time_full(s)} - {format_time_full(e)} | {', '.join(cats)}")
            self.update_stats(); self.slider.update()

    def delete_selected(self):
        row = self.log.currentRow()
        if row >= 0: self.log.takeItem(row); self.all_tags.pop(row); self.update_stats(); self.slider.update()

    def update_stats(self):
        total_tagged_ms = sum(t['End'] - t['Start'] for t in self.all_tags)
        for cat in COLORS:
            count = sum(1 for t in self.all_tags if cat in t['Categories'])
            duration_ms = sum((t['End'] - t['Start']) for t in self.all_tags if cat in t['Categories'])
            percent = (duration_ms / total_tagged_ms * 100) if total_tagged_ms > 0 else 0
            self.stat_widgets[cat].setText(f"Count: {count} | Time: {duration_ms/1000:.1f}s ({percent:.1f}%)")

    def export_csv(self, exit_after=False):
        if not self.all_tags: return
        filename = f"{self.current_video_name}_datacsv.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save Session Data", filename, "CSV (*.csv)")
        if path:
            with open(path, 'w', newline='') as f:
                w = csv.writer(f); w.writerow(["Start_ms", "End_ms", "Categories", "Responses"])
                for t in self.all_tags: w.writerow([t['Start'], t['End'], "|".join(t['Categories']), str(t['Prompts'])])
            if exit_after: self.close()

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Space"), self, self.toggle_playback)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoTagger()
    window.show()
    sys.exit(app.exec())