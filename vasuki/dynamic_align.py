from modeller import Environ, Model, Alignment
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QFileDialog, QTextEdit, QWidget, QMessageBox, QGroupBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
    QToolBar, QAction, QSplitter, QSizePolicy, QFrame
)
from PyQt5.QtGui import QFont, QIcon, QPalette, QLinearGradient, QColor, QBrush
from PyQt5.QtCore import Qt, QSize
import sys, os, shutil, html, requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')

MAX_OVERHANG = 40
# None = MODELLER defaults. Set e.g. (-600, -600) to compare alignments.
GAP_PENALTIES_1D = None


def _read_pir(path):
    recs = []
    with open(path) as fh:
        text = fh.read()
    for chunk in text.split('>P1;')[1:]:
        lines = [l.rstrip() for l in chunk.strip().splitlines()]
        recs.append((lines[0].strip(), lines[1],
                     ''.join(lines[2:]).replace('*', '').replace(' ', '')))
    return recs


_THREE2ONE = {
    'ALA': 'A', 'ARG': 'R', 'ASN': 'N', 'ASP': 'D', 'CYS': 'C', 'GLN': 'Q',
    'GLU': 'E', 'GLY': 'G', 'HIS': 'H', 'ILE': 'I', 'LEU': 'L', 'LYS': 'K',
    'MET': 'M', 'PHE': 'F', 'PRO': 'P', 'SER': 'S', 'THR': 'T', 'TRP': 'W',
    'TYR': 'Y', 'VAL': 'V'}


def _template_ss(pdb_path, chain, first_res, seq):
    """Secondary structure of the template residues from the PDB HELIX/SHEET
    records: one character per residue ('H' helix, 'E' strand, ' ' other).
    Returns None if the file/records are missing or do not match `seq`."""
    if not os.path.exists(pdb_path):
        return None
    helices, strands, res, seen = [], [], [], set()
    with open(pdb_path) as fh:
        for line in fh:
            rec = line[:6]
            try:
                if rec == 'HELIX ' and line[19] == chain and line[31] == chain:
                    helices.append((int(line[21:25]), int(line[33:37])))
                elif rec == 'SHEET ' and line[21] == chain and line[32] == chain:
                    strands.append((int(line[22:26]), int(line[33:37])))
                elif (rec == 'ATOM  ' and line[12:16].strip() == 'CA'
                      and line[21] == chain and line[16] in ' A'):
                    key = (int(line[22:26]), line[26])
                    if key not in seen:
                        seen.add(key)
                        res.append((key[0], _THREE2ONE.get(line[17:20], 'X')))
            except (ValueError, IndexError):
                continue
    if not res or not (helices or strands):
        return None
    start = 0
    if first_res is not None:
        idx = [i for i, (num, _) in enumerate(res) if num == first_res]
        if not idx:
            return None
        start = idx[0]
    chunk = res[start:start + len(seq)]
    if len(chunk) != len(seq) or ''.join(a for _, a in chunk) != seq:
        return None
    out = []
    for num, _ in chunk:
        if any(s <= num <= e for s, e in helices):
            out.append('H')
        elif any(s <= num <= e for s, e in strands):
            out.append('E')
        else:
            out.append(' ')
    return ''.join(out)


def _ss_columns(header, ts, pdb_dir):
    """Per-alignment-column helix/strand string for one template (or None)."""
    f = header.split(':')
    if len(f) < 4:
        return None
    pdb_path = os.path.join(pdb_dir, f[1].strip())
    if not os.path.exists(pdb_path) and os.path.exists(pdb_path + '.pdb'):
        pdb_path += '.pdb'
    first = f[2].strip()
    try:
        first_res = int(first)
    except ValueError:
        first_res = None
    ss = _template_ss(pdb_path, f[3].strip(), first_res, ts.replace('-', ''))
    if not ss:
        return None
    it = iter(ss)
    return ''.join(next(it) if c != '-' else ' ' for c in ts)


def _render_alignment(path, title, width=60, pdb_dir='.', kept=None):
    """Readable pairwise rendering (each template vs target) of a PIR file.
    Adds helix/strand rows for the template when the PDB has HELIX/SHEET
    records, and a TRIMMED row marking columns removed for model building
    (pass `kept` = column indices that were kept)."""
    recs = _read_pir(path)
    temps = [r for r in recs if r[1].lower().startswith('structure')]
    targs = [r for r in recs if r[1].lower().startswith('sequence')]
    qc, _, qs = targs[-1]
    n = len(qs)
    trim_line = None
    if kept is not None and len(kept) < n:
        kept_set = set(kept)
        trim_line = ''.join(' ' if i in kept_set else 'x' for i in range(n))

    out = [title, '=' * len(title),
           f"Target  : {qc} ({sum(c != '-' for c in qs)} residues)",
           f"Columns : {n}"]
    for tc, _, ts in temps:
        aligned = sum(1 for a, b in zip(ts, qs) if a != '-' and b != '-')
        ident = sum(1 for a, b in zip(ts, qs) if a == b and a != '-')
        out.append(f"Template {tc}: {sum(c != '-' for c in ts)} residues | "
                   f"identity {ident}/{aligned} ({100 * ident / max(aligned, 1):.1f}%) | "
                   f"covers {aligned} target residues")
    out.append('')
    any_ss = False
    for tc, th, ts in temps:
        ss_cols = _ss_columns(th, ts, pdb_dir)
        any_ss = any_ss or bool(ss_cols)
        out.append(f"--- {tc} vs {qc} ---")
        for i in range(0, n, width):
            a_row, b_row = ts[i:i + width], qs[i:i + width]
            cons = ''.join('*' if a == b and a != '-' else (' ' if '-' in (a, b) else '.')
                           for a, b in zip(a_row, b_row))
            out += [f"{i + 1:>6}", f"{tc:<12}{a_row}"]
            if ss_cols:
                out.append(f"{'H/E':<12}{ss_cols[i:i + width]}")
            out += [f"{qc:<12}{b_row}", f"{'':<12}{cons}"]
            if trim_line:
                out.append(f"{'TRIMMED':<12}{trim_line[i:i + width]}")
            out.append('')
    legend = '* identical   . mismatch   (blank) gap'
    if any_ss:
        legend += '   H helix / E strand (template, from PDB HELIX/SHEET records)'
    if trim_line:
        legend += '   x column removed for model building'
    out.append(legend)
    return '\n'.join(out)


def write_alignment_report(full_ali, used_ali, out_path, info=None, pdb_dir='.'):
    """Write the full (gapped) alignment, the alignment used for modelling
    (if trimmed) and the list of trimmed residues to one text file.
    The full alignment carries helix/strand rows and marks the trimmed columns."""
    kept = info.get("kept") if info else None
    parts = [_render_alignment(
        full_ali, "FULL alignment (untrimmed; gaps = no template coverage)",
        pdb_dir=pdb_dir, kept=kept if (info and info.get("dropped")) else None)]
    if info and info.get("dropped"):
        parts.append(_render_alignment(
            used_ali, "ALIGNMENT USED FOR MODEL BUILDING (template-free termini trimmed)",
            pdb_dir=pdb_dir))
        parts.append('\n'.join([
            "TRIMMED RESIDUES (no template coverage; excluded from model building)",
            "=====================================================================",
            f"N-terminus ({len(info['cut_lead'])}): {info['cut_lead'] or '-'}",
            f"C-terminus ({len(info['cut_trail'])}): {info['cut_trail'] or '-'}",
            "Template residues were not altered. Internal gaps are never trimmed.",
            "Model numbering runs 1..N over the trimmed target, not original numbering."]))
    else:
        parts.append("No trimming was applied; the full alignment was used for model building.")
    if info and (info.get("islands_lead") or info.get("islands_trail")):
        parts.append(
            "WARNING: isolated template residues lie outside the main aligned block "
            f"(N-term: {info.get('islands_lead', 0)}, C-term: {info.get('islands_trail', 0)}). "
            "That end was not trimmed. The alignment is fragmented; verify it before modelling.")
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n\n\n'.join(parts) + '\n')


def trim_terminal_overhangs(ali_path, min_block=5, max_overhang=MAX_OVERHANG,
                            trim_long=False):
    """Trim target residues at the termini that no template covers
    (signal peptides, disordered tails) so MODELLER does not have to invent
    them across a template-free gap.

    Flanks longer than max_overhang are only trimmed when trim_long=True.
    Returns dict: dropped, lead, trail (flank sizes before trimming),
    target_len, covered (target residues aligned to a template).
    """
    info = {"dropped": 0, "lead": 0, "trail": 0, "target_len": 0, "covered": 0,
            "cut_lead": "", "cut_trail": "", "islands_lead": 0, "islands_trail": 0,
            "kept": None}
    with open(ali_path) as fh:
        text = fh.read()

    recs = []
    for chunk in text.split('>P1;')[1:]:
        lines = [l.rstrip() for l in chunk.strip().splitlines()]
        code, header = lines[0].strip(), lines[1]
        seq = ''.join(lines[2:]).replace('*', '').replace(' ', '')
        recs.append([code, header, seq])

    templ = [r for r in recs if r[1].lower().startswith('structure')]
    targ = [r for r in recs if r[1].lower().startswith('sequence')]
    if not templ or not targ:
        return info
    tgt = targ[-1][2]
    n = len(tgt)
    covered = [any(r[2][i] != '-' for r in templ) for i in range(n)]
    info["target_len"] = sum(c != '-' for c in tgt)
    info["covered"] = sum(1 for i in range(n) if covered[i] and tgt[i] != '-')

    first = last = None
    run = 0
    for i in range(n):
        run = run + 1 if covered[i] else 0
        if run >= min_block:
            first = i - min_block + 1
            break
    run = 0
    for i in range(n - 1, -1, -1):
        run = run + 1 if covered[i] else 0
        if run >= min_block:
            last = i + min_block - 1
            break
    if first is None or last is None:
        return info

    lead = sum(1 for i in range(first) if not covered[i] and tgt[i] != '-')
    trail = sum(1 for i in range(last + 1, n) if not covered[i] and tgt[i] != '-')
    info["lead"], info["trail"] = lead, trail

    def _stub_ok(cols, at_start):
        # A flank may be trimmed only if it has no template residues, or just a
        # short (<=3) stub at the very end of the alignment (e.g. expression Met).
        # Otherwise trimming would glue distant target residues together.
        if not cols:
            return True
        if len(cols) > 3:
            return False
        edge = list(range(len(cols))) if at_start else list(range(n - len(cols), n))
        return cols == edge

    lead_cov = [i for i in range(first) if covered[i]]
    trail_cov = [i for i in range(last + 1, n) if covered[i]]
    lead_ok = _stub_ok(lead_cov, True)
    trail_ok = _stub_ok(trail_cov, False)
    info["islands_lead"] = 0 if lead_ok else len(lead_cov)
    info["islands_trail"] = 0 if trail_ok else len(trail_cov)
    cut_lead = lead_ok and (trim_long or lead <= max_overhang)
    cut_trail = trail_ok and (trim_long or trail <= max_overhang)

    keep = [i for i in range(n)
            if covered[i]
            or first <= i <= last
            or (i < first and not cut_lead)
            or (i > last and not cut_trail)]
    info["dropped"] = n - len(keep)
    info["kept"] = keep          # column indices (of the input file) that were kept
    if info["dropped"] == 0:
        return info
    kept = set(keep)
    info["cut_lead"] = ''.join(tgt[i] for i in range(first)
                               if i not in kept and tgt[i] != '-')
    info["cut_trail"] = ''.join(tgt[i] for i in range(last + 1, n)
                                if i not in kept and tgt[i] != '-')

    with open(ali_path, 'w') as fh:
        for code, header, seq in recs:
            s = ''.join(seq[i] for i in keep)
            fh.write(f">P1;{code}\n{header}\n")
            for k in range(0, len(s), 75):
                chunk = s[k:k + 75]
                fh.write(chunk + ('*' if k + 75 >= len(s) else '') + '\n')
            fh.write('\n')
    return info


def _report_to_html(text):
    """Monospace HTML version of the alignment report for the preview box:
    helix = red H, strand = blue E, trimmed columns = grey x."""
    helix = '<span style="color:#c1121f;font-weight:bold">H</span>'
    strand = '<span style="color:#1d4ed8;font-weight:bold">E</span>'
    trimmed = '<span style="color:#9ca3af">x</span>'
    rows = []
    for line in text.split('\n'):
        if line.startswith('H/E ') or line.startswith('TRIMMED '):
            label, body = line[:12], line[12:]
            parts = []
            for c in body:
                if c == 'H':
                    parts.append(helix)
                elif c == 'E':
                    parts.append(strand)
                elif c == 'x':
                    parts.append(trimmed)
                else:
                    parts.append(html.escape(c))
            rows.append(html.escape(label) + ''.join(parts))
        else:
            rows.append(html.escape(line))
    return ('<a name="alnreport"></a><pre style="font-family:Consolas,monospace;'
            'font-size:11pt;margin:0">' + '\n'.join(rows) + '</pre>')


class DynamicAlign(QMainWindow):
    def __init__(self, selected_templates=None):
        super().__init__()
        self.setWindowTitle('Modeller — Dynamic Alignment')
        self.setMinimumSize(1200, 720)
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
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
        
        btn_open = styled_button("Browse PIR File", "#9a8c98", "#d1495b")
        btn_open.clicked.connect(self.open_fasta)
        button_layout.addWidget(btn_open)

        btn_pdb = styled_button("Import Local PDBs", "#9a8c98", "#d1495b")
        btn_pdb.clicked.connect(self.import_pdbs)
        button_layout.addWidget(btn_pdb)

        button_layout.addSpacing(20)

        self.align_btn = styled_button("Run Alignment", "#4a4e69", "#22223b")
        self.align_btn.clicked.connect(self.do_align)
        self.align_btn.setEnabled(False)
        button_layout.addWidget(self.align_btn)

        self.download_btn = styled_button("Save Alignment", "#fca311", "#f5cb5c")
        self.download_btn.clicked.connect(self.download_ali)
        self.download_btn.setEnabled(False)
        button_layout.addWidget(self.download_btn)

        self.nextbtn = styled_button("Model Building", "#3c6e71", "#6b9080")
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
        preview_box.setFont(QFont("Segoe UI", 12))
        pv_layout = QVBoxLayout(preview_box)
        pv_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFont(QFont("Consolas", 11))
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
        output_box.setFont(QFont("Segoe UI", 12))
        out_layout = QVBoxLayout(output_box)
        self.msg_edit = QTextEdit()
        self.msg_edit.setReadOnly(True)
        self.msg_edit.setFont(QFont("Consolas", 11))
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
        tpl_label.setStyleSheet("color: #4a4e69; line-height: 1.0;")
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
            self.status_display.setFont(QFont("Segoe UI", 12))



    def open_fasta(self):
        path, _ = QFileDialog.getOpenFileName(self, "Browse PIR Format", "", "PIR Files (*.fasta *.fa *.ali *.pir);;All Files (*)")
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
            self.status_display.setFont(QFont("Segoe UI", 11))

    def open_nextpage(self):
        from .modelbuilding import ModelBuild
        aln_path = os.path.abspath('Alignment.ali')
        if os.path.exists(aln_path):
            # trimmed alignment + the folder holding the template PDBs (MODELLER looks there)
            self.modelwindow = ModelBuild(alnfile=aln_path, output_dir=os.path.dirname(aln_path))
        else:
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
            self.status_display.setText("Template PDBs ready")
            self.status_display.setFont(QFont("Segoe UI", 11))


    def do_align(self):
        if not self.upload_path or not self.selected_templates:
            QMessageBox.warning(self, "Missing Input",
                                "Please upload target sequence and select at least one template.")
            return

        self.msg_edit.clear()
        self.msg_edit.append("Running MODELLER Alignment...")
        self.progress.setValue(10)
        QApplication.processEvents()

        try:
            env = Environ()
            env.libs.topology.read(file='$(LIB)/top_heav.lib')
            env.libs.parameters.read(file='$(LIB)/par.lib')

            # --- Only use templates whose "Use" box is ticked ---
            active = []
            for i, tpl in enumerate(self.selected_templates):
                chk = self.templates_table.cellWidget(i, 0)
                if chk is None or chk.isChecked():
                    active.append(tpl)
            if not active:
                raise RuntimeError("No template ticked. Tick at least one template in the 'Use' column.")

            aln = Alignment(env)

            # --- Load templates correctly ---
            for tpl in active:
                pdb_id = tpl['PDB_ID']
                chain = tpl.get('Chain', 'A')
                pdbfile = f"{pdb_id}.pdb"

                if not os.path.exists(pdbfile):
                    raise FileNotFoundError(f"Missing PDB file: {pdbfile}")

                mdl = Model(
                    env,
                    file=pdbfile,
                    model_segment=(f"FIRST:{chain}", f"LAST:{chain}")
                )

                align_code = f"{pdb_id}_{chain}"
                aln.append_model(
                    mdl,
                    align_codes=align_code,
                    atom_files=pdbfile
                )

                self.msg_edit.append(f"Template loaded: {pdb_id} (chain {chain})")

            self.progress.setValue(40)
            QApplication.processEvents()

            # --- Add target sequence ---
            aln.append(file=self.upload_path, alignment_format='PIR')
            self.msg_edit.append("Target sequence added")

            # --- Structure-aware alignment ---
            if GAP_PENALTIES_1D:
                aln.align2d(max_gap_length=50, gap_penalties_1d=GAP_PENALTIES_1D)
            else:
                aln.align2d(max_gap_length=50)

            # --- Write alignment ---
            aln.write(file='Alignment.ali', alignment_format='PIR')

            # --- Keep the untrimmed, gapped alignment as the record ---
            shutil.copy('Alignment.ali', 'Alignment_full.ali')
            try:
                aln.write(file='Alignment_full.pap', alignment_format='PAP',
                          alignment_features='INDICES HELIX BETA')
            except Exception:
                aln.write(file='Alignment_full.pap', alignment_format='PAP')

            # --- Trim template-free termini (short ones automatically) ---
            info = trim_terminal_overhangs('Alignment.ali')
            pct = 100 * info["covered"] // max(info["target_len"], 1)
            self.msg_edit.append(
                f"Template covers {info['covered']}/{info['target_len']} target residues ({pct}%).")

            if ((info["lead"] > MAX_OVERHANG and not info["islands_lead"]) or
                    (info["trail"] > MAX_OVERHANG and not info["islands_trail"])):
                ans = QMessageBox.question(
                    self, "Partial template coverage",
                    f"Template covers only {info['covered']} of {info['target_len']} "
                    f"target residues ({pct}%).\n\n"
                    "Yes = model only the templated region (domain model)\n"
                    "No = keep full length (template-free parts will be unreliable)",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ans == QMessageBox.Yes:
                    more = trim_terminal_overhangs('Alignment.ali', trim_long=True)
                    info["dropped"] += more["dropped"]
                    info["cut_lead"] += more["cut_lead"]
                    info["cut_trail"] += more["cut_trail"]
                    if more["kept"] is not None:
                        info["kept"] = (more["kept"] if info["kept"] is None else
                                        [info["kept"][i] for i in more["kept"]])

            if info["islands_lead"] or info["islands_trail"]:
                self.msg_edit.append(
                    "WARNING: isolated template residues lie outside the main aligned block "
                    f"(N-term: {info['islands_lead']}, C-term: {info['islands_trail']}). "
                    "That end was NOT trimmed. The alignment looks fragmented; "
                    "check it before modelling.")

            if info["dropped"]:
                self.msg_edit.append(
                    f"Trimmed {info['dropped']} template-free terminal columns from alignment.")
                try:
                    aln = Alignment(env)
                    aln.append(file='Alignment.ali', alignment_format='PIR',
                               align_codes='all')
                except Exception:
                    pass  # keep untrimmed .pap preview if re-read fails
            aln.write(file='Alignment.pap', alignment_format='PAP')

            # --- Human-readable report: full vs used alignment + trimmed residues ---
            try:
                write_alignment_report('Alignment_full.ali', 'Alignment.ali',
                                       'Alignment_report.txt', info)
                self.msg_edit.append("Alignment report written: Alignment_report.txt")
            except Exception as rep_err:
                self.msg_edit.append(f"(Could not write alignment report: {rep_err})")

            self.progress.setValue(90)
            QApplication.processEvents()

            # --- Preview: full alignment with helix/strand and trimmed-column rows ---
            if info["dropped"]:
                self.msg_edit.append(
                    "Template-free termini are excluded from model building. "
                    "Full alignment: Alignment_full.ali | used for modelling: Alignment.ali")
            self.msg_edit.append(
                '<span style="color:#c1121f"><b>H</b></span> helix (template) &nbsp;&nbsp; '
                '<span style="color:#1d4ed8"><b>E</b></span> strand (template) &nbsp;&nbsp; '
                '<span style="color:#9ca3af">x</span> column trimmed for model building')
            try:
                with open('Alignment_report.txt', 'r', encoding='utf-8') as f:
                    report_text = f.read()
                self.msg_edit.append(_report_to_html(report_text))
                self.msg_edit.scrollToAnchor('alnreport')
            except Exception:
                with open('Alignment_full.pap', 'r', encoding='utf-8') as f:
                    self.msg_edit.append(f.read())

            self.progress.setValue(100)
            self.status_display.setText("Alignment completed successfully")
            self.download_btn.setEnabled(True)

        except Exception as e:
            self.msg_edit.append(f"\n❌ Alignment failed:\n{str(e)}")
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
        base = os.path.splitext(path)[0]
        for src_name, suffix in (('Alignment_full.ali', '_full.ali'),
                                 ('Alignment_report.txt', '_report.txt')):
            if os.path.exists(src_name):
                shutil.copy(src_name, base + suffix)
        QMessageBox.information(
            self, "Saved",
            f"Saved: {path}\n(+ {os.path.basename(base)}_full.ali and "
            f"{os.path.basename(base)}_report.txt)")
        self.status_display.setText(f"Saved {os.path.basename(path)} successfully.")


def main():
    app = QApplication(sys.argv)
    window = DynamicAlign()
    window.show()
    # sys.exit(app.exec_())

if __name__ == '__main__':
    main()