import sys
import csv
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QSlider, QListWidget, 
                             QCheckBox, QLabel, QLineEdit, QFormLayout, QFrame)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl, qInstallMessageHandler, QRect
from PyQt6.QtGui import QPainter, QColor, QPalette

# --- Color Palette Definition ---
COLORS = {
    "Management": QColor("#F3D97B"),   # Tasteful Yellow
    "Therapeutic": QColor("#A8E6CF"),  # Nice Green
    "Rapport": QColor("#A1E3F9"),      # Nice Aqua
    "Other": QColor("#D3D3D3")         # Subtle Grey
}

# --- Styled UI (Light Mode) ---
STYLESHEET = """
QMainWindow {
    background-color: #F8F9FA;
}
QLabel {
    color: #333333;
    font-size: 13px;
    font-weight: 500;
}
QPushButton {
    background-color: #FFFFFF;
    color: #333;
    border-radius: 6px;
    padding: 10px;
    border: 1px solid #D1D1D1;
}
QPushButton:hover {
    background-color: #F0F0F0;
}
QPushButton#PrimaryBtn {
    background-color: #4A90E2;
    color: white;
    border: none;
}
QPushButton#PrimaryBtn:hover {
    background-color: #357ABD;
}
QPushButton#ExitBtn {
    color: #C0392B;
    border: 1px solid #C0392B;
}
QPushButton#ExitBtn:hover {
    background-color: #FDEDEC;
}
QLineEdit {
    border: 1px solid #D1D1D1;
    border-radius: 4px;
    padding: 6px;
    background: white;
}
QListWidget {
    background-color: white;
    border: 1px solid #D1D1D1;
    border-radius: 6px;
}
/* Unique colors for checkboxes */
QCheckBox#Management { color: #856404; font-weight: bold; }
QCheckBox#Therapeutic { color: #155724; font-weight: bold; }
QCheckBox#Rapport { color: #0C5460; font-weight: bold; }
QCheckBox#Other { color: #383D41; font-weight: bold; }
"""

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
                total_width = end_px - start_px
                
                if len(cats) > 1:
                    # Draw Striped Pattern
                    stripe_width = 10 
                    current_x = start_px
                    idx = 0
                    while current_x < end_px:
                        color = COLORS.get(cats[idx % len(cats)], COLORS["Other"])
                        painter.setBrush(color)
                        painter.setPen(Qt.PenStyle.NoPen)
                        w = min(stripe_width, end_px - current_x)
                        painter.drawRect(QRect(current_x, 4, w, self.height() - 8))
                        current_x += w
                        idx += 1
                else:
                    # Draw Solid Block
                    color = COLORS.get(cats[0], COLORS["Other"])
                    painter.setBrush(color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(QRect(start_px, 4, end_px - start_px, self.height() - 8))
        
        painter.end()
        super().paintEvent(event)

class VideoTagger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPOT-C | Clinical Observation Tool")
        self.resize(1200, 900)
        self.setStyleSheet(STYLESHEET)

        self.mediaPlayer = QMediaPlayer()
        self.videoWidget = QVideoWidget()
        self.audioOutput = QAudioOutput()
        self.mediaPlayer.setVideoOutput(self.videoWidget)
        self.mediaPlayer.setAudioOutput(self.audioOutput)
        
        self.start_time = None
        self.all_tags = []
        self.prompt_widgets = {}

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        master_layout = QVBoxLayout(central_widget)

        # TOP SPLIT
        top_layout = QHBoxLayout()
        
        # Player Area
        player_layout = QVBoxLayout()
        self.video_container = QFrame()
        self.video_container.setStyleSheet("background: #000; border-radius: 8px;")
        v_box = QVBoxLayout(self.video_container)
        v_box.addWidget(self.videoWidget)
        player_layout.addWidget(self.video_container, stretch=5)
        
        self.slider = StripedSlider(Qt.Orientation.Horizontal)
        player_layout.addWidget(self.slider)
        
        self.playBtn = QPushButton("Play / Pause")
        self.playBtn.setObjectName("PrimaryBtn")
        self.playBtn.clicked.connect(self.toggle_playback)
        player_layout.addWidget(self.playBtn)

        # Sidebar Area
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(15, 0, 15, 0)
        
        open_btn = QPushButton("📁 Load Video Recording")
        open_btn.clicked.connect(self.open_file_dialog)
        sidebar.addWidget(open_btn)
        
        sidebar.addWidget(QLabel("<br><b>TAG CATEGORIES</b>"))
        self.check_boxes = {}
        for cat in COLORS.keys():
            cb = QCheckBox(cat)
            cb.setObjectName(cat) # Used for the stylesheet colors
            cb.stateChanged.connect(self.refresh_prompts)
            self.check_boxes[cat] = cb
            sidebar.addWidget(cb)
        
        self.markStartBtn = QPushButton("⏱ Mark Start Time")
        self.markStartBtn.clicked.connect(self.set_start)
        sidebar.addWidget(self.markStartBtn)
        
        sidebar.addWidget(QLabel("<br><b>CLINICAL PROMPTS</b>"))
        self.prompt_container = QWidget()
        self.prompt_layout = QFormLayout(self.prompt_container)
        sidebar.addWidget(self.prompt_container)
        
        self.saveTagBtn = QPushButton("✅ Save Full Entry")
        self.saveTagBtn.setObjectName("PrimaryBtn")
        self.saveTagBtn.clicked.connect(self.save_interval)
        sidebar.addWidget(self.saveTagBtn)
        sidebar.addStretch()

        top_layout.addLayout(player_layout, stretch=2)
        top_layout.addLayout(sidebar, stretch=1)

        # Bottom Area
        self.tagLog = QListWidget()
        footer = QHBoxLayout()
        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_to_csv)
        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("ExitBtn")
        exit_btn.clicked.connect(self.close)
        
        footer.addWidget(export_btn)
        footer.addStretch()
        footer.addWidget(exit_btn)

        master_layout.addLayout(top_layout, stretch=4)
        master_layout.addWidget(QLabel("<b>SESSION LOG</b>"))
        master_layout.addWidget(self.tagLog, stretch=1)
        master_layout.addLayout(footer)

        self.mediaPlayer.positionChanged.connect(self.update_slider)
        self.mediaPlayer.durationChanged.connect(self.update_duration)

    def refresh_prompts(self):
        from PyQt6.QtWidgets import QCheckBox
        # Questions mapping
        q_map = {
            "Management": ["Room setup notes:", "Safety concerns?"],
            "Therapeutic": ["Technique used:", "Client outcome?"],
            "Rapport": ["Engagement level:", "Praise used?"],
            "Other": ["General notes:"]
        }
        
        for i in reversed(range(self.prompt_layout.count())): 
            self.prompt_layout.itemAt(i).widget().setParent(None)
        self.prompt_widgets.clear()
        
        for cat, cb in self.check_boxes.items():
            if cb.isChecked():
                for q in q_map[cat]:
                    le = QLineEdit()
                    self.prompt_layout.addRow(QLabel(q), le)
                    self.prompt_widgets[f"{cat}_{q}"] = le

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Recording", "", "Videos (*.mp4 *.mov *.avi)")
        if path: self.mediaPlayer.setSource(QUrl.fromLocalFile(path))

    def toggle_playback(self):
        if self.mediaPlayer.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.mediaPlayer.pause()
        else: self.mediaPlayer.play()

    def set_start(self):
        self.start_time = self.mediaPlayer.position()
        self.markStartBtn.setText(f"In-Point: {self.start_time // 1000}s")

    def save_interval(self):
        if self.start_time is None: return
        selected = [c for c, cb in self.check_boxes.items() if cb.isChecked()]
        if not selected: return

        tag = {
            "Categories": selected,
            "Start": self.start_time,
            "End": self.mediaPlayer.position(),
            "Prompts": {k: v.text() for k, v in self.prompt_widgets.items()}
        }
        self.all_tags.append(tag)
        self.slider.tags = self.all_tags
        self.slider.update()
        self.tagLog.addItem(f"[{', '.join(selected)}] {tag['Start']//1000}s - {tag['End']//1000}s")
        
        # Reset
        self.start_time = None
        self.markStartBtn.setText("⏱ Mark Start Time")
        for cb in self.check_boxes.values(): cb.setChecked(False)

    def export_to_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV Files (*.csv)")
        if path:
            with open(path, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(["Start_ms", "End_ms", "Categories", "Responses"])
                for t in self.all_tags:
                    w.writerow([t['Start'], t['End'], "|".join(t['Categories']), str(t['Prompts'])])

    def update_slider(self, pos): self.slider.setValue(pos)
    def update_duration(self, dur): self.slider.setRange(0, dur)
    def set_position(self, pos): self.mediaPlayer.setPosition(pos)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoTagger()
    window.show()
    sys.exit(app.exec())