import sys
import os
import csv
import subprocess
from turtle import color

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QTextEdit, QVBoxLayout, QHBoxLayout, QCheckBox,
    QMessageBox, QFrame, QLineEdit, QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont, QPalette, QBrush, QColor, QLinearGradient, QTextCursor, QIcon
from .chatmodel import Chatbot
from .config import get_api_key

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')


class RamPlotWorker(QThread):
    finished = pyqtSignal(dict, list)
    error = pyqtSignal(str)

    def __init__(self, input_dir, output_dir):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir

    def run(self):
        try:
            self.run_ramplot()
            summary = self.parse_analysis()
            plots = self.collect_plots()
            self.finished.emit(summary, plots)
        except Exception as e:
            self.error.emit(str(e))

    def run_ramplot(self):
        os.makedirs(self.output_dir, exist_ok=True)

        cmd = [
            "ramplot", "pdb",
            "-i", self.input_dir,
            "-m", "0",
            "-r", "600",
            "-p", "png",
            "-o", self.output_dir
        ]
        subprocess.run(cmd, check=True)

    def parse_analysis(self):
        summary = {
            "total": "NA",
            "favoured": "NA",
            "allowed": "NA",
            "disallowed": "NA"
        }

        csv_path = os.path.join(self.output_dir, "Analysis.csv")
        in_standard = False

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue

                key = row[0].lower()

                if "total residue" in key:
                    summary["total"] = row[1]

                elif "ramachandran plot (standard)" in key:
                    in_standard = True

                elif "six category" in key:
                    break

                elif in_standard and "favoured" in key and len(row) >= 3:
                    summary["favoured"] = f"{row[1].strip()} ({row[2].strip()})"


                elif in_standard and key.startswith("allowed") and len(row) >= 3:
                 summary["allowed"] = f"{row[1].strip()} ({row[2].strip()})"

                elif in_standard and "disallowed" in key and len(row) >= 3:
                    summary["disallowed"] = f"{row[1].strip()} ({row[2].strip()})"

        return summary

    def collect_plots(self):
        plot_dir = os.path.join(self.output_dir, "Plots")
        return [
            os.path.join(plot_dir, f)
            for f in sorted(os.listdir(plot_dir))
            if f.endswith(".png")
        ]


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ramachandran Plot Analysis")
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
        self.resize(1400, 850)
        self.showMaximized()

        token = get_api_key()
        try:
            self.chatbot = Chatbot(token=token)
        except Exception as e:
            print(f"Chatbot disabled: {e}")
            self.chatbot = None
        self.plots = []
        self.plot_index = 0
        self.analysis = {}
        self.input_dir = None
        self.output_dir = None

        self.build_ui()

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
        self.input_dir = QFileDialog.getExistingDirectory(self)
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

        self.worker = RamPlotWorker(self.input_dir, self.output_dir)
        self.worker.finished.connect(self.display)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self.worker.start()

    def display(self, summary, plots):
        self.analysis = summary
        self.plots = plots
        self.plot_index = 0

        self.analysis_box.setText(
            f"Ramachandran Plot Analysis\n\n"
            f"Total Residues: {summary['total']}\n"
            f"Favoured: {summary['favoured']}\n"
            f"Allowed: {summary['allowed']}\n"
            f"Disallowed: {summary['disallowed']}"
        )

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
        
        prompt = f"""
        You are an expert in protein structure validation.

        Ramachandran statistics:
        Total residues: {self.analysis.get('total')}
        Favoured: {self.analysis.get('favoured')}
        Allowed: {self.analysis.get('allowed')}
        Disallowed: {self.analysis.get('disallowed')}

        If the user asks queries, provide concise and informative answers in 3-4 lines. 
        Question: {user_msg}
        """

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
            self.chattext.append("<span style='color:red;'>Vasuki: Chatbot is disabled. Please set your Hugging Face API token.</span>")
            return

        try:
            response = self.chatbot._llm_response(prompt)

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
                    {response}
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
        self.chat_input.clear()


# =========================
# Entry
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = RamPlotGUI()
    gui.show()
    sys.exit(app.exec_())