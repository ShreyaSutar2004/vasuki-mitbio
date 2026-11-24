
import os
import sys
import subprocess

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
from modeller.automodel import AutoModel, assess, refine, autosched

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')

from .dynamic_align import DynamicAlign
from .validation import RamPlotGUI



# Relaxation runs in its own Python process so that a native crash of OpenMM (or a library
# clash with Qt / OpenGL) can never close the VASUKI window. The process loads relax.py by
# path and calls relax_pdb(), so it works with any version of relax.py that has that function.
_RELAX_RUNNER = r"""
import sys, importlib.util
script, src, dst, iters = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
spec = importlib.util.spec_from_file_location("vasuki_relax", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.relax_pdb(src, dst, max_iterations=iters, log=lambda s: print(s, flush=True))
"""


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

    def __init__(self, alnfile, knowns, sequence, start_model, end_model, assess_methods,
                 output_dir=None, relax=False):
        super().__init__()
        self.relax = relax
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

            self.message.emit("Starting model building")
            a = AutoModel(env,
                          alnfile=self.alnfile,
                          knowns=self.knowns,
                          sequence=self.sequence,
                          assess_methods=self.assess_methods)
            a.starting_model = self.start_model
            a.ending_model = self.end_model
            # Stronger optimisation / refinement (slower, cleaner stereochemistry)
            a.library_schedule = autosched.slow
            a.max_var_iterations = 300
            a.md_level = refine.slow
            a.repeat_optimization = 2

            self.message.emit(f"Building models {self.start_model} to {self.end_model}")
            

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
            for m in successful_models:
                m['type'] = 'Raw'

            # Optional relaxation (restrained energy minimisation, OpenMM).
            # The relaxed models REPLACE the raw ones in the list that is carried on to the
            # Models tab, visualization and validation (the raw files stay in the output
            # folder). A model that could not be relaxed keeps its raw version, so the set
            # stays complete.
            if successful_models and self.relax and not self._cancel:
                self.message.emit("Model building completed. Initiating relaxation of models...")
                relaxed = {r['source']: r for r in self.relax_models(successful_models)}
                not_relaxed = [m['filename'] for m in successful_models
                               if m['filename'] not in relaxed]
                if not_relaxed:
                    self.message.emit("Not relaxed, raw model carried forward: "
                                      + ", ".join(not_relaxed))
                successful_models[:] = [relaxed.get(m['filename'], m)
                                        for m in successful_models]
    
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

    def relax_models(self, models):
        """Restrained energy minimisation of every built model.

        Each model is relaxed in a SEPARATE Python process (relax.py), so a native crash
        of OpenMM, or a library conflict with Qt/OpenGL, can never take this window down.
        Raw models are kept; relaxed copies are written as <name>_relaxed.pdb.
        Output of the relaxation is saved to relax_log.txt in the output folder.
        Never raises: problems are reported in the console and the raw models stay valid."""
        relaxed = []
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relax.py")
        if not os.path.exists(script):
            self.message.emit("Relaxation skipped: relax.py not found next to modelbuilding.py")
            return relaxed

        total = len(models)
        log_path = os.path.abspath("relax_log.txt")
        popen_extra = {}
        if os.name == "nt":
            popen_extra["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
        try:
            logf = open(log_path, "w", encoding="utf-8")
        except OSError:
            logf = None

        try:
            for i, m in enumerate(models, 1):
                if self._cancel:
                    self.message.emit("Relaxation cancelled.")
                    break
                src = os.path.abspath(m['filename'])
                dst = os.path.abspath(os.path.splitext(m['filename'])[0] + '_relaxed.pdb')
                self.message.emit(f"Relaxing {m['filename']} ({i}/{total}) ...")
                if logf:
                    logf.write(f"=== {m['filename']}\n")

                tail, code = [], None
                try:
                    proc = subprocess.Popen(
                        [sys.executable, "-c", _RELAX_RUNNER, script, src, dst, "500"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        encoding="utf-8", errors="replace", **popen_extra)
                    for line in proc.stdout:
                        line = line.rstrip()
                        if not line:
                            continue
                        if logf:
                            logf.write(line + "\n")
                            logf.flush()
                        tail = (tail + [line])[-6:]
                        if line.lstrip().startswith("relax:"):
                            self.message.emit(line.strip())
                        if self._cancel:
                            proc.terminate()
                            break
                    code = proc.wait()
                except Exception as e:
                    tail = [f"could not start relaxation process: {e}"]
                    code = -1

                if any("Relaxation needs OpenMM" in l or "No module named 'openmm'" in l
                       or "No module named 'pdbfixer'" in l for l in tail):
                    self.message.emit("Relaxation skipped: OpenMM/PDBFixer missing "
                                      "(pip install openmm pdbfixer in the VASUKI environment).")
                    break
                if code != 0 or not os.path.exists(dst):
                    detail = tail[-1] if tail else f"process exit code {code}"
                    self.message.emit(
                        f"Relaxation failed for {m['filename']} (exit code {code}): "
                        f"{detail} | details: relax_log.txt")
                    continue
                relaxed.append({'filename': os.path.basename(dst), 'type': 'Relaxed',
                                'source': m['filename'],
                                'molpdf_raw': m.get('molpdf'), 'dope_raw': m.get('dope'),
                                'ga341_raw': m.get('ga341')})
        finally:
            if logf:
                logf.close()
        self.message.emit(f"Relaxation finished: {len(relaxed)} of {total} models relaxed.")
        return relaxed

    def cancel(self):
        self._cancel = True
        self.message.emit("Cancel requested. (Note: may not stop an active model run.)")


class ModelBuild(QMainWindow):
    def __init__(self, alnfile=None, output_dir=None):
        super().__init__()
        self.setWindowTitle('Modeller GUI - Model Building')
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
        self.worker = None
        self.visualizers = []
        self.models = []
        self.last_output_dir = None
        self.initUI()
        if alnfile:
            self.prefill(alnfile, output_dir)

    
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
        left_layout.setSpacing(9)

        # Section title
        section_label = QLabel("Controls")
        section_label.setFont(QFont("Segoe UI", 12))
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
        left_layout.addWidget(field_label("Templates"))
        self.knowns_edit = styled_input()
        left_layout.addWidget(self.knowns_edit)

        # Target Sequence name
        left_layout.addWidget(field_label("Target"))
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
        self.end_spin.setValue(5)
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

        # Relaxation
        left_layout.addWidget(field_label("Relaxation"))
        self.chk_relax = QCheckBox("Perform relaxation on generated models")
        self.chk_relax.setFont(QFont('Concolas', 12))
        self.chk_relax.setChecked(False)
        self.chk_relax.setToolTip(
            "Restrained energy minimisation (OpenMM) of every generated model to reduce "
            "clashes. If ticked, the relaxed models are shown in the Models tab and used for "
            "validation; otherwise the original MODELLER models are used. "
            "Needs: pip install openmm pdbfixer. Can be slow for large proteins.")
        left_layout.addWidget(self.chk_relax)

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

        self.btn_build = action_button("Build Models", "#3c6e71")

        self.btn_build.clicked.connect(self.start_build)
        left_layout.addWidget(self.btn_build)

        self.btn_cancel = action_button("Cancel", "#da4167")
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

        # Add button below table
        self.btn_ramplot = QPushButton("Model Structure Validation")
        self.btn_ramplot.setFont(QFont("Segoe UI", 12, QFont.Medium))
        self.btn_ramplot.setCursor(Qt.PointingHandCursor)
        self.btn_ramplot.setEnabled(False)  # Disable until table is generated
        self.btn_ramplot.setStyleSheet("""
            QPushButton {
                background-color:#9a8c98;
                color:white;
                padding:10px;
                border-radius:6px;
            }
            QPushButton:pressed {
                background-color:#d1495b;
            }
            QPushButton:disabled {
                background-color:#cccccc;
                color:#666666;
            }
        """)
        self.btn_ramplot.clicked.connect(self.open_ramplot)
        models_layout.addWidget(self.btn_ramplot)

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


    def prefill(self, alnfile, output_dir=None):
        """Fill the form from the alignment produced by the previous step."""
        try:
            if not os.path.exists(alnfile):
                return
            self.aln_edit.setText(alnfile)
            templates, target = self.parse_ali_file(alnfile)
            if templates:
                self.knowns_edit.setText(",".join(templates))
            if target:
                self.seq_edit.setText(target)
            self.output_edit.setText(output_dir or os.path.dirname(os.path.abspath(alnfile)))
            self.console.append(f"Alignment loaded from the previous step: {alnfile}")
        except Exception as e:
            self.console.append(f"Could not pre-fill from alignment: {e}")

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
        self.last_output_dir = os.path.abspath(outdir) if outdir else os.getcwd()

        assess_methods = []
        if self.chk_dope.isChecked(): assess_methods.append(assess.DOPE)
        if self.chk_ga341.isChecked(): assess_methods.append(assess.GA341)
        if not assess_methods: assess_methods = (assess.GA341,)

        self.relax_selected = self.chk_relax.isChecked()
        self.console.clear()
        self.progress.setRange(0, 0)
        self.status_label.setText("Running Modeller...")
        self.status_label.setFont(QFont("Segoe UI", 11))
        self.btn_build.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        self.worker = ModelBuildWorker(alnfile, knowns, sequence,
                                       self.start_spin.value(),
                                       self.end_spin.value(),
                                       tuple(assess_methods),
                                       outdir,
                                       relax=self.relax_selected)
        self.worker.message.connect(self.on_message)
        self.worker.log_line.connect(self.on_log_line)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def cancel_build(self):
        if self.worker:
            self.worker.cancel()
            self.status_label.setText("Cancelling...")
            self.status_label.setFont(QFont("Segoe UI", 11))
        self.btn_cancel.setEnabled(False)

    def on_message(self, text):
        self.console.append(text)
        if "Initiating relaxation" in text:
            self.status_label.setText("Relaxing models...")
            self.status_label.setFont(QFont("Segoe UI", 11))

    def on_log_line(self, line):
        self.console.append(line)
        # Detect live summary
        if ("Summary of successfully produced models:" in line
                and not getattr(self, 'relax_selected', False)):
            try:
                text = self.console.toPlainText()
                match = re.search(r"Summary of successfully produced models:[\s\S]+", text)
                if match:
                    models = self.worker.parse_summary(match.group(0))
                    if models:
                        self.populate_table(models)
            except Exception as e:
                self.console.append(f"(could not show the live model table: {e})")
                

    def populate_table(self, models):
        if not models:
            return
        self.models = list(models)
        headers = ["Filename", "Type", "MolPDF", "DOPE", "GA341", "Visualize"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(models))

        def shown(m, key):
            """(text, number). Scores of a relaxed model are those of the raw model it
            was made from (marked "(raw)"), so models can still be ranked by DOPE."""
            v = m.get(key)
            if isinstance(v, (int, float)):
                return f"{v:.2f}", v
            v = m.get(key + '_raw')
            if isinstance(v, (int, float)):
                return f"{v:.2f} (raw)", v
            return ("n/a" if m.get('type') == 'Relaxed' else ""), None

        best_dope = min((shown(m, 'dope')[1] for m in models
                         if shown(m, 'dope')[1] is not None), default=None)
        for r, m in enumerate(models):
            mtype = m.get('type', 'Raw')
            self.table.setItem(r, 0, QTableWidgetItem(str(m.get('filename', ''))))
            type_item = QTableWidgetItem(mtype)
            if mtype == 'Relaxed':
                type_item.setBackground(QColor(255, 244, 179))
            self.table.setItem(r, 1, type_item)
            self.table.setItem(r, 2, QTableWidgetItem(shown(m, 'molpdf')[0]))
            dope_text, dope_val = shown(m, 'dope')
            dope_item = QTableWidgetItem(dope_text)
            if dope_val is not None and best_dope is not None and dope_val == best_dope:
                dope_item.setBackground(QColor(144, 238, 144))
            self.table.setItem(r, 3, dope_item)
            self.table.setItem(r, 4, QTableWidgetItem(shown(m, 'ga341')[0]))

            visualize_btn = QPushButton("Visualize")
            visualize_btn.setStyleSheet('background-color : #e0afa0; color : white; font-weight: bold')
            visualize_btn.clicked.connect(lambda _, model=m: self.open_visualizer(model))
            self.table.setCellWidget(r, 5, visualize_btn)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.btn_ramplot.setEnabled(True)
        self.tabs.setCurrentIndex(1)

    def on_finished(self, log_text, success, models):
        try:
            self._on_finished_impl(log_text, success, models)
        except Exception:
            import traceback
            self.console.append("Error while showing the results:\n" + traceback.format_exc())
            self.btn_build.setEnabled(True)
            self.btn_cancel.setEnabled(False)

    def _on_finished_impl(self, log_text, success, models):
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        if models:
            self.populate_table(models)
            n_rel = sum(1 for m in models if m.get('type') == 'Relaxed')
            n_raw = len(models) - n_rel
            if n_rel:
                extra = f" ({n_raw} could not be relaxed and are shown as raw)" if n_raw else ""
                self.console.append(
                    f"Models ready: {n_rel} relaxed models{extra}. These are used for "
                    "visualization and validation; the original models stay in the output folder.")
            else:
                if getattr(self, 'relax_selected', False):
                    self.console.append("Relaxation could not be applied; showing the original models.")
                self.console.append(
                    f"Models ready: {n_raw} original models. "
                    "Use 'Model Structure Validation' to validate them.")
        self.status_label.setText("Completed" if success else "Failed")
        self.btn_build.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def open_visualizer(self, model):
        from .visualize import Visualizer
        filename = model.get('filename')
        output_dir = self.last_output_dir or self.output_edit.text().strip() or os.getcwd()

        if not filename:
            QMessageBox.warning(self, "No File", "Model file not found.")
            return

        viz = Visualizer(output_dir)
        viz.visualize_model(model)

        viz.show()

        self.visualizers.append(viz) 

    def open_ramplot(self):
        """Open the Ramachandran Plot visualization window."""
        files = [m['filename'] for m in self.models if m.get('filename')]
        folder = self.last_output_dir or self.output_edit.text().strip() or os.getcwd()
        # hand over exactly the models of this run (raw + relaxed), not the whole folder
        self.ramplot_window = RamPlotGUI(input_dir=folder, files=files)
        self.ramplot_window.show()

        self.close()
        
def main():
    app = QApplication(sys.argv)
    gui = ModelBuild()
    gui.show()
    # sys.exit(app.exec_())


if __name__ == "__main__":
    main()