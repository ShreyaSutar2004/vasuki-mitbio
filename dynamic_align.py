from modeller import Environ, Model, Alignment
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QFileDialog, QTextEdit, QWidget, QMessageBox, QGroupBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
    QToolBar, QAction, QSplitter, QSizePolicy, QFrame
)
from PyQt5.QtGui import QFont, QIcon, QPalette, QLinearGradient, QColor, QBrush
from PyQt5.QtCore import Qt, QSize
import sys, os, requests


class DynamicAlign(QMainWindow):
    def __init__(self, selected_templates=None):
        super().__init__()
        self.setWindowTitle('Modeller — Dynamic Alignment')
        self.setMinimumSize(1200, 720)
        self.setWindowIcon(QIcon("D:/Shreya_VS_projects/Modeller_automation/Images/Screenshot 2025-11-09 171245.png"))
        self.selected_templates = selected_templates or []
        self.uploaded_file = None
        self.upload_path = None
        self.initUI()


    def initUI(self):

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        # Title
        title = QLabel()
        title.setText("""
         <span style="font-family:'Source Sans Pro'; font-size:20pt; font-weight:400; color:#924511;">Dynamic Alignment</span><br>
                            """)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setWordWrap(True)
        title.setFixedHeight(60)
        self.main_layout.addWidget(title)
        self.main_layout.setStretchFactor(title, 0)

        # Background Palette
        palette = QPalette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#d6ccc2"))
        gradient.setColorAt(1.0, QColor("#f5ebe0"))
        palette.setBrush(QPalette.Window, QBrush(gradient))
        self.setAutoFillBackground(True)
        self.setPalette(palette)
       
       # Horizontal Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ddd; }")

        # Left Panel: Controls
        left_frame = QFrame()
        left_label = QLabel('Controls')
        left_label.setFont(QFont("Segoe UI", 14, QFont.Medium))
        left_label.setAlignment(Qt.AlignLeft)
        left_frame.setFrameShape(QFrame.StyledPanel)
        left_frame.setMidLineWidth(300)
        left_layout = QVBoxLayout(left_frame)
        left_layout.addWidget(left_label)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(20)
        button_layout.setAlignment(Qt.AlignLeft)

        def styled_button(text, color1, color2):
            btn = QPushButton(text)
            btn.setFont(QFont("Segoe UI", 10))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(45)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color1};
                    color: white;
                    padding: 10px 18px;
                    
                }}
                QPushButton:pressed {{
                    background-color: {color2};
                }}
            """)
            return btn 
        
        btn_open = styled_button("Browse FASTA / .ali", "#9a8c98", "#d1495b")
        btn_open.clicked.connect(self.open_fasta)
        button_layout.addWidget(btn_open)

        btn_pdb = styled_button("Import Local PDBs", "#9a8c98", "#d1495b")
        btn_pdb.clicked.connect(self.import_pdbs)
        button_layout.addWidget(btn_pdb)

        button_layout.addSpacing(20)

        self.align_btn = styled_button("Run Alignment", "#2e7d32", "#1b5e20")
        self.align_btn.clicked.connect(self.do_align)
        self.align_btn.setEnabled(False)
        button_layout.addWidget(self.align_btn)

        self.download_btn = styled_button("Download .ali", "#f57c00", "#ef6c00")
        self.download_btn.clicked.connect(self.download_ali)
        self.download_btn.setEnabled(False)
        button_layout.addWidget(self.download_btn)

        self.nextbtn = styled_button("Model Building", "#1565c0", "#0d47a1")
        self.nextbtn.clicked.connect(self.open_nextpage)
        button_layout.addWidget(self.nextbtn)

        left_layout.addLayout(button_layout)
        left_layout.addStretch()
        splitter.addWidget(left_frame)

        # Center Panel: Vertical Splitter for Preview and Messages
        center_splitter = QSplitter(Qt.Vertical)
        center_splitter.setStyleSheet("QSplitter::handle { background-color: #ddd; }")

        # Preview Section
        preview_box = QGroupBox("Uploaded File Preview")
        pv_layout = QVBoxLayout(preview_box)
        pv_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFont(QFont("Consolas", 10))
        self.preview_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f2e9e4;
                color: #22223b;
                border: 2px #22223b;
                border-radius: 10px;
                padding: 10px;
            }
            QTextEdit:focus {
                border: 2px #22223b;
                background-color: #f2e9e4;
            }
        """)
        pv_layout.addWidget(self.preview_edit)
        center_splitter.addWidget(preview_box)

        # Messages/Output Section
        output_box = QGroupBox("Alignment / Messages")
        out_layout = QVBoxLayout(output_box)
        self.msg_edit = QTextEdit()
        self.msg_edit.setReadOnly(True)
        self.msg_edit.setFont(QFont("Consolas", 10))
        self.msg_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.msg_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f2e9e4;
                color: #22223b;
                border: 2px #22223b;
                border-radius: 10px;
                padding: 10px;
            }
            QTextEdit:focus {
                border: 2px #22223b;
                background-color: #f2e9e4;
            }
        """)
        out_layout.addWidget(self.msg_edit)
        center_splitter.addWidget(output_box)

        center_splitter.setStretchFactor(0, 1) 
        center_splitter.setStretchFactor(1, 3)
        center_splitter.setSizes([300, 500])

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.addWidget(center_splitter)
        center_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.addWidget(center_widget)

        # Right Panel: Templates
        right_frame = QFrame()
        right_frame.setFrameShape(QFrame.StyledPanel)
        right_frame.setMinimumWidth(250)
        right_layout = QVBoxLayout(right_frame)

        tpl_label = QLabel("Selected Templates")
        tpl_label.setFont(QFont("Segoe UI", 14, QFont.Medium))
        tpl_label.setAlignment(Qt.AlignLeft)
        right_layout.addWidget(tpl_label)

        self.templates_table = QTableWidget(0, 5)
        self.templates_table.setHorizontalHeaderLabels(["Use", "PDB_ID", "Chain", "Accession", "Description"])
        self.templates_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.templates_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.templates_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.templates_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.templates_table)
        splitter.addWidget(right_frame)

        # Splitter proportions 
        splitter.setSizes([250, 800, 300])
        splitter.setStretchFactor(0, 1)  # left
        splitter.setStretchFactor(1, 3)  # center
        splitter.setStretchFactor(2, 1)  # right
        self.main_layout.addWidget(splitter)
        self.main_layout.setStretchFactor(splitter, 1)
       
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(100)
        self.status_display.setPlainText("Ready")
        self.main_layout.addWidget(splitter)
        self.main_layout.addWidget(self.status_display)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setValue(0)
        self.main_layout.addWidget(self.progress)

        # Pre-populate if templates provided
        if self.selected_templates:
            self.populate_templates(self.selected_templates)
            self.auto_download_pdbs()
            self.status_display.setPlainText("Templates loaded. Ready for alignment.")

    def open_fasta(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open FASTA or .ali", "", "FASTA/ALI Files (*.fasta *.fa *.ali *.pir);;All Files (*)")
        if not path: return
        self.upload_path = path
        with open(path, 'r', encoding='utf-8') as f:
            self.uploaded_file = f.read()
        self.preview_edit.setPlainText("\n".join(self.uploaded_file.splitlines()[:400]))
        self.status_display.setText(f"Loaded: {os.path.basename(path)}")
        self.align_btn.setEnabled(True)
        self.download_btn.setEnabled(False)

    def import_blast_selection(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load BLAST Selection", "", "PDB Files (*.pdb);;All Files (*)")
        if not path: return
        parsed = []
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                for ln in fh:
                    parts = ln.strip().split()
                    if not parts: continue
                    pdb = parts[0]
                    parsed.append({
                        'PDB_ID': pdb,
                        'Chain': parts[1] if len(parts)>1 else 'A',
                        'Accession': parts[2] if len(parts)>2 else '',
                        'Description': "BLAST Template"
                    })
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to parse BLAST file:\n{e}")
            return
        self.selected_templates.extend(parsed)
        self.populate_templates(self.selected_templates)
        self.msg_edit.append(f"Loaded {len(parsed)} BLAST templates")
        self.auto_download_pdbs()

    # Manual PDB import fallback
    def import_pdbs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDB Files", "", "PDB Files (*.pdb);;All Files (*)")
        if not files: return

        imported = []
        for file in files:
            pdb_id = os.path.splitext(os.path.basename(file))[0]
            # Avoid duplicates
            if any(tpl['PDB_ID'] == pdb_id for tpl in self.selected_templates):
                continue
            tpl = {'PDB_ID': pdb_id, 'Chain': 'A', 'Accession': '', 'Description': 'Manually imported'}
            self.selected_templates.append(tpl)
            imported.append(pdb_id)

        if imported:
            self.populate_templates(self.selected_templates)
            self.msg_edit.append(f"PDBs imported: {', '.join(imported)}")
            self.status_display.setText("PDBs imported successfully")
        else:
            self.msg_edit.append("No new PDBs imported (duplicates skipped).")

    def open_nextpage(self):
        from modelbuilding import ModelBuild
        self.modelwindow = ModelBuild()
        self.modelwindow.show()
        self.close()

    def populate_templates(self, templates):
        self.templates_table.setRowCount(0)
        for tpl in templates:
            row = self.templates_table.rowCount()
            self.templates_table.insertRow(row)
            chk = QCheckBox()
            chk.setChecked(True)
            self.templates_table.setCellWidget(row, 0, chk)
            self.templates_table.setItem(row, 1, QTableWidgetItem(tpl.get('PDB_ID','')))
            self.templates_table.setItem(row, 2, QTableWidgetItem(tpl.get('Chain','A')))
            self.templates_table.setItem(row, 3, QTableWidgetItem(tpl.get('Accession','')))
            self.templates_table.setItem(row, 4, QTableWidgetItem(tpl.get('Description','')))

 
    def auto_download_pdbs(self):
        if not self.selected_templates:
            return
        downloaded = []
        for tpl in self.selected_templates:
            pdb_id = tpl['PDB_ID']
            pdb_path = f"{pdb_id}.pdb"
            if os.path.exists(pdb_path):
                continue
            url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    with open(pdb_path, 'wb') as f:
                        f.write(r.content)
                    downloaded.append(pdb_id)
            except Exception:
                pass
        if downloaded:
            self.msg_edit.append(f"Auto-downloaded PDBs: {', '.join(downloaded)}")
            self.status_display.setText("Template PDBs ready ✅")


    def do_align(self):
        if not self.upload_path or not self.selected_templates:
            QMessageBox.warning(self, "Missing Input", "Please upload target file and ensure templates are available.")
            return

        self.msg_edit.clear()
        self.msg_edit.append("Running Modeller alignment...")
        self.progress.setValue(20)
        QApplication.processEvents()

        try:
            env = Environ()
            aln = Alignment(env)

            for tpl in self.selected_templates:
                code = tpl['PDB_ID']
                pdbfile = f"{code}.pdb"
                align_code = f"{code}{tpl.get('Chain','A')}"
                if not os.path.exists(pdbfile):
                    raise FileNotFoundError(f"PDB file not found: {pdbfile}")
                mdl = Model(env, file=code)
                aln.append_model(mdl, align_codes=align_code, atom_files=pdbfile)
                self.msg_edit.append(f"Template added: {code}")

            aln.append(file=self.upload_path, alignment_format='PIR' if self.upload_path.endswith('.ali') else 'FASTA')
            aln.align2d(max_gap_length=50)
            aln.write(file='Alignment.ali', alignment_format='PIR')
            aln.write(file='Alignment.pap', alignment_format='PAP')

            if os.path.exists('Alignment.pap'):
                with open('Alignment.pap', 'r', encoding='utf-8') as f:
                    pap = f.read()
                self.msg_edit.append("\n=== Alignment (.pap) Preview ===\n")
                self.msg_edit.append(pap[:5000])
            else:
                self.msg_edit.append("⚠️ PAP file not generated.")

            self.progress.setValue(100)
            self.status_display.setText("Alignment complete ✅")
            self.download_btn.setEnabled(True)

        except Exception as e:
            self.msg_edit.append(f"❌ Error: {str(e)}")
            self.status_display.setText("Alignment failed")
            self.progress.setValue(0)


    def download_ali(self):
        if not os.path.exists('Alignment.ali'):
            QMessageBox.warning(self, "Not Found", "No .ali file generated yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Alignment", "alignment.ali", "PIR/ALI Files (*.ali);;All Files (*)")
        if not path: return
        with open('Alignment.ali', 'r', encoding='utf-8') as src:
            content = src.read()
        with open(path, 'w', encoding='utf-8') as dest:
            dest.write(content)
        QMessageBox.information(self, "Saved", f"Saved: {path}")
        self.status_display.setText(f"Saved {os.path.basename(path)} ✅")


def main():
    app = QApplication(sys.argv)
    window = DynamicAlign()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
