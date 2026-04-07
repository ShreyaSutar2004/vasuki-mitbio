
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QStatusBar,
    QFileDialog, QTextEdit, QWidget, QMessageBox, QSizePolicy
)
from PyQt5.QtGui import QPalette, QColor, QTextCursor, QFont, QIcon, QLinearGradient, QBrush, QPixmap
from PyQt5.QtCore import Qt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')

class MainWindow(QMainWindow):
    def __init__(self, api_key=None):
        super().__init__()
        self.api_key = api_key
        self.setWindowTitle("Vasuki - Home")
        self.setMinimumSize(1500, 900)
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
        self.initUI()

    def initUI(self):
        # --- Central Widget ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # --- Main Layout ---
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.setSpacing(40)
        header_layout = QHBoxLayout()
        
        mitheader = QHBoxLayout()
        mitheader.setContentsMargins(0, 0, 0, 0)

        mitbio_logo = QLabel()
        mitbio_pixmap = QPixmap(os.path.join(IMAGE_DIR, "MIT_BIO_new_logo_clean.png"))
        mitbio_pixmap = mitbio_pixmap.scaled(250, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        mitbio_logo.setPixmap(mitbio_pixmap)
        mitbio_logo.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        mitheader.addWidget(mitbio_logo)
        

        mitadt_logo = QLabel()
        mitadt_pixmap = QPixmap(os.path.join(IMAGE_DIR, "MIT_ADT_new_logo_clean.png"))
        mitadt_pixmap = mitadt_pixmap.scaled(250, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        mitadt_logo.setPixmap(mitadt_pixmap)
        mitadt_logo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        mitheader.addWidget(mitadt_logo)

        layout.addLayout(mitheader)
        

        # Load the logo image
        logo = QLabel()
        pixmap = QPixmap(os.path.join(IMAGE_DIR, "image-removebg-preview.png"))
        pixmap = pixmap.scaled(340, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo.setPixmap(pixmap)
        logo.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        header_layout.addWidget(logo)

        # Title and subtitle in a vertical layout
        title = QLabel()
        title.setText("""
            <span style="font-family:'Source Sans Pro'; font-size:36pt; font-weight:800;letter-spacing:1.2px; color:#924511;">V A S U K I</span><br>
            <span style="font-family:'Source Sans Pro'; font-size:18pt; font-weight:400;letter-spacing:1.2px; color:#825e34;"><i>From Myth to Molecule</i></span>
        """)
        title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        title.setWordWrap(False)

        header_layout.addWidget(title)
        # center the header layout (logo + title) then nudge slightly left
        header_layout.setAlignment(Qt.AlignHCenter)
        # add extra right margin so the centered content shifts slightly left
        header_layout.setContentsMargins(0, 0, 350, 0)

        # Add the header layout (logo + title) to the main vertical layout
        layout.addLayout(header_layout)


        # --- FASTA Section ---
        fasta_layout = QVBoxLayout()
        # top row: label + sample link/button
        fasta_top = QHBoxLayout()
        fasta_label = QLabel("Enter or Upload your FASTA Sequence:")
        fasta_label.setFont(QFont("Poppins", 14, QFont.Medium))
        fasta_label.setStyleSheet("color: #4a4e69; line-height: 1.0;")
        fasta_top.addWidget(fasta_label)

        # sample button (styled like a link) to insert a beginner-friendly FASTA
        sample_button = QPushButton("Sample.fasta")
        sample_button.setCursor(Qt.PointingHandCursor)
        sample_button.setFlat(True)
        sample_button.setStyleSheet("color: #1a73e8; text-decoration: underline; background: transparent; border: none; font-size:20px;")
        fasta_top.addWidget(sample_button)
        fasta_top.addStretch()

        fasta_layout.addLayout(fasta_top)

        # sample FASTA text stored on the window for reuse
        self.sample_fasta_text = """>sp|P52790|HXK3_HUMAN Hexokinase-3 OS=Homo sapiens OX=9606 GN=HK3 PE=1 SV=2
MDSIGSSGLRQGEETLSCSEEGLPGPSDSSELVQECLQQFKVTRAQLQQIQASLLGSMEQ
ALRGQASPAPAVRMLPTYVGSTPHGTEQGDFVVLELGATGASLRVLWVTLTGIEGHRVEP
RSQEFVIPQEVMLGAGQQLFDFAAHCLSEFLDAQPVNKQGLQLGFSFSFPCHQTGLDRST
LISWTKGFRCSGVEGQDVVQLLRDAIRRQGAYNIDVVAVVNDTVGTMMGCEPGVRPCEVG
LVVDTGTNACYMEEARHVAVLDEDRGRVCVSVEWGSFSDDGALGPVLTTFDHTLDHESLN
PGAQRFEKMIGGLYLGELVRLVLAHLARCGVLFGGCTSPALLSQGSILLEHVAEMEDPST
GAARVHAILQDLGLSPGASDVELVQHVCAAVCTRAAQLCAAALAAVLSCLQHSREQQTLQ
VAVATGGRVCERHPRFCSVLQGTVMLLAPECDVSLIPSVDGGGRGVAMVTAVAARLAAHR
RLLEETLAPFRLNHDQLAAVQAQMRKAMAKGLRGEASSLRMLPTFVRATPDGSERGDFLA
LDLGGTNFRVLLVRVTTGVQITSEIYSIPETVAQGSGQQLFDHIVDCIVDFQQKQGLSGQ
SLPLGFTFSFPCRQLGLDQGILLNWTKGFKASDCEGQDVVSLLREAITRRQAVELNVVAI
VNDTVGTMMSCGYEDPRCEIGLIVGTGTNACYMEELRNVAGVPGDSGRMCINMEWGAFGD
DGSLAMLSTRFDASVDQASINPGKQRFEKMISGMYLGEIVRHILLHLTSLGVLFRGQQIQ
RLQTRDIFKTKFLSEIESDSLALRQVRAILEDLGLPLTSDDALMVLEVCQAVSQRAAQLC
GAGVAAVVEKIRENRGLEELAVSVGVDGTLYKLHPRFSSLVAATVRELAPRCVVTFLQSE
DGSGKGAALVTAVACRLAQLTRV"""

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

        # connect sample button to load sample FASTA into the text box
        def load_sample():
            try:
                self.text_fasta.setPlainText(self.sample_fasta_text)
                cursor = self.text_fasta.textCursor()
                cursor.movePosition(QTextCursor.Start)
                self.text_fasta.setTextCursor(cursor)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load sample FASTA: {e}")

        sample_button.clicked.connect(load_sample)
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

        

        # --- Footer Bar ---
        status_bar = QStatusBar()
        status_bar.setFixedHeight(45)
        status_bar.setStyleSheet("""
            QStatusBar {
                color: #4a4e69;
                padding: 6px;
            }
        """)

        footer_label = QLabel(
            "Designed & Developed by Ms.Shreya Sutar (B.Tech Bioengineering Sciences and Research) & Prof. Dr. K.V Swamy (School of Bioengineering Sciences and Research)"
            "| MIT Art Design and Technology University Pune India "
            "\n Reach out to us at: shreyasutar2018@gmail.com, venkateswara.swamy@mituniversity.edu.in"
        )
        footer_label.setStyleSheet("""
                                   color: #4a4e69; 
                                   font-size: 16px; 
                                   font-weight: Medium;
                                   font-family: 'Poppins';
                                   """)
        footer_label.setAlignment(Qt.AlignCenter)

        status_bar.addPermanentWidget(footer_label, 1)
        self.setStatusBar(status_bar)


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
        from Bio import SeqIO
        from io import StringIO
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
        from .blast import BlastWindow
        fasta_sequence = self.text_fasta.toPlainText()
        self.blast_window = BlastWindow(fasta_sequence)
        self.blast_window.show()
        self.close()
