import os
import sys

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt5.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

from PyQt5 import QtWebEngine
QtWebEngine.QtWebEngine.initialize()

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QFileDialog, QTextEdit, QWidget, QMessageBox, QSizePolicy
)
from PyQt5.QtGui import QPalette, QColor, QTextCursor, QFont, QIcon, QLinearGradient, QBrush
from Bio import SeqIO
from io import StringIO
from blast import BlastWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoMod - Home")
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(QIcon("D:/Shreya_VS_projects/Modeller_automation/Images/Screenshot 2025-11-09 171245.png"))
        self.initUI()

    def initUI(self):
        # --- Central Widget ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # --- Main Layout ---
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.setSpacing(40)

        # --- Title ---
        title = QLabel()
        title.setText(
            """
            <div style= " line-height :1.0;" >
            <span style="font-family:\'Source Sans Pro\'; font-size:28pt; font-weight:700; color:#924511;">AutoMod</span><br>
            <span style="font-family:\'Segoe UI\'; font-size:14pt; color:#825e34;"><i>Automated Comparative Modelling. Simplified.</i></span>
            </div>
            """
        )
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setWordWrap(True)
        layout.addWidget(title)


        

        # --- FASTA Section ---
        fasta_layout = QVBoxLayout()
        fasta_label = QLabel("Enter or Upload your FASTA Sequence:")
        fasta_label.setFont(QFont("Segoe UI", 14, QFont.Medium))
        fasta_label.setStyleSheet("color: #4a4e69; line-height: 1.0;")
        fasta_layout.addWidget(fasta_label)

        self.text_fasta = QTextEdit()
        self.text_fasta.setAcceptRichText(False)
        self.text_fasta.setPlaceholderText("Paste FASTA sequence here...")
        self.text_fasta.setFont(QFont("Sans Serif", 12))
        self.text_fasta.setStyleSheet("""
            QTextEdit {
                background-color: #f2e9e4;
                color: #22223b;
                border: 2px #22223b ;
                border-radius: 10px;
                padding: 10px;
            }
            QTextEdit:focus {
                border: 2px  #22223b;
                background-color: #f2e9e4;
            }
        """)
        self.text_fasta.setMinimumHeight(250)
        fasta_layout.addWidget(self.text_fasta)
        layout.addLayout(fasta_layout)

        # --- Buttons Layout ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(25)
        button_layout.setAlignment(Qt.AlignCenter)

        def styled_button(text, color1, color2):
            btn = QPushButton(text)
            btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(48)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color1};
                    color: white;
                    border-radius: 10px;
                    padding: 10px 18px;
                }}
                QPushButton:pressed {{
                    background-color: {color2};
                }}
            """)
            return btn

        # Buttons
        upload_button = styled_button("Upload FASTA", "#9a8c98", "#d1495b")
        upload_button.clicked.connect(self.upload_fasta)

        submit_button = styled_button("Submit Query", "#9a8c98", "#d1495b")
        submit_button.clicked.connect(self.submit_fasta)

        download_button = styled_button("*Download .PIR", "#9a8c98", "#d1495b")
        download_button.clicked.connect(self.download_ali)

        button_layout.addWidget(upload_button)
        button_layout.addWidget(submit_button)
        button_layout.addWidget(download_button)
        layout.addLayout(button_layout)

        # --- Background Gradient ---
        palette = QPalette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#d6ccc2"))
        gradient.setColorAt(1.0, QColor("#f5ebe0"))
        palette.setBrush(QPalette.Window, QBrush(gradient))
        self.setAutoFillBackground(True)
        self.setPalette(palette)

    # --- Functions ---
    def upload_fasta(self):
        options = QFileDialog.Options()
        filepath, _ = QFileDialog.getOpenFileName(self,
                                                   "Open FASTA File", 
                                                  " ", 
                                                  "FASTA Files (*.fasta)",
                                                    options=options)
        if not filepath:
            print("No file selected.")
            return
        print(f"Selected file: {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
                self.text_fasta.setPlainText(content)
        except Exception as e:
            QMessageBox.warning(self, f'Error! Failed to read the file : {e}')
    def submit_fasta(self):
        fasta_content = self.text_fasta.toPlainText()
        if fasta_content.strip():
            try:
                fasta_records = list(SeqIO.parse(StringIO(fasta_content), "fasta"))
                if fasta_records:
                    self.open_blast_window()
                else:
                    QMessageBox.warning(self, "Invalid", "No valid FASTA records found.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to parse FASTA: {e}")
        else:
            QMessageBox.warning(self, "Empty Input", "Please paste or upload a FASTA sequence first.")

    def fasta_to_pir(self):
        from collections import defaultdict
        import re

        fasta_text = self.text_fasta.toPlainText().strip()
        if not fasta_text:
            return None

        lines = fasta_text.splitlines()
        pir_lines, seq, name_counts = [], [], defaultdict(int)
        seq_name = None

        def make_short_code(header):
            token = header.split("|")[-1].split()[0]
            token = token.split("_")[0]
            code = re.sub(r"[^A-Za-z0-9_]", "_", token.upper() or "SEQ")
            return code

        for line in lines:
            if line.startswith(">"):
                if seq_name and seq:
                    name_counts[seq_name] += 1
                    unique_name = f"{seq_name}_{name_counts[seq_name]}" if name_counts[seq_name] > 1 else seq_name
                    pir_lines.append(f">P1;{unique_name}")
                    pir_lines.append(f"sequence:{unique_name}:::::::0.00:0.00")
                    pir_lines.append("".join(seq) + "*")
                    seq = []
                seq_name = make_short_code(line[1:])
            else:
                seq.append(line.strip())

        if seq_name and seq:
            name_counts[seq_name] += 1
            unique_name = f"{seq_name}_{name_counts[seq_name]}" if name_counts[seq_name] > 1 else seq_name
            pir_lines.append(f">P1;{unique_name}")
            pir_lines.append(f"sequence:{unique_name}:::::::0.00:0.00")
            pir_lines.append("".join(seq) + "*")

        return "\n".join(pir_lines)

    def download_ali(self):
        pir_text = self.fasta_to_pir()
        if pir_text:
            options = QFileDialog.Options()
            filename, _ = QFileDialog.getSaveFileName(self, "Save PIR File", "target.ali", "PIR Files (*.ali)")
            if filename:
                with open(filename, "w") as f:
                    f.write(pir_text)
                QMessageBox.information(self, "Success", "Target file (PIR) saved successfully.")
        else:
            QMessageBox.warning(self, "No Target", "Please upload or paste a FASTA sequence first.")

    def open_blast_window(self):
        fasta_sequence = self.text_fasta.toPlainText()
        self.blast_window = BlastWindow(fasta_sequence)
        self.blast_window.show()
        self.close()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
