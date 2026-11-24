from PyQt5.QtWidgets import (QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QApplication, QTableWidget, QTableWidgetItem, QCheckBox, QHeaderView, 
                             QFileDialog, QMessageBox, QProgressBar, QFrame, QSizePolicy, QTabWidget, QSplitter, QLineEdit)
from PyQt5.QtGui import QFont, QPalette, QColor, QLinearGradient, QBrush, QIcon, QTextCursor
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import sys
from io import StringIO, BytesIO
import requests
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')
import zipfile
import time
import hashlib
import pandas as pd
from .dynamic_align import DynamicAlign
import html
from .chatmodel import Chatbot, BlastManager
from Bio import SeqIO

NCBI_TOOL = "vasuki-mitbio"

# Template search backend. NCBI's BLAST API queue can stall for 10+ min; the RCSB PDB
# sequence search (MMseqs2) answers in seconds. If RCSB fails, NCBI BLAST is used as fallback.
# Set to False to use NCBI BLAST only.
USE_RCSB_FIRST = True
RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_GRAPHQL_URL = "https://data.rcsb.org/graphql"
RCSB_ENTITY_URL = "https://data.rcsb.org/rest/v1/core/polymer_entity"


def hit_metrics(hsps, query_len):
    """Return (identity %, query coverage %) for one hit; '' if it can't be computed."""
    ident_pct = cov_pct = ""
    try:
        align_len = float(hsps.get("align_len") or 0)
        if align_len:
            ident_pct = round(100.0 * float(hsps.get("identity", 0)) / align_len, 1)
    except (TypeError, ValueError):
        pass
    try:
        q_from, q_to = hsps.get("query_from"), hsps.get("query_to")
        if q_from and q_to and query_len:
            cov_pct = round(100.0 * (int(q_to) - int(q_from) + 1) / float(query_len), 1)
    except (TypeError, ValueError):
        pass
    return ident_pct, cov_pct


class BlastWorker(QThread):
    result_ready = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, fasta_sequence, cache):
        super().__init__()
        self.fasta_sequence = fasta_sequence
        self.cache = cache
        self.query_hash = hashlib.md5(fasta_sequence.encode()).hexdigest()
        self.base_url = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"

    def run(self):
        print("[blast.py v8] BLAST worker started")
        if self.query_hash in self.cache:
            self.result_ready.emit(self.cache[self.query_hash])
            self.progress.emit(100)
            return

        try:
            # Validate FASTA sequence
            try:
                record = SeqIO.read(StringIO(self.fasta_sequence), "fasta")
            except Exception as e:
                self.result_ready.emit(f"Error: Invalid FASTA format: {str(e)}")
                self.progress.emit(100)
                return

            # Fast path: RCSB PDB sequence search (no NCBI queue)
            self.progress.emit(10)
            if USE_RCSB_FIRST:
                try:
                    json_content = self.rcsb_search(str(record.seq))
                    self.cache[self.query_hash] = json_content
                    self.result_ready.emit(json_content)
                    self.progress.emit(100)
                    return
                except Exception as e:
                    print(f"[blast.py v8] RCSB search failed ({type(e).__name__}: {e}); falling back to NCBI BLAST")
                    self.progress.emit(10)

            # Step 1: Submit the BLAST search (CMD=Put)
            submit_params = {
                "CMD": "Put",
                "PROGRAM": "blastp",
                "DATABASE": "pdb",
                "QUERY": self.fasta_sequence, 
                "FORMAT_TYPE": "JSON2_S",
                "EXPECT": "1e-5",
                "HITLIST_SIZE": "50",
                "BLAST_PROGRAMS": "kmerBlastp",  # Quick BLASTP (website default)
                "tool": NCBI_TOOL
            }
            classic_params = {k: v for k, v in submit_params.items() if k != "BLAST_PROGRAMS"}
            rid = rtoe = None
            for attempt_params in (submit_params, classic_params):
                mode = "Quick BLASTP" if "BLAST_PROGRAMS" in attempt_params else "classic blastp"
                try:
                    submit_response = requests.post(self.base_url, data=attempt_params, timeout=60)
                    submit_response.raise_for_status()
                    print(f"Submit Response ({mode}):", submit_response.text[:500])
                    rid, rtoe = self.parse_rid_rtoe(submit_response.text)
                except requests.exceptions.RequestException as e:
                    print(f"Submit failed ({mode}): {type(e).__name__}: {e}")
                    rid = None
                if rid:
                    print(f"Submitted using {mode}")
                    break
                print(f"No RID from {mode}, trying fallback...")
            print(f"RID={rid}, RTOE={rtoe}")
            if not rid:
                raise ValueError("Failed to submit BLAST search (no RID returned)")

            self.progress.emit(20)

            # Wait initial estimated time (capped so it can't hang the UI)
            time.sleep(min(int(rtoe), 20) if rtoe and rtoe.isdigit() else 10)

            # Step 2: Poll for status (with hard timeout)
            MAX_WAIT = 1800  # seconds (30 min)
            poll_start = time.time()
            while True:
                elapsed = time.time() - poll_start
                if elapsed > MAX_WAIT:
                    raise TimeoutError(f"BLAST timed out after {MAX_WAIT}s (RID={rid})")

                status_response = self.get_with_retry(
                    self.id_params({"CMD": "Get", "FORMAT_OBJECT": "SearchInfo", "RID": rid})
                )

                status = self.parse_status(status_response.text)
                print(f"Status: {status} ({int(elapsed)}s)")

                if status == "READY":
                    self.progress.emit(90)
                    break
                elif status in ("FAILED", "UNKNOWN"):
                    raise ValueError(f"BLAST search failed with status: {status} (RID={rid})")

                self.progress.emit(20 + int(60 * elapsed / MAX_WAIT))
                time.sleep(60)  # NCBI guideline: max 1 poll/min per RID

            # Step 3: Fetch results
            results_params = self.id_params({
                "CMD": "Get",
                "FORMAT_TYPE": "JSON2_S",
                "RID": rid
            })
            results_response = self.get_with_retry(results_params)

        
            print("Results Response (first 500 chars):", results_response.text[:500])

            
            try:
                json_content = results_response.text
                json.loads(json_content)  
            except json.JSONDecodeError:
                
                try:
                    zip_buffer = BytesIO(results_response.content)
                    with zipfile.ZipFile(zip_buffer) as myzip:
                        file_list = myzip.namelist()
                        json_content = None
                        for fname in file_list:
                            if fname.endswith('_1.json'):
                                with myzip.open(fname) as stream:
                                    json_content = stream.read().decode('utf-8')
                        
                        
                                break
                        if not json_content:
                            raise ValueError("No JSON file found in the zip archive")
                except zipfile.BadZipFile:
                    snippet = results_response.text[:300].strip() or "(empty response)"
                    raise ValueError(f"NCBI did not return JSON (RID={rid}). Received: {snippet}")

            # Cache and emit result
            self.cache[self.query_hash] = json_content
            self.result_ready.emit(json_content)
            self.progress.emit(100)

        except requests.exceptions.RequestException as e:
            detail = f"{type(e).__name__}: {e}"
            if getattr(e, "response", None) is not None:
                detail += f" | Server said: {e.response.text[:200].strip()}"
            print("BLAST network error:", detail)
            self.result_ready.emit(f"Error: Network issue during BLAST: {detail}")
            self.progress.emit(100)
        except Exception as e:
            self.result_ready.emit(f"Error during BLAST: {str(e)}")
            self.progress.emit(100)

    def rcsb_search(self, sequence):
        """RCSB PDB sequence search. Returns JSON text shaped like NCBI's JSON2_S,
        so show_blast_table() works unchanged."""
        t0 = time.time()
        seq = re.sub(r"[^A-Za-z]", "", sequence).upper()
        payload = {
            "query": {
                "type": "terminal",
                "service": "sequence",
                "parameters": {
                    "value": seq,
                    "evalue_cutoff": 1e-5,
                    "identity_cutoff": 0,
                    "sequence_type": "protein",
                },
            },
            "return_type": "polymer_entity",
            "request_options": {
                "scoring_strategy": "sequence",
                "results_verbosity": "verbose",
                "paginate": {"start": 0, "rows": 50},
            },
        }
        resp = requests.post(RCSB_SEARCH_URL, json=payload, timeout=60)
        if resp.status_code == 204:
            result_set = []
        else:
            resp.raise_for_status()
            result_set = resp.json().get("result_set", [])
        print(f"[blast.py v8] RCSB search: {len(result_set)} hits in {time.time() - t0:.1f}s")
        self.progress.emit(50)

        ids = []
        for item in result_set:
            ident = item.get("identifier", "") if isinstance(item, dict) else str(item)
            if "_" in ident:
                ids.append(ident)
        meta = self.rcsb_entity_meta(ids)
        self.progress.emit(85)

        hits = []
        for item in result_set:
            if not isinstance(item, dict):
                continue
            ident = item.get("identifier", "")
            if ident not in meta:
                print(f"[blast.py v8] Skipping {ident}: no chain info")
                continue
            chain, sciname = meta[ident]
            entry = ident.split("_")[0]

            node = {}
            for svc in item.get("services", []):
                nodes = svc.get("nodes", [])
                if nodes:
                    node = nodes[0]
                    break
            mc = node.get("match_context") or {}
            if isinstance(mc, list):
                mc = mc[0] if mc else {}
            frac = float(mc.get("sequence_identity", 0) or 0)
            aln_len = int(mc.get("alignment_length", 0) or 0)
            ident_count = int(round(frac * aln_len))
            hits.append({
                "num": len(hits) + 1,
                "description": [{
                    "id": f"pdb|{entry}|{chain}",
                    "accession": f"{entry}_{chain}",
                    "title": "",
                    "sciname": sciname,
                }],
                "hsps": [{
                    "score": mc.get("bitscore", node.get("original_score", "")),
                    "evalue": mc.get("evalue", ""),
                    "identity": ident_count,
                    "align_len": aln_len,
                    "query_from": mc.get("query_beg"),
                    "query_to": mc.get("query_end"),
                }],
            })
        return json.dumps({"BlastOutput2": [{"report": {"results": {"search": {"query_len": len(seq), "hits": hits}}}}]})

    def rcsb_entity_meta(self, ids):
        """Map entity id (e.g. 4INS_1) -> (author chain id, scientific name)."""
        meta = {}
        if not ids:
            return meta
        query = ("query($ids:[String!]!){polymer_entities(entity_ids:$ids){rcsb_id "
                 "rcsb_polymer_entity_container_identifiers{auth_asym_ids asym_ids} "
                 "rcsb_entity_source_organism{ncbi_scientific_name}}}")
        try:
            gr = requests.post(RCSB_GRAPHQL_URL, json={"query": query, "variables": {"ids": ids}}, timeout=60)
            gr.raise_for_status()
            for ent in ((gr.json().get("data") or {}).get("polymer_entities") or []):
                if ent and ent.get("rcsb_id"):
                    meta[ent["rcsb_id"]] = self._parse_entity(ent)
        except Exception as e:
            print(f"[blast.py v8] RCSB GraphQL failed ({type(e).__name__}: {e}); using per-entity lookups")
        for ident in ids:
            if ident in meta:
                continue
            entry, _, entity = ident.partition("_")
            try:
                er = requests.get(f"{RCSB_ENTITY_URL}/{entry}/{entity}", timeout=30)
                er.raise_for_status()
                meta[ident] = self._parse_entity(er.json())
            except Exception as e:
                print(f"[blast.py v8] Entity lookup failed for {ident}: {type(e).__name__}: {e}")
        return meta

    @staticmethod
    def _parse_entity(ent):
        cid = ent.get("rcsb_polymer_entity_container_identifiers") or {}
        chains = cid.get("auth_asym_ids") or cid.get("asym_ids") or []
        orgs = ent.get("rcsb_entity_source_organism") or []
        sciname = (orgs[0] or {}).get("ncbi_scientific_name", "") if orgs else ""
        return (chains[0] if chains else "A", sciname or "")

    def get_with_retry(self, params, tries=5):
        last = None
        for i in range(tries):
            try:
                r = requests.get(self.base_url, params=params, timeout=60)
                r.raise_for_status()
                return r
            except requests.exceptions.RequestException as e:
                last = e
                print(f"Request failed ({type(e).__name__}: {e}); retry {i + 1}/{tries}")
                time.sleep(10 * (i + 1))
        raise last

    def id_params(self, params):
        params["tool"] = NCBI_TOOL
        return params

    def parse_rid_rtoe(self, text):
        rid_m = re.search(r"RID\s*=\s*(\S+)", text)
        rtoe_m = re.search(r"RTOE\s*=\s*(\d+)", text)
        return (rid_m.group(1) if rid_m else None,
                rtoe_m.group(1) if rtoe_m else None)

    def parse_status(self, text):
        m = re.search(r"Status=(\w+)", text)
        return m.group(1) if m else "UNKNOWN"

class BlastWindow(QMainWindow):
    def __init__(self, fasta_sequence=""):
        super().__init__()
        self.setWindowTitle('Run BLAST')
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
        self.fasta_sequence = fasta_sequence
        self.cache = {}
        try:
            self.chatbot = Chatbot()
        except Exception as e:
            print(f"Chatbot initialization failed: {e}")
            self.chatbot = None

        self.tableWidget = None 
        self.initGUI()

    def initGUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        # Title 
        title = QLabel()
        title.setText("""
         <span style="font-family:\'Source Sans Pro\'; font-size:20pt; font-weight:400; color:#924511;">BLAST</span><br>""")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setWordWrap(True)
        # title.setFixedHeight(60)
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

        # Splitter 
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel 
        left_frame = QFrame()
        left_label = QLabel('Controls')
        left_label.setFont(QFont("Segoe UI", 14, QFont.Medium))
        left_label.setStyleSheet("color: #4a4e69; line-height: 1.0;")
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
            btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(45)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color1};
                    color: white;
                    border-radius: 10px; 
                    padding: 8px 18px;
                }}
                QPushButton:pressed {{
                    background-color: {color2};
                }}
            """)
            return btn 
        
        blast_btn = styled_button("Run BLAST","#9a8c98", "#d1495b")
        blast_btn.clicked.connect(self.BLASTClicked)
        button_layout.addWidget(blast_btn)

        download_btn = styled_button("Download PDBs","#9a8c98", "#d1495b")
        download_btn.clicked.connect(self.download_selected_pdbs)
        button_layout.addWidget(download_btn)

        proceed_btn = styled_button("Align","#9a8c98", "#d1495b")
        proceed_btn.clicked.connect(self.show_align_page)
        button_layout.addWidget(proceed_btn)

        left_layout.addLayout(button_layout)
        left_layout.addStretch()
        splitter.addWidget(left_frame)

        # Center Panel 
        center_tabs = QTabWidget()
        center_tabs.tabBar().setFont(QFont("Segoe UI", 12, QFont.Medium))
        center_tabs.setMinimumWidth(400)
        splitter.addWidget(center_tabs)

        # Add tabs
        seq_tab = QWidget()
        seq_layout = QVBoxLayout(seq_tab)
        self.seq_view = QTextEdit()
        self.seq_view.setText(self.fasta_sequence)
        self.seq_view.setReadOnly(True)
        self.seq_view.setFont(QFont("Consolas", 12))
        self.seq_view.setStyleSheet("""
            QTextEdit {
                background-color: #f2e9e4;
                color: #4a4e69;
                border: 2px #22223b ;
                border-radius: 10px;
                padding: 10px;
            }
            QTextEdit:focus {
                border: 2px  #22223b;
                background-color: #f2e9e4;
            }
        """)
        
        seq_layout.addWidget(self.seq_view)
        center_tabs.addTab(seq_tab, "Sequence")
        

        self.output_tab = QWidget()
        self.output_layout = QVBoxLayout(self.output_tab)
        center_tabs.addTab(self.output_tab, "BLAST Output")
        

        # Right Frame 
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
        self.chattext.setPlaceholderText("ChatBot responses will appear here...")
        self.chattext.setFont(QFont("Segoe UI", 11))
        right_layout.addWidget(self.chattext)

        # Chat Input 
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("How can I assist you?")
        self.chat_input.setFont(QFont("Segoe UI", 11))
        self.chat_input.setMinimumHeight(40)

        self.chat_input.returnPressed.connect(self.send_chat_message)
        input_layout.addWidget(self.chat_input)

        send_btn = QPushButton()
        send_btn = styled_button("Send", "#9a8c98", "#d1495b")
        send_btn.clicked.connect(self.send_chat_message)
        input_layout.addWidget(send_btn)

        right_layout.addLayout(input_layout)
        splitter.addWidget(right_frame)

        splitter.setSizes([200, 900, 350])
        self.main_layout.addWidget(splitter)
        self.main_layout.setStretchFactor(splitter, 1)

        #Status and Progress 
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(100)
        self.main_layout.addWidget(self.status_display)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)

    def send_chat_message(self):
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
        try:
            if not self.chatbot:
                response = "Chatbot is unavailable. The Qwen model failed to initialise (see console)."
            else:
                response = self.chatbot.generate_response(user_msg)    
                
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


    def BLASTClicked(self):
        self.status_display.setPlainText("Running BLAST, please wait... (This may take a while due to remote server query)")
        self.status_display.setFont(QFont("Segoe UI", 12))
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.worker = BlastWorker(self.fasta_sequence, self.cache)
        self.worker.result_ready.connect(self.HandleResult)
        self.worker.progress.connect(self.update_progress)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        if value == 100:
            self.progress_bar.setVisible(False)

    def HandleResult(self, result):
        if self.tableWidget:
            self.output_layout.removeWidget(self.tableWidget)
            self.tableWidget.deleteLater()
            self.tableWidget = None
        if not result or result.startswith("Error"):
            self.status_display.setPlainText(result or "Error: empty response from BLAST")
            self.status_display.setFont(QFont("Segoe UI", 12))
            self.progress_bar.setVisible(False)
            return
        try:
            data = json.loads(result)
            self.status_display.setPlainText('BLAST Finished, Preparing Result Table...')
            self.status_display.setFont(QFont("Segoe UI", 12))
            self.show_blast_table(data)
        except json.JSONDecodeError as e:
            print("[blast.py v8] Non-JSON result:", result[:300])
            self.status_display.setPlainText(f"Error: Failed to parse BLAST results as JSON: {str(e)}\nReceived: {result[:300]}")
            self.status_display.setFont(QFont("Segoe UI", 12))
            self.progress_bar.setVisible(False)
        except Exception as e:
            self.status_display.setPlainText(f"Error: {str(e)}")
            self.progress_bar.setVisible(False)

    def show_blast_table(self, data):
     try:
        blast_output = data['BlastOutput2']
        hits = blast_output[0]['report']['results']['search']['hits'] if isinstance(blast_output, list) else blast_output['report']['results']['search']['hits']
        search_obj = (blast_output[0] if isinstance(blast_output, list) else blast_output)['report']['results']['search']
        query_len = search_obj.get('query_len', 0) or 0
        if not hits:
            self.status_display.setPlainText("No hits found in the BLAST results.")
            return

     except KeyError as e:
        self.status_display.setPlainText(f"Error processing BLAST results: {str(e)}")
        return

    # Updated headers to include Chain
     headers = ["Select", "PDB_ID", "Chain", "Accession", "Scientific_Name", "Score", "E_Value", "Identity", "Identity_%", "Coverage_%"]
     self.tableWidget = QTableWidget(len(hits), len(headers))
     self.tableWidget.setHorizontalHeaderLabels(headers)
     self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

     blast_rows = []

     for row_idx, hit in enumerate(hits):
        desc = hit['description'][0]
        pdb_id = desc.get('id', '').split('|')[1] if 'id' in desc and '|' in desc.get('id', '') else ''
        # Extract chain from description (PDB format: |PDB|id|chain|...)
        chain = desc.get('id', '').split('|')[2] if 'id' in desc and '|' in desc.get('id', '') and len(desc.get('id', '').split('|')) > 2 else 'A'
        accession = desc.get('accession', '')
        sciname = desc.get('sciname', '')
        hsps = hit['hsps'][0]
        score = hsps.get('score', '')
        evalue = hsps.get('evalue', '')
        identity = hsps.get('identity', '')
        ident_pct, cov_pct = hit_metrics(hsps, query_len)

        checkbox_widget = QWidget()
        checkbox_layout = QHBoxLayout(checkbox_widget)
        checkbox = QCheckBox()
        checkbox_layout.addWidget(checkbox, alignment=Qt.AlignCenter)
        checkbox_widget.setLayout(checkbox_layout)
        self.tableWidget.setCellWidget(row_idx, 0, checkbox_widget)

        # Updated to include Chain column
        self.tableWidget.setItem(row_idx, 1, QTableWidgetItem(str(pdb_id)))
        self.tableWidget.setItem(row_idx, 2, QTableWidgetItem(str(chain)))  # New Chain column
        self.tableWidget.setItem(row_idx, 3, QTableWidgetItem(str(accession)))
        self.tableWidget.setItem(row_idx, 4, QTableWidgetItem(str(sciname)))
        self.tableWidget.setItem(row_idx, 5, QTableWidgetItem(str(score)))
        self.tableWidget.setItem(row_idx, 6, QTableWidgetItem(str(evalue)))
        self.tableWidget.setItem(row_idx, 7, QTableWidgetItem(str(identity)))
        self.tableWidget.setItem(row_idx, 8, QTableWidgetItem(str(ident_pct)))
        self.tableWidget.setItem(row_idx, 9, QTableWidgetItem(str(cov_pct)))

        blast_rows.append([pdb_id, chain, accession, sciname, score, evalue, identity, ident_pct, cov_pct])
     

     self.output_layout.addWidget(self.tableWidget)
     self.status_display.setPlainText('Blast Results are ready. Select templates and proceed')

     # Set blast manager for chatbot
     if self.chatbot:
         df = pd.DataFrame(blast_rows, columns=headers[1:])
         from .chatmodel import BlastManager
         self.chatbot.blast_manager = BlastManager(df)


    def get_selected_templates(self):
     selected = []
     if self.tableWidget:
        for row in range(self.tableWidget.rowCount()):
            widget = self.tableWidget.cellWidget(row, 0)
            if widget:
                checkbox = widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    template = {
                        'PDB_ID': self.tableWidget.item(row, 1).text(),
                        'Chain': self.tableWidget.item(row, 2).text(),
                        'Accession': self.tableWidget.item(row, 3).text(),
                        'Scientific_Name': self.tableWidget.item(row, 4).text(),
                        'Score': self.tableWidget.item(row, 5).text(),
                        'E_Value': self.tableWidget.item(row, 6).text(),
                        'Identity': self.tableWidget.item(row, 7).text(),
                        'Identity_%': self.tableWidget.item(row, 8).text(),
                        'Coverage_%': self.tableWidget.item(row, 9).text()
                    }
                    selected.append(template)
     return selected

    def download_selected_pdbs(self):
        selected = self.get_selected_templates()
        if not selected:
            QMessageBox.warning(self, "No Selection", "No templates selected for download.")
            return

        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if not folder:
            return

        import os
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # session with retries/backoff
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))

        failed = []
        for t in selected:
            pdb_id = t['PDB_ID']
            url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            try:
                # increase timeout and stream to avoid large-memory usage
                with session.get(url, timeout=30, stream=True) as response:
                    response.raise_for_status()
                    out_path = os.path.join(folder, f"{pdb_id}.pdb")
                    with open(out_path, 'wb') as fh:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                fh.write(chunk)
            except requests.exceptions.RequestException as e:
                failed.append(f"{pdb_id}: {e}")

        if failed:
            QMessageBox.warning(self, "Download Complete with errors",
                                "Some downloads failed:\n" + "\n".join(failed))
        else:
            QMessageBox.information(self, "Download Complete", "Selected PDB files downloaded successfully.")

    def show_align_page(self):
     selected_templates = self.get_selected_templates()
     if not selected_templates:
        QMessageBox.warning(self, "No Selection", "Please select at least one template.")
        return
     fasta_text = self.seq_view.toPlainText()
     self.align_window = DynamicAlign(selected_templates)
     self.align_window.show()

def main():
    app = QApplication(sys.argv)
    window = BlastWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()