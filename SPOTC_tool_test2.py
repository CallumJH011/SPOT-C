import sys, os
import vlc
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# ---------- CONFIG ----------
FPS = 30  # frame stepping
COLORS = {
    "Management": "#F3D97B",
    "Therapeutic": "#4A90E2",
    "Rapport": "#82CD47",
    "Other": "#D3D3D3"
}

def format_time(ms):
    s = ms / 1000
    m = int(s // 60)
    sec = int(s % 60)
    ms = int(ms % 1000)
    return f"{m:02}:{sec:02}.{ms:03}"

# ---------- TAG OBJECT ----------
class Tag:
    def __init__(self, start, end, categories):
        self.start = start
        self.end = end
        self.categories = categories

# ---------- MAIN WINDOW ----------
class VideoTagger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clinical Speech Annotation Tool")
        self.resize(1200, 800)

        # VLC player setup
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()

        self.tags = []
        self.start_time = None

        self.init_ui()
        self.setup_shortcuts()

    # ---------- UI ----------
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Video Frame
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background:black;")
        layout.addWidget(self.video_frame, 5)
        if sys.platform.startswith('darwin'):
            self.mediaplayer.set_nsobject(int(self.video_frame.winId()))
        else:
            self.mediaplayer.set_hwnd(int(self.video_frame.winId()))

        # Controls layout
        controls = QHBoxLayout()
        self.play_btn = QPushButton("Play/Pause")
        self.play_btn.clicked.connect(self.toggle_playback)
        controls.addWidget(self.play_btn)

        self.speed_box = QComboBox()
        self.speed_box.addItems(["0.5x","1x","1.5x","2x"])
        self.speed_box.currentTextChanged.connect(self.change_speed)
        controls.addWidget(QLabel("Speed:"))
        controls.addWidget(self.speed_box)

        load_btn = QPushButton("Load Video")
        load_btn.clicked.connect(self.load_video)
        controls.addWidget(load_btn)

        layout.addLayout(controls)

        # Category buttons
        cat_layout = QHBoxLayout()
        self.cat_btns = {}
        for name in COLORS:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet(f"background:{COLORS[name]}; padding:6px;")
            self.cat_btns[name] = btn
            cat_layout.addWidget(btn)
        layout.addLayout(cat_layout)

        # Tag buttons
        tag_layout = QHBoxLayout()
        self.start_btn = QPushButton("Mark Start")
        self.start_btn.clicked.connect(self.mark_start)
        save_btn = QPushButton("Save Tag")
        save_btn.clicked.connect(self.save_tag)
        tag_layout.addWidget(self.start_btn)
        tag_layout.addWidget(save_btn)
        layout.addLayout(tag_layout)

        # Log and stats
        self.log = QListWidget()
        self.log.itemDoubleClicked.connect(self.edit_tag)
        layout.addWidget(self.log)

        self.stats = QLabel("No tags yet")
        layout.addWidget(self.stats)

    # ---------- VIDEO CONTROLS ----------
    def load_video(self):
        path,_ = QFileDialog.getOpenFileName(self, "Open Video")
        if path:
            media = self.instance.media_new(path)
            self.mediaplayer.set_media(media)
            self.mediaplayer.play()
            QTimer.singleShot(100, self.mediaplayer.pause)  # pause immediately to update frame

    def toggle_playback(self):
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
        else:
            self.mediaplayer.play()

    def change_speed(self, val):
        rate = float(val.replace("x",""))
        self.mediaplayer.set_rate(rate)

    def get_time(self):
        return int(self.mediaplayer.get_time())  # in milliseconds

    def set_time(self, ms):
        self.mediaplayer.set_time(ms)

    # ---------- TAGGING ----------
    def mark_start(self):
        self.start_time = self.get_time()
        self.start_btn.setText(f"In: {format_time(self.start_time)}")

    def save_tag(self):
        if self.start_time is None:
            return
        end_time = self.get_time()
        cats = [name for name, b in self.cat_btns.items() if b.isChecked()]
        if not cats:
            return
        tag = Tag(self.start_time, end_time, cats)
        self.tags.append(tag)
        self.log.addItem(f"{cats} {format_time(tag.start)} → {format_time(tag.end)}")
        self.start_time = None
        self.start_btn.setText("Mark Start")
        for b in self.cat_btns.values():
            b.setChecked(False)
        self.update_stats()

    # ---------- TAG EDIT ----------
    def edit_tag(self, item):
        idx = self.log.row(item)
        tag = self.tags[idx]
        start, ok = QInputDialog.getInt(self, "Edit Start", "Start ms", tag.start)
        if ok: tag.start = start
        end, ok = QInputDialog.getInt(self, "Edit End", "End ms", tag.end)
        if ok: tag.end = end
        self.log.item(idx).setText(f"{tag.categories} {format_time(tag.start)} → {format_time(tag.end)}")
        self.update_stats()

    # ---------- SHORTCUTS ----------
    def setup_shortcuts(self):
        QShortcut(QKeySequence("Space"), self, self.toggle_playback)
        QShortcut(QKeySequence("Right"), self, self.frame_forward)
        QShortcut(QKeySequence("Left"), self, self.frame_back)
        QShortcut(QKeySequence("S"), self, self.mark_start)
        QShortcut(QKeySequence("E"), self, self.save_tag)

    # ---------- FRAME STEPPING ----------
    def frame_forward(self):
        self.set_time(self.get_time() + int(1000/FPS))
    def frame_back(self):
        self.set_time(self.get_time() - int(1000/FPS))

    # ---------- STATS ----------
    def update_stats(self):
        counts = {k:0 for k in COLORS}
        for t in self.tags:
            for c in t.categories:
                counts[c] += 1
        txt = " | ".join(f"{k}:{v}" for k,v in counts.items())
        self.stats.setText(txt)

# ---------- RUN ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = VideoTagger()
    w.show()
    sys.exit(app.exec())