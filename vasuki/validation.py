
import sys
import os
import csv
import subprocess
import shutil

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QTextEdit, QVBoxLayout, QHBoxLayout, QCheckBox,
    QMessageBox, QFrame, QLineEdit, QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QFont, QPalette, QBrush, QColor, QLinearGradient, QTextCursor, QIcon
import html
from .chatmodel import Chatbot

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')



# ramplot 1.0.x crashes (UnboundLocalError) for a model that has NO disallowed residues in the
# "standard" statistics: it forgets to define the counter in that branch. Excellent models
# (e.g. relaxed ones) can hit this, so we run ramplot through this small wrapper, which defines
# the missing counter in memory (the installed library is not modified) and then calls the same
# function the ramplot command line calls, with the same arguments.
_RAMPLOT_RUNNER = r"""
import sys, re, importlib.util
inp, out = sys.argv[1], sys.argv[2]
spec = importlib.util.find_spec("ramplot.ramplot")
src = open(spec.origin, encoding="utf-8", newline="").read()
src = re.sub(r"([ \t]+)ResidueDisallowedRegionStd=0",
             r"\1CountResidueDisallowedRegionStd=0\n\1ResidueDisallowedRegionStd=0", src)
ns = {"__name__": "ramplot_patched", "__file__": spec.origin, "__package__": "ramplot"}
exec(compile(src, spec.origin, "exec"), ns)
ns["TorsionAngleCalculation"](inp, out, "0", "600", "png")
"""


class RamPlotWorker(QThread):
    finished = pyqtSignal(dict, list)
    error = pyqtSignal(str)

    def __init__(self, input_dir, output_dir, files=None):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.files = files

    def run(self):
        try:
            summary, plots = self.run_per_model()
            self.finished.emit(summary, plots)
        except Exception as e:
            self.error.emit(str(e))

    def run_per_model(self):
        """Run ramplot separately on every PDB so each model gets its own
        statistics (a single run on a folder pools all PDBs together)."""
        os.makedirs(self.output_dir, exist_ok=True)
        if self.files:
            # exactly the models handed over by Model Building (raw + relaxed)
            pdbs = sorted(os.path.basename(f) for f in self.files
                          if f.lower().endswith(".pdb")
                          and os.path.exists(os.path.join(self.input_dir, os.path.basename(f))))
        else:
            pdbs = sorted(f for f in os.listdir(self.input_dir)
                          if f.lower().endswith(".pdb"))
        if not pdbs:
            raise RuntimeError("No .pdb files found in the input folder.")

        summary, plots = {}, []
        for pdb in pdbs:
            name = os.path.splitext(pdb)[0]
            tmp_in = os.path.join(self.output_dir, f"_in_{name}")
            out = os.path.join(self.output_dir, f"ram_{name}")
            os.makedirs(tmp_in, exist_ok=True)
            shutil.copy(os.path.join(self.input_dir, pdb), tmp_in)

            csv_path = os.path.join(out, "Analysis.csv")
            err = ""
            attempts = (
                [sys.executable, "-c", _RAMPLOT_RUNNER, tmp_in, out],
                ["ramplot", "pdb", "-i", tmp_in, "-m", "0", "-r", "600", "-p", "png", "-o", out],
            )
            for cmd in attempts:
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True)
                except OSError as e:
                    err = str(e)
                    continue
                if proc.returncode == 0 and os.path.exists(csv_path):
                    err = ""
                    break
                lines = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
                err = lines[-1] if lines else "ramplot failed"
            shutil.rmtree(tmp_in, ignore_errors=True)

            if err or not os.path.exists(csv_path):
                summary[name] = {"total": "NA", "favoured": "NA", "allowed": "NA",
                                 "disallowed": "NA", "note": f"ramplot failed: {err}"}
                continue

            summary[name] = self.parse_analysis(csv_path)
            plot_dir = os.path.join(out, "Plots")
            if os.path.isdir(plot_dir):
                plots += [os.path.join(plot_dir, f)
                          for f in sorted(os.listdir(plot_dir)) if f.endswith(".png")]
        return summary, plots

    def parse_analysis(self, csv_path):
        """Read the six-category Ramachandran statistics (glycine/proline
        handled separately, comparable to MolProbity)."""
        s = {"total": "NA", "favoured": "NA", "allowed": "NA", "disallowed": "NA"}
        section = None
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                key = row[0].lower()
                if "total residue" in key:
                    s["total"] = row[1]
                elif "(standard)" in key:
                    section = "standard"
                elif "six categories" in key:
                    section = "six"
                elif section == "six" and len(row) >= 3:
                    val = f"{row[1].strip()} ({row[2].strip().strip(chr(40)+chr(41))})"
                    if key.startswith("favoured"):
                        s["favoured"] = val
                    elif key.startswith("allowed"):
                        s["allowed"] = val
                    elif key.startswith("disallowed"):
                        s["disallowed"] = val
        return s


class SquareImage(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setMinimumSize(200, 200)

        self._original_pixmap = None
        self._last_size = None

    def set_image(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return

        self._original_pixmap = pixmap
        self._last_size = None
        self._update_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self):
        if self._original_pixmap is None:
            return

        size = self.size()
        if size == self._last_size:
            return 

        self._last_size = size

        side = min(size.width(), size.height())
        if side <= 0:
            return

        scaled = self._original_pixmap.scaled(
            side,
            side,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        QLabel.setPixmap(self, scaled)


# =========================
# Main GUI
# =========================
class RamPlotGUI(QMainWindow):
    def __init__(self, input_dir=None, files=None):
        super().__init__()
        self.setWindowTitle("Ramachandran Plot Analysis")
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
        self.resize(1400, 850)
        self.showMaximized()

        try:
            self.chatbot = Chatbot()
        except Exception as e:
            print(f"Chatbot initialization failed: {e}")
            self.chatbot = None
        self.plots = []
        self.plot_index = 0
        self.analysis = {}
        self.input_dir = None
        self.output_dir = None
        self.model_files = list(files) if files else None

        self.build_ui()

        # Models handed over by Model Building: validate them straight away
        if input_dir and os.path.isdir(input_dir):
            self.input_dir = input_dir
            self.output_dir = input_dir
            n = len(self.model_files) if self.model_files else sum(
                1 for f in os.listdir(input_dir) if f.lower().endswith(".pdb"))
            self.analysis_box.setText(
                f"Received {n} model(s) from Model Building. "
                "Running Ramachandran analysis...")
            QTimer.singleShot(300, self.run)

    def build_ui(self):

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        
        title = QLabel("Ramachandran 2D/3D Plot Analysis")
        title.setFont(QFont("Source Sans Pro", 20, QFont.Medium))
        title.setStyleSheet("color: #924511;")
        title.setAlignment(Qt.AlignLeft)
        self.main_layout.addWidget(title)
        self.main_layout.setStretchFactor(title, 0)

        palette = QPalette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#d6ccc2"))
        gradient.setColorAt(1.0, QColor("#f5ebe0"))
        palette.setBrush(QPalette.Window, QBrush(gradient))
        self.setAutoFillBackground(True)
        self.setPalette(palette)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ddd; }")

        left_frame = QFrame()
        left_label = QLabel('Controls')
        left_label.setFont(QFont("Segoe UI", 14))
        left_label.setAlignment(Qt.AlignLeft)
        left_frame.setFrameShape(QFrame.StyledPanel)
        left_frame.setMidLineWidth(300)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setSpacing(20)
        left_layout.addWidget(left_label)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(20)
        button_layout.setAlignment(Qt.AlignLeft)

        def styled_button(text, color1, color2):
            btn = QPushButton(text)
            btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(45)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color1};
                    color: white;
                    border-radius: 8px;
                    padding: 10px 18px;
                    
                }}
                QPushButton:pressed {{
                    background-color: {color2};
                }}
            """)
            return btn 

        input_button = styled_button("Select Model Folder", "#9a8c98", "#d1495b")
        input_button.clicked.connect(self.select_input)
        button_layout.addWidget(input_button)

        self.checkbox = QCheckBox("Same as Input Path")
        self.checkbox.setChecked(True)
        self.checkbox.setFont(QFont("Segoe UI", 10))
        self.checkbox.stateChanged.connect(self.toggle_output_mode)
        button_layout.addWidget(self.checkbox)

        self.output_button = styled_button("Select Output Folder", "#9a8c98", "#d1495b")
        self.output_button.setEnabled(False)
        self.output_button.setStyleSheet(
            "background-color: #9a8c98; color: white; padding: 10px; border-radius: 6px;"
        )
        self.output_button.clicked.connect(self.select_output_folder)
        button_layout.addWidget(self.output_button)

        run_button = styled_button("Generate Plots", "#62929e", "#c6c5b9")
        run_button.clicked.connect(self.run)
        button_layout.addWidget(run_button)

        left_layout.addLayout(button_layout)
        left_layout.addStretch()
        splitter.addWidget(left_frame)

        center_splitter = QSplitter(Qt.Vertical)
        center_splitter.setStyleSheet("QSplitter::handle { background-color: #ddd; }")
        center_splitter.setSizes([600, 350])
        
        plot_label = QLabel("Ramachandran Plots")
        plot_label.setFont(QFont("Segoe UI", 12))

        plot_label.setAlignment(Qt.AlignLeft)
        plot_frame = QFrame()
        plot_frame.setFrameShape(QFrame.StyledPanel)
        plot_frame.setStyleSheet("""
            background-color: #f2e9e4;
                color: #22223b;
                border: 2px #22223b;
                border-radius: 10px;
                padding: 10px;
        """)
        plot_layout = QVBoxLayout(plot_frame)
        plot_layout.addWidget(plot_label)
        plot_layout.setContentsMargins(10, 10, 10, 10)

        self.plot_box = SquareImage()
        self.plot_box.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        center_splitter.setStretchFactor(0, 3)
        plot_layout.addWidget(self.plot_box)

        nav_layout = QHBoxLayout()
        prev_button = styled_button("◀ Previous", "#db7f8e", "#ffdbda")
        next_button = styled_button("▶ Next", "#db7f8e", "#ffdbda")
        prev_button.clicked.connect(self.prev_plot)
        next_button.clicked.connect(self.next_plot) 
        nav_layout.addWidget(prev_button)
        nav_layout.addWidget(next_button)   
        plot_layout.addLayout(nav_layout)
        
        center_splitter.addWidget(plot_frame)

        # ========= ANALYSIS FRAME =========
        analysis_frame = QFrame()
        analysis_frame.setFrameShape(QFrame.StyledPanel)
        analysis_layout = QVBoxLayout(analysis_frame)
        
        analysis_label = QLabel("Analysis Results")
        analysis_label.setFont(QFont("Segoe UI", 12))
        analysis_label.setStyleSheet("color: #4a4e69;")
        analysis_label.setAlignment(Qt.AlignLeft)
        analysis_layout.addWidget(analysis_label)

        self.analysis_box = QTextEdit()
        self.analysis_box.setReadOnly(True)
        self.analysis_box.setFont(QFont("Segoe UI", 12))
        analysis_layout.addWidget(self.analysis_box)
        center_splitter.setStretchFactor(1, 2)
        center_splitter.addWidget(analysis_frame)

        # Add the center splitter to the main horizontal splitter so it is visible
        splitter.addWidget(center_splitter)

        right_frame = QFrame()
        right_frame.setFrameShape(QFrame.StyledPanel)
        right_frame.setMinimumWidth(200)
        right_layout = QVBoxLayout(right_frame)

        # ChatBot
        chatbot_label = QLabel("Modssitant")
        chatbot_label.setFont(QFont("Segoe UI", 14, QFont.Medium))
        chatbot_label.setStyleSheet("color: #4a4e69; line-height: 1.0;")
        chatbot_label.setAlignment(Qt.AlignLeft)
        right_layout.addWidget(chatbot_label)

        self.chattext = QTextEdit()
        self.chattext.setReadOnly(True)
        self.chattext.setPlaceholderText("Ask about model quality...")
        self.chattext.setFont(QFont("Segoe UI", 11))
        right_layout.addWidget(self.chattext)

        # Chat Input 
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("How can I assist you?")
        self.chat_input.setFont(QFont("Segoe UI", 11))
        self.chat_input.setMinimumHeight(40)

        self.chat_input.returnPressed.connect(self.ask)
        input_layout.addWidget(self.chat_input)

        send_btn = QPushButton()
        send_btn = styled_button("Send", "#9a8c98", "#d1495b")
        send_btn.clicked.connect(self.ask)
        input_layout.addWidget(send_btn)

        right_layout.addLayout(input_layout)
        splitter.addWidget(right_frame)

        splitter.setSizes([200, 900, 350])
        self.main_layout.addWidget(splitter)
        self.main_layout.setStretchFactor(splitter, 1)



    # =========================
    # Actions
    # =========================

    def toggle_output_mode(self):
        if self.checkbox.isChecked():
            self.output_button.setEnabled(False)
            self.output_dir = getattr(self, "input_dir", None)
        else:
            self.output_button.setEnabled(True)

    def select_input(self):
        folder = QFileDialog.getExistingDirectory(self)
        if not folder:
            return
        self.input_dir = folder
        self.model_files = None          # a manually chosen folder = all its .pdb files
        # Initialize output_dir based on checkbox state
        if self.checkbox.isChecked():
            self.output_dir = self.input_dir

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self)
        if folder:
            self.output_dir = folder

    def select_output(self):
        if hasattr(self, "checkbox") and self.checkbox.isChecked():
            self.output_dir = self.input_dir
            self.output_button.setEnabled(False)
        else:
            self.output_button.setEnabled(True)
            self.output_dir = QFileDialog.getExistingDirectory(self)


    def run(self):
        self.analysis_box.setText("Running Ramachandran plot analysis...")
        if not hasattr(self, "input_dir") or not self.input_dir:
            QMessageBox.warning(self, "Error", "Select input folder")
            return
        
        if not hasattr(self, "output_dir") or not self.output_dir:
            QMessageBox.warning(self, "Error", "Select output folder or check 'Same as Input Path'")
            return

        self.worker = RamPlotWorker(self.input_dir, self.output_dir, self.model_files)
        self.worker.finished.connect(self.display)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self.worker.start()

    def display(self, summary, plots):
        self.analysis = summary
        self.plots = plots
        self.plot_index = 0

        lines = []
        for name, s in summary.items():
            if s.get("note"):
                lines.append(f"{name}: {s['note']}")
            else:
                lines.append(
                    f"{name}: {s['total']} res | Favoured {s['favoured']} | "
                    f"Allowed {s['allowed']} | Disallowed {s['disallowed']}")
        self.analysis_text = "\n".join(lines)
        self.analysis_box.setText(
            "Ramachandran Analysis (six-category, per model)\n\n" + self.analysis_text)

        if plots:
            self.plot_box.set_image(plots[0])

    def next_plot(self):
        if self.plots:
            self.plot_index = (self.plot_index + 1) % len(self.plots)
            self.plot_box.set_image(self.plots[self.plot_index])

    def prev_plot(self):
        if self.plots:
            self.plot_index = (self.plot_index - 1) % len(self.plots)
            self.plot_box.set_image(self.plots[self.plot_index])

    def ask(self):

        user_msg = self.chat_input.text().strip()
        if not user_msg:
            return
        
        # User message (Researcher)
        user_html = f"""
        <div style="
            margin: 8px 0 14px 0;
            color: #c77dff;
            font-weight: 600;
            font-family: Segoe UI;
            font-size: 11pt;
        ">
            Modeler:
            <span style="
                font-weight: 400;
                color: #000000;
            ">
                {user_msg}
            </span>
        </div>
        """
        self.chattext.append(user_html)
        self.chat_input.clear()

        # Generate and append bot response
        if not self.chatbot:
            self.chattext.append("<span style='color:red;'>Vasuki: Chatbot is disabled. </span>")
            return

        try:
            response = self.chatbot.generate_ramachandran_response(
                question=user_msg,
                analysis_text=getattr(self, "analysis_text", "")
            )

            bot_html = f"""
            <div style="
                margin: 0 0 18px 0;
                color: #7b2cbf;
                font-weight: 600;
                font-family: Segoe UI;
                font-size: 11pt;
            ">
                Vasuki:
                <span style="
                    font-weight: 400;
                    color: #222222;
                ">
                    {html.escape(response).replace(chr(10), "<br>")}
                </span>
            </div>
            """
            self.chattext.append(bot_html)

        except Exception as e:
            self.chattext.append(
                f"<span style='color:red;'>Vasuki: Error generating response: {e}</span>"
            )

        # Scroll to end
        self.chattext.moveCursor(QTextCursor.End)
        self.chattext.ensureCursorVisible()
        # self.chat_input.clear()


# =========================
# Entry
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = RamPlotGUI()
    gui.show()
    sys.exit(app.exec_())