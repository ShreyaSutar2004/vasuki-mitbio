import os
import sys

# os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

# from PyQt5.QtCore import Qt, QCoreApplication
# QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

# from PyQt5 import QtWebEngine
# QtWebEngine.QtWebEngine.initialize()

import io
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QFileDialog, QTextEdit, QWidget, QMessageBox, QLineEdit, QSpinBox,
    QCheckBox, QProgressBar, QGroupBox, QFormLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter
)
from PyQt5.QtGui import QFont, QColor, QIcon, QPalette, QBrush, QLinearGradient
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from modeller import Environ
from modeller.automodel import AutoModel, assess

from dynamic_align import DynamicAlign



class LogStream(io.StringIO):
    def __init__(self, line_signal):
        super().__init__()
        self.line_signal = line_signal
        self.pending = ""

    def write(self, text):
        super().write(text)
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            if line.strip():
                self.line_signal.emit(line)


class ModelBuildWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, bool, list)
    message = pyqtSignal(str)
    log_line = pyqtSignal(str)

    def __init__(self, alnfile, knowns, sequence, start_model, end_model, assess_methods, output_dir=None):
        super().__init__()
        self.alnfile = alnfile
        self.knowns = knowns
        self.sequence = sequence
        self.start_model = start_model
        self.end_model = end_model
        self.assess_methods = assess_methods
        self.output_dir = output_dir
        self._cancel = False



    def run(self):
        log_text = ""
        success = False
        successful_models = []
        old_stdout = None
        original_cwd = os.getcwd()

        try:
            self.message.emit("Initializing Modeller environment...")
            env = Environ()

            # Ensure outputs go to chosen folder
            if self.output_dir:
                os.makedirs(self.output_dir, exist_ok=True)
                os.chdir(self.output_dir)
            env.io.atom_files_directory = [self.output_dir or os.getcwd()]
            self.message.emit(f"Models will be saved to: {self.output_dir or os.getcwd()}")

            # Capture Modeller output
            buffer = LogStream(self.log_line)
            old_stdout = sys.stdout
            sys.stdout = buffer
            sys.stderr = buffer

            self.message.emit("Starting model build...")
            a = AutoModel(env,
                          alnfile=self.alnfile,
                          knowns=self.knowns,
                          sequence=self.sequence,
                          assess_methods=self.assess_methods)
            a.starting_model = self.start_model
            a.ending_model = self.end_model

            self.message.emit(f"Building models {self.start_model} to {self.end_model}...")

            if self._cancel:
                raise RuntimeError("Build cancelled by user.")

            a.make()
            success = True
            log_text = buffer.getvalue()

            # Parse summary
            summary_match = re.search(r'Summary of successfully produced models:[\s\S]+', log_text)
            if summary_match:
                successful_models = self.parse_summary(summary_match.group(0))

            self.message.emit(f"Produced {len(successful_models)} successful models.")
        except Exception as e:
            import traceback
            error_msg = f"Build failed: {e}\n{traceback.format_exc()}"
            self.message.emit(error_msg)
            log_text = error_msg
        finally:
            if old_stdout is not None:
                sys.stdout = old_stdout
            sys.stderr = sys.__stderr__
            os.chdir(original_cwd)

        self.finished.emit(log_text, success, successful_models)

    def parse_summary(self, text):
        successful_models = []
        lines = [l for l in text.split('\n') if l.strip() and not l.startswith('---')]
        if len(lines) > 2:
            headers = re.split(r'\s{2,}', lines[1].strip())
            key_map = {'Filename': 'filename', 'molpdf': 'molpdf', 'DOPE score': 'dope', 'GA341 score': 'ga341'}
            keys = [key_map.get(h, h.lower()) for h in headers]
            for line in lines[2:]:
                fields = re.split(r'\s{2,}', line.strip())
                if len(fields) >= len(keys):
                    model = dict(zip(keys, fields[:len(keys)]))
                    for k in ['molpdf', 'dope', 'ga341']:
                        try:
                            model[k] = float(model[k])
                        except Exception:
                            pass
                    successful_models.append(model)
        return successful_models

    def cancel(self):
        self._cancel = True
        self.message.emit("Cancel requested. (Note: may not stop an active model run.)")


class ModelBuild(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Modeller GUI - Model Building')
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(QIcon("D:/Shreya_VS_projects/Modeller_automation/Images/Screenshot 2025-11-09 171245.png"))
        self.worker = None
        self.visualizers =[]
        self.initUI()

    
    def initUI(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Title
        title = QLabel("""
            <span style="font-family:'Source Sans Pro'; 
                         font-size:22pt; 
                         font-weight:400; 
                         color:#924511;">
                         Model Building
            </span>
        """)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setFixedHeight(50)
        main_layout.addWidget(title)

        # Background gradient
        palette = QPalette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#d6ccc2"))
        gradient.setColorAt(1.0, QColor("#f5ebe0"))
        palette.setBrush(QPalette.Window, QBrush(gradient))
        self.setAutoFillBackground(True)
        self.setPalette(palette)


        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("QSplitter::handle { background-color: #c9c4b8; }")

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(15)

        # Section title
        section_label = QLabel("Controls")
        section_label.setFont(QFont("Segoe UI", 12, QFont.Medium))
        section_label.setStyleSheet("color:#4a4e69;")
        left_layout.addWidget(section_label)

        # Label style
        def field_label(text):
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 11, QFont.Medium))
            lbl.setStyleSheet("color:#4a4e69; padding-left:2px;")
            return lbl

        # Styled input
        def styled_input():
            le = QLineEdit()
            le.setFont(QFont("Consolas", 10))
            le.setStyleSheet("""
                QLineEdit {
                    background:#f2e9e4; 
                    padding:6px;
                    border-radius:6px;
                }
            """)
            return le

        # Styled small button
        def small_button(text):
            btn = QPushButton(text)
            btn.setFont(QFont("Segoe UI", 10))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color:#9a8c98;
                    color:white;
                    padding:6px 14px;
                    border-radius:6px;
                }
                QPushButton:pressed {
                    background-color:#d1495b;
                }
            """)
            return btn

        # Alignment file
        left_layout.addWidget(field_label("Alignment File"))
        self.aln_edit = styled_input()
        btn_aln = small_button("Browse")
        btn_aln.clicked.connect(self.browse_alignment)
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self.aln_edit)
        row1.addWidget(btn_aln)
        left_layout.addLayout(row1)

        # Known templates
        left_layout.addWidget(field_label("Templates (comma-separated)"))
        self.knowns_edit = styled_input()
        left_layout.addWidget(self.knowns_edit)

        # Target Sequence name
        left_layout.addWidget(field_label("Target Sequence (label from .ali file)"))
        self.seq_edit = styled_input()
        left_layout.addWidget(self.seq_edit)

        # Output folder
        left_layout.addWidget(field_label("Output Folder"))
        self.output_edit = styled_input()
        btn_out = small_button("Browse")
        btn_out.clicked.connect(self.browse_output)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self.output_edit)
        row2.addWidget(btn_out)
        left_layout.addLayout(row2)

        # Model range
        left_layout.addWidget(field_label("Model Range"))
        range_row = QHBoxLayout()
        # range_row.setSpacing(5)
        self.start_spin = QSpinBox()
        self.start_spin.setMinimum(1)
        self.end_spin = QSpinBox()
        self.end_spin.setValue(2)
        for w in (self.start_spin, self.end_spin):
            w.setFont(QFont("Segoe UI", 12))
            w.setFixedWidth(60)

        label_from = QLabel('From')
        label_from.setFont(QFont('Concolas',12))
        label_to = QLabel('To')
        label_to.setFont(QFont('Concolas', 12))
        range_row.addWidget(label_from)
        range_row.addWidget(self.start_spin)
        range_row.addWidget(label_to)
        range_row.addWidget(self.end_spin)
        left_layout.addLayout(range_row)

        # Assess methods
        left_layout.addWidget(field_label("Assessment Methods"))
        chk_row = QHBoxLayout()
        chk_row.setSpacing(10)
        self.chk_dope = QCheckBox("DOPE")
        self.chk_dope.setFont(QFont('Concolas', 12))
        self.chk_ga341 = QCheckBox("GA341")
        self.chk_ga341.setFont(QFont('Concolas', 12))
        self.chk_ga341.setChecked(True)
        chk_row.addWidget(self.chk_dope)
        chk_row.addWidget(self.chk_ga341)
        left_layout.addLayout(chk_row)

        # Action Buttons
        def action_button(text, color):
            btn = QPushButton(text)
            btn.setFont(QFont("Segoe UI", 11, QFont.Medium))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color:{color};
                    color:white;
                    border-radius:8px;
                    padding:10px 20px;
                    margin-bottom: 5px;
                }}
                QPushButton:pressed {{
                    background-color:#6b705c;
                }}
            """)
            return btn

        self.btn_build = action_button("Build Models", "#2e7d32")

        self.btn_build.clicked.connect(self.start_build)
        left_layout.addWidget(self.btn_build)

        self.btn_cancel = action_button("Cancel", "#d1495b")
        self.btn_cancel.clicked.connect(self.cancel_build)
        self.btn_cancel.setEnabled(False)
        left_layout.addWidget(self.btn_cancel)

        left_layout.addStretch()
        splitter.addWidget(left_widget)



        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(12)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 11))
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                background:#9a8c98;
                color:white;
                padding:10px;
                border-radius:6px;
                margin-right:4px;
            }
            QTabBar::tab:selected {
                background:#6b705c;
            }
        """)
        right_layout.addWidget(self.tabs)

        # Console Tab
        console_tab = QWidget()
        console_layout = QVBoxLayout(console_tab)
        console_layout.setSpacing(10)

        self.console = QTextEdit()
        self.console.setFont(QFont("Consolas", 10))
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background:#f2e9e4; padding:10px; border-radius:10px;")
        console_layout.addWidget(self.console)

        self.progress = QProgressBar()
        console_layout.addWidget(self.progress)

        self.status_label = QLabel("Idle")
        self.status_label.setFont(QFont("Segoe UI", 11))
        console_layout.addWidget(self.status_label)

        self.tabs.addTab(console_tab, "Console")

        # Models Tab
        models_tab = QWidget()
        models_layout = QVBoxLayout(models_tab)

        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget {
                background:#f2e9e4;
                border-radius:10px;
                selection-background-color:#9a8c98;
            }
            QHeaderView::section {
                background:#9a8c98;
                color:white;
                padding:8px;
            }
        """)
        models_layout.addWidget(self.table)

        self.tabs.addTab(models_tab, "Models")

        splitter.addWidget(right_widget)
        splitter.setSizes([350, 900])

        main_layout.addWidget(splitter)


    def parse_ali_file(self, ali_path):
        """Parse .ali/.pir file to extract template and target align codes."""
        templates, target = [], None
        with open(ali_path, 'r') as f:
            lines = f.readlines()

        current = None
        for line in lines:
            line = line.strip()
            if line.startswith('>P1;'):
                current = line.split(';')[1].strip()
            elif current and line.lower().startswith('structurex'):
                templates.append(current)
                current = None
            elif current and line.lower().startswith('sequence:'):
                target = current
                current = None
        return templates, target


    # --- Slots ---
    def browse_alignment(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Alignment File", "", "Alignment Files (*.ali *.pir);;All Files (*)"
        )
        if path:
            self.aln_edit.setText(path)
            try:
                templates, target = self.parse_ali_file(path)
                if templates:
                    self.knowns_edit.setText(",".join(templates))
                if target:
                    self.seq_edit.setText(target)
                QMessageBox.information(
                    self,
                    "Alignment Parsed",
                    f"Detected Templates: {', '.join(templates)}\nTarget: {target}"
                )
            except Exception as e:
                QMessageBox.warning(self, "Parsing Error", f"Failed to parse alignment file:\n{e}")


    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    def start_build(self):
        alnfile = self.aln_edit.text().strip()
        if not alnfile or not os.path.exists(alnfile):
            QMessageBox.warning(self, "Invalid File", "Please select a valid alignment file.")
            return
        knowns = self.knowns_edit.text().strip()
        knowns = tuple(k.strip() for k in knowns.split(',') if k.strip())
        sequence = self.seq_edit.text().strip()
        if not sequence:
            QMessageBox.warning(self, "Missing Target", "Enter target sequence name present in alignment file.")
            return
        outdir = self.output_edit.text().strip() or None

        assess_methods = []
        if self.chk_dope.isChecked(): assess_methods.append(assess.DOPE)
        if self.chk_ga341.isChecked(): assess_methods.append(assess.GA341)
        if not assess_methods: assess_methods = (assess.GA341,)

        self.console.clear()
        self.progress.setRange(0, 0)
        self.status_label.setText("Running Modeller...")
        self.btn_build.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        self.worker = ModelBuildWorker(alnfile, knowns, sequence,
                                       self.start_spin.value(),
                                       self.end_spin.value(),
                                       tuple(assess_methods),
                                       outdir)
        self.worker.message.connect(self.console.append)
        self.worker.log_line.connect(self.on_log_line)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def cancel_build(self):
        if self.worker:
            self.worker.cancel()
            self.status_label.setText("Cancelling...")
        self.btn_cancel.setEnabled(False)

    def on_log_line(self, line):
        self.console.append(line)
        # Detect live summary
        if "Summary of successfully produced models:" in line:
            text = self.console.toPlainText()
            match = re.search(r"Summary of successfully produced models:[\s\S]+", text)
            if match:
                models = self.worker.parse_summary(match.group(0))
                if models:
                    self.populate_table(models)
    
    
    
        
    
                

    def populate_table(self, models):
        if not models: return
        headers = ["Filename", "MolPDF", "DOPE", "GA341","Visualize"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(models))

        best_dope = min((m.get('dope', float('inf')) for m in models if m.get('dope') is not None), default=None)
        for r, m in enumerate(models):
            self.table.setItem(r, 0, QTableWidgetItem(str(m.get('filename', ''))))
            self.table.setItem(r, 1, QTableWidgetItem(f"{m.get('molpdf', 0):.2f}"))
            dope_val = m.get('dope')
            dope_item = QTableWidgetItem(f"{dope_val:.2f}" if dope_val else "")
            if dope_val == best_dope:
                dope_item.setBackground(QColor(144, 238, 144))
            self.table.setItem(r, 2, dope_item)
            self.table.setItem(r, 3, QTableWidgetItem(f"{m.get('ga341', 0):.2f}"))

            visualize_btn = QPushButton("Visualize")
            visualize_btn.setStyleSheet('background-color : lightgreen; color : white; font-weight: bold')

            visualize_btn.clicked.connect(lambda _, model=m: self.open_visualizer(model))
            self.table.setCellWidget(r, 4, visualize_btn)
            

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabs.setCurrentIndex(1)

    def on_finished(self, log_text, success, models):
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        if models:
            self.populate_table(models)
        self.status_label.setText("Completed" if success else "Failed")
        self.btn_build.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def open_visualizer(self, model):
        from visualize import Visualizer
        filename = model.get('filename')
        output_dir = self.output_edit.text().strip()

        if not filename:
            QMessageBox.warning(self, "No File", "Model file not found.")
            return

        viz = Visualizer(output_dir)
        viz.visualize_model(model)

        viz.show()

        self.visualizers.append(viz) 
        




def main():
    app = QApplication(sys.argv)
    gui = ModelBuild()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
