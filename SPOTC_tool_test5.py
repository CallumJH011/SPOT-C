import sys
import csv
import vlc
import os
import ast
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QWidget, QFileDialog, QSlider, QListWidget, 
                               QLabel, QLineEdit, QFormLayout, QFrame, QMessageBox, 
                               QComboBox, QDialog, QDialogButtonBox, QScrollArea, QGridLayout,
                               QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint
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

# ---------- STYLESHEET ----------
STYLESHEET = f"""
QMainWindow {{ background-color: #F4F7F9; }}
QFrame#PanelFrame {{ background-color: #FFFFFF; border-radius: 12px; border: 1px solid #DDE1E7; }}
QFrame#VideoContainer {{ background-color: #000000; border-radius: 12px; }}
QLabel#TitleLabel {{ font-size: 14px; font-weight: bold; color: #2C3E50; }}

QPushButton.CategoryBtn {{
    border-radius: 8px; padding: 10px 2px; min-width: 100px;
    font-weight: bold; border: 2px solid transparent; color: #2C3E50; font-size: 12px;
}}
QPushButton.CategoryBtn:checked {{ border: 2px solid #2C3E50; }}
QPushButton#Management {{ background-color: {COLORS["Management"]}; }}
QPushButton#Therapeutic {{ background-color: {COLORS["Therapeutic"]}; color: white; }}
QPushButton#Rapport {{ background-color: {COLORS["Rapport"]}; }}
QPushButton#Other {{ background-color: {COLORS["Other"]}; }}

QPushButton#PrimaryBtn {{ 
    background-color: #009DDC; 
    color: white; 
    border-radius: 6px; 
    padding: 10px; 
    font-weight: bold; 
    border: none; 
}}
QPushButton#PrimaryBtn:hover {{ background-color: #008AC2; }}

/* Logic for the Load from Save button state */
QPushButton#PrimaryBtn:disabled {{ 
    background-color: #BDC3C7; 
    color: #ECF0F1; 
}}

QPushButton#SecondaryBtn {{ background-color: #FFFFFF; border: 1px solid #D1D1D1; border-radius: 6px; padding: 8px 15px; color: #555; font-weight: 500; }}
QPushButton#DeleteBtn {{ color: #E74C3C; border: 1px solid #FADBD8; border-radius: 6px; padding: 8px 15px; background: #FDEDEC; }}

QScrollArea {{ border: 1px solid #F0F0F0; border-radius: 8px; background: #FAFAFA; }}
QLineEdit {{ border: 1px solid #DDE1E7; border-radius: 4px; padding: 8px; background: white; }}
QListWidget {{ background-color: white; border-radius: 8px; border: 1px solid #DDE1E7; }}
"""

def format_time_full(ms):
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    return f"{m:02}:{s:02}.{ms:03}"

# ---------- MULTI-COLORED STRIPED SLIDER ----------
class StripedSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.tags = []
        self.setFixedHeight(35) 

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.maximum() > 0:
            for tag in self.tags:
                cats = tag.get('Categories', ["Other"])
                start_px = int((tag['Start'] / self.maximum()) * self.width())
                end_px = int((tag['End'] / self.maximum()) * self.width())
                bar_y, bar_h = 6, self.height() - 12

                if len(cats) > 1:
                    stripe_w = 10 
                    curr_x, idx = start_px, 0
                    while curr_x < end_px:
                        color = QColor(COLORS.get(cats[idx % len(cats)], "#D3D3D3"))
                        painter.setBrush(color)
                        painter.setPen(Qt.PenStyle.NoPen)
                        w = min(stripe_w, end_px - curr_x)
                        painter.drawRect(QRect(curr_x, bar_y, w, bar_h))
                        curr_x += w
                        idx += 1
                else:
                    color = QColor(COLORS.get(cats[0], "#D3D3D3"))
                    painter.setBrush(color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(QRect(start_px, bar_y, max(end_px - start_px, 3), bar_h))
        painter.end()
        super().paintEvent(event)

class EditTagDialog(QDialog):
    def __init__(self, tag_data, player_ref, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Clinical Observation")
        self.resize(500, 600); self.setStyleSheet(STYLESHEET)
        self.player, self.tag_data = player_ref, tag_data
        layout = QVBoxLayout(self)
        
        t_group = QFrame(); t_group.setObjectName("PanelFrame")
        t_layout = QHBoxLayout(t_group)
        self.start_in = QLineEdit(str(tag_data['Start']))
        self.end_in = QLineEdit(str(tag_data['End']))
        sk = QPushButton("Seek"); sk.setObjectName("SecondaryBtn")
        sk.clicked.connect(lambda: self.player.set_time(int(self.start_in.text())))
        t_layout.addWidget(QLabel("In:")); t_layout.addWidget(self.start_in)
        t_layout.addWidget(QLabel("Out:")); t_layout.addWidget(self.end_in)
        t_layout.addWidget(sk); layout.addWidget(t_group)

        self.cat_btns = {}; grid = QGridLayout()
        for i, name in enumerate(COLORS):
            btn = QPushButton(name); btn.setCheckable(True); btn.setProperty("class", "CategoryBtn"); btn.setObjectName(name)
            if name in tag_data['Categories']: btn.setChecked(True)
            btn.clicked.connect(self.refresh_edit_prompts); self.cat_btns[name] = btn
            grid.addWidget(btn, i // 2, i % 2)
        layout.addLayout(grid)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.p_widget = QWidget(); self.p_layout = QFormLayout(self.p_widget)
        self.scroll.setWidget(self.p_widget); layout.addWidget(self.scroll)
        self.prompt_inputs = {}; self.refresh_edit_prompts()
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)

    def refresh_edit_prompts(self):
        while self.p_layout.count():
            w = self.p_layout.takeAt(0).widget()
            if w: w.deleteLater()
        self.prompt_inputs = {}
        for name, btn in self.cat_btns.items():
            if btn.isChecked():
                for q in CLINICAL_PROMPTS[name]:
                    key = f"{name}_{q}"
                    le = QLineEdit(self.tag_data.get('Prompts', {}).get(key, ""))
                    self.p_layout.addRow(QLabel(q), le); self.prompt_inputs[key] = le

    def get_data(self):
        cats = [n for n, b in self.cat_btns.items() if b.isChecked()]
        p = {k: v.text() for k, v in self.prompt_inputs.items()}
        return int(self.start_in.text() or 0), int(self.end_in.text() or 0), cats, p

# ---------- MAIN WINDOW ----------
class VideoTagger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPOT-C | Clinical Annotation Suite")
        self.resize(1300, 900); self.setStyleSheet(STYLESHEET)
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.all_tags, self.start_time, self.video_name = [], None, "No Video Loaded"

        self.init_ui()
        self.setup_shortcuts()
        self.timer = QTimer(self); self.timer.setInterval(50)
        self.timer.timeout.connect(self.update_ui_state); self.timer.start()

    def init_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central); main_layout.setContentsMargins(20, 20, 20, 20); main_layout.setSpacing(15)

        top_h = QHBoxLayout(); top_h.setSpacing(20)
        p_side = QVBoxLayout()
        self.title_label = QLabel(self.video_name); self.title_label.setObjectName("TitleLabel")
        p_side.addWidget(self.title_label)
        self.video_container = QFrame(); self.video_container.setObjectName("VideoContainer")
        self.video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        p_side.addWidget(self.video_container, stretch=1)
        
        if sys.platform.startswith('darwin'):
            self.video_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
            self.mediaplayer.set_nsobject(int(self.video_container.winId()))
        else: self.mediaplayer.set_hwnd(int(self.video_container.winId()))

        self.slider = StripedSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(lambda pos: self.mediaplayer.set_time(pos))
        p_side.addWidget(self.slider)
        
        ctrls = QHBoxLayout()
        self.play_btn = QPushButton("Play / Pause"); self.play_btn.setObjectName("PrimaryBtn")
        self.play_btn.clicked.connect(self.toggle_playback); ctrls.addWidget(self.play_btn)
        ctrls.addStretch(); ctrls.addWidget(QLabel("Speed:"))
        self.speed = QComboBox(); self.speed.addItems(["0.5x", "1.0x", "1.5x", "2.0x"]); self.speed.setCurrentIndex(1)
        self.speed.currentTextChanged.connect(lambda v: self.mediaplayer.set_rate(float(v.replace("x",""))))
        ctrls.addWidget(self.speed); p_side.addLayout(ctrls)

        # SIDEBAR
        sidebar = QFrame(); sidebar.setObjectName("PanelFrame")
        sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        side_layout = QVBoxLayout(sidebar); side_layout.setSpacing(10)
        l_row = QHBoxLayout()
        
        # Both buttons now use PrimaryBtn which is blue when enabled
        self.load_rec_btn = QPushButton("Load Recording"); self.load_rec_btn.setObjectName("PrimaryBtn")
        self.load_rec_btn.clicked.connect(self.load_video)
        
        self.ls_btn = QPushButton("Load from Save"); self.ls_btn.setObjectName("PrimaryBtn")
        self.ls_btn.setEnabled(False)
        self.ls_btn.clicked.connect(self.load_from_csv)
        
        l_row.addWidget(self.load_rec_btn); l_row.addWidget(self.ls_btn); side_layout.addLayout(l_row)
        side_layout.addWidget(QLabel("<b>TAG CATEGORIES</b>"))
        grid = QGridLayout(); self.cat_btns = {}
        for i, name in enumerate(COLORS):
            btn = QPushButton(name); btn.setCheckable(True); btn.setProperty("class", "CategoryBtn"); btn.setObjectName(name)
            btn.clicked.connect(self.refresh_prompts); self.cat_btns[name] = btn
            grid.addWidget(btn, i // 2, i % 2)
        side_layout.addLayout(grid)
        self.mark_btn = QPushButton("Mark Start Position"); self.mark_btn.setObjectName("SecondaryBtn")
        self.mark_btn.clicked.connect(self.mark_start); side_layout.addWidget(self.mark_btn)
        side_layout.addWidget(QLabel("<b>CLINICAL PROMPTS</b>"))
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.p_widget = QWidget(); self.p_layout = QFormLayout(self.p_widget)
        self.scroll.setWidget(self.p_widget); side_layout.addWidget(self.scroll, stretch=1)
        save_e = QPushButton("Save Full Entry"); save_e.setObjectName("PrimaryBtn")
        save_e.clicked.connect(self.save_tag); side_layout.addWidget(save_e)

        top_h.addLayout(p_side, stretch=2); top_h.addWidget(sidebar, stretch=1)
        main_layout.addLayout(top_h, stretch=3)

        # BOTTOM AREA
        bottom_h = QHBoxLayout(); bottom_h.setSpacing(20)
        log_side = QVBoxLayout()
        log_side.addWidget(QLabel("<b>SESSION ACTIVITY LOG</b>"))
        self.log = QListWidget(); self.log.itemDoubleClicked.connect(self.handle_log_double_click)
        log_side.addWidget(self.log); bottom_h.addLayout(log_side, 1)

        dash = QFrame(); dash.setObjectName("PanelFrame"); d_layout = QVBoxLayout(dash)
        d_layout.addWidget(QLabel("<b>CLINICAL DASHBOARD</b>"), alignment=Qt.AlignCenter)
        self.s_grid = QGridLayout(); self.s_widgets = {}
        for i, cat in enumerate(COLORS):
            l = QLabel(f"<b>{cat}:</b>"); d = QLabel("Count: 0 | Time: 0.0s (0%)")
            self.s_grid.addWidget(l, i, 0); self.s_grid.addWidget(d, i, 1); self.s_widgets[cat] = d
        d_layout.addLayout(self.s_grid); d_layout.addStretch(); bottom_h.addWidget(dash, 1)
        main_layout.addLayout(bottom_h, 1)

        # FOOTER
        footer = QHBoxLayout()
        s_btn = QPushButton("Save Session"); s_btn.setObjectName("SecondaryBtn"); s_btn.clicked.connect(lambda: self.save_csv(False))
        se_btn = QPushButton("Save & Exit"); se_btn.setObjectName("SecondaryBtn"); se_btn.clicked.connect(lambda: self.save_csv(True))
        del_btn = QPushButton("Delete Selected"); del_btn.setObjectName("SecondaryBtn"); del_btn.setStyleSheet("color:#E74C3C;"); del_btn.clicked.connect(self.delete_selected)
        footer.addWidget(s_btn); footer.addWidget(se_btn); footer.addWidget(del_btn); footer.addStretch()
        ex = QPushButton("Exit Tool"); ex.setObjectName("SecondaryBtn"); ex.clicked.connect(self.close); footer.addWidget(ex)
        main_layout.addLayout(footer)

    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Videos (*.mp4 *.mov *.avi *.mkv)")
        if path:
            self.all_tags, self.log.clear(), self.update_stats()
            self.video_name = os.path.basename(path); self.title_label.setText(self.video_name)
            self.mediaplayer.set_media(self.instance.media_new(path))
            self.mediaplayer.play(); QTimer.singleShot(200, self.mediaplayer.pause)
            self.ls_btn.setEnabled(True) # Enabled turns it blue via CSS PrimaryBtn selector

    def load_from_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Save", "", "CSV (*.csv)")
        if not path: return
        try:
            with open(path, 'r', newline='') as f:
                reader = csv.DictReader(f); new_tags = []; self.log.clear()
                for row in reader:
                    tag = {"Start": int(row['Start_ms']), "End": int(row['End_ms']), "Categories": row['Categories'].split('|'), "Prompts": ast.literal_eval(row['Responses'])}
                    new_tags.append(tag); self.log.addItem(f"{tag['Categories']} | {format_time_full(tag['Start'])}")
                self.all_tags = new_tags; self.slider.tags = self.all_tags; self.slider.update(); self.update_stats()
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def toggle_playback(self): self.mediaplayer.pause() if self.mediaplayer.is_playing() else self.mediaplayer.play()
    def update_ui_state(self):
        if self.mediaplayer.get_state() not in [vlc.State.NothingSpecial, vlc.State.Stopped]:
            t, d = self.mediaplayer.get_time(), self.mediaplayer.get_length()
            if d > 0:
                self.slider.setRange(0, d)
                if not self.slider.isSliderDown(): self.slider.setValue(t)

    def mark_start(self): self.start_time = self.mediaplayer.get_time(); self.mark_btn.setText(f"In: {format_time_full(self.start_time)}")
    def save_tag(self):
        cats = [n for n, b in self.cat_btns.items() if b.isChecked()]
        if self.start_time is None or not cats: return
        tag = {"Start": self.start_time, "End": self.mediaplayer.get_time(), "Categories": cats, "Prompts": {k: v.text() for k, v in self.prompt_inputs.items()}}
        self.all_tags.append(tag); self.slider.tags = self.all_tags; self.slider.update()
        self.log.addItem(f"{', '.join(cats)} | {format_time_full(tag['Start'])}")
        self.update_stats(); self.start_time = None; self.mark_btn.setText("Mark Start Position")
        for b in self.cat_btns.values(): b.setChecked(False); self.refresh_prompts()

    def handle_log_double_click(self, item):
        idx = self.log.row(item); dlg = EditTagDialog(self.all_tags[idx], self.mediaplayer, self)
        if dlg.exec():
            s, e, c, p = dlg.get_data(); self.all_tags[idx] = {"Start":s, "End":e, "Categories":c, "Prompts":p}
            item.setText(f"{', '.join(c)} | {format_time_full(s)}")
            self.update_stats(); self.slider.update()

    def delete_selected(self):
        row = self.log.currentRow()
        if row >= 0: self.log.takeItem(row); self.all_tags.pop(row); self.update_stats(); self.slider.update()

    def update_stats(self):
        total = sum(t['End'] - t['Start'] for t in self.all_tags)
        for cat in COLORS:
            count = sum(1 for t in self.all_tags if cat in t['Categories'])
            dur = sum((t['End'] - t['Start']) for t in self.all_tags if cat in t['Categories'])
            pct = (dur / total * 100) if total > 0 else 0
            self.s_widgets[cat].setText(f"Count: {count} | Time: {dur/1000:.1f}s ({pct:.1f}%)")

    def save_csv(self, exit_after):
        if not self.all_tags: return
        p, _ = QFileDialog.getSaveFileName(self, "Save Session", f"{os.path.splitext(self.video_name)[0]}_datacsv.csv", "CSV (*.csv)")
        if p:
            with open(p, 'w', newline='') as f:
                w = csv.writer(f); w.writerow(["Start_ms", "End_ms", "Categories", "Responses"])
                for t in self.all_tags: w.writerow([t['Start'], t['End'], "|".join(t['Categories']), str(t['Prompts'])])
            if exit_after: self.close()

    def refresh_prompts(self):
        while self.p_layout.count():
            w = self.p_layout.takeAt(0).widget()
            if w: w.deleteLater()
        self.prompt_inputs = {}
        for name, btn in self.cat_btns.items():
            if btn.isChecked():
                for q in CLINICAL_PROMPTS[name]:
                    le = QLineEdit(); self.p_layout.addRow(QLabel(q), le); self.prompt_inputs[f"{name}_{q}"] = le

    def setup_shortcuts(self): QShortcut(QKeySequence("Space"), self).activated.connect(self.toggle_playback)

if __name__ == "__main__":
    app = QApplication(sys.argv); w = VideoTagger(); w.show(); sys.exit(app.exec())