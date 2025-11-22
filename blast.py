
from PyQt5.QtWidgets import (QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QApplication, QTableWidget, QTableWidgetItem, QCheckBox, QHeaderView, 
                             QFileDialog, QMessageBox, QProgressBar, QFrame, QSizePolicy, QTabWidget, QSplitter, QLineEdit)
from PyQt5.QtGui import QFont, QPalette, QColor, QLinearGradient, QBrush, QIcon, QTextCursor
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import sys
from Bio import SeqIO
from io import StringIO, BytesIO
import requests
import json
import zipfile
import time
import hashlib
from dynamic_align import DynamicAlign
from chatmodel import Chatbot

class BlastWorker(QThread):
    finished = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, fasta_sequence, cache):
        super().__init__()
        self.fasta_sequence = fasta_sequence
        self.cache = cache
        self.query_hash = hashlib.md5(fasta_sequence.encode()).hexdigest()
        self.base_url = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"

    def run(self):
        if self.query_hash in self.cache:
            self.finished.emit(self.cache[self.query_hash])
            self.progress.emit(100)
            return

        try:
            # Validate FASTA sequence
            try:
                record = SeqIO.read(StringIO(self.fasta_sequence), "fasta")
            except Exception as e:
                self.finished.emit(f"Error: Invalid FASTA format: {str(e)}")
                self.progress.emit(100)
                return

            # Step 1: Submit the BLAST search (CMD=Put)
            self.progress.emit(10)
            submit_params = {
                "CMD": "Put",
                "PROGRAM": "blastp",
                "DATABASE": "pdb",
                "QUERY": self.fasta_sequence, 
                "FORMAT_TYPE": "JSON2_S",
                "EXPECT": "1e-5",
                "HITLIST_SIZE": "50"
            }
            submit_response = requests.get(self.base_url, params=submit_params, timeout=30)
            submit_response.raise_for_status()

            # Log raw response for debugging
            print("Submit Response:", submit_response.text[:500]) 

            # Parse RID and RTOE
            rid, rtoe = self.parse_rid_rtoe(submit_response.text)
            if not rid:
                raise ValueError("Failed to parse RID from submission response")

            self.progress.emit(20)

            # Wait initial estimated time
            time.sleep(int(rtoe) if rtoe else 10)

            # Step 2: Poll for status
            while True:
                status_params = {
                    "CMD": "Get",
                    "FORMAT_OBJECT": "SearchInfo",
                    "RID": rid
                }
                status_response = requests.get(self.base_url, params=status_params, timeout=30)
                status_response.raise_for_status()

                # Log status response
                print("Status Response:", status_response.text[:500])

                status = self.parse_status(status_response.text)
                if status == "READY":
                    self.progress.emit(90)
                    break
                elif status in ["FAILED", "UNKNOWN"]:
                    raise ValueError(f"BLAST search failed with status: {status}")

                self.progress.emit(min(self.progress_bar_value() + 10, 80))
                time.sleep(5)  

            # Step 3: Fetch results
            results_params = {
                "CMD": "Get",
                "FORMAT_TYPE": "JSON2_S",
                "RID": rid
            }
            results_response = requests.get(self.base_url, params=results_params, timeout=30)
            results_response.raise_for_status()

        
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
                    raise ValueError("Response is not a valid ZIP archive")

            # Cache and emit result
            self.cache[self.query_hash] = json_content
            self.finished.emit(json_content)
            self.progress.emit(100)

        except requests.exceptions.RequestException as e:
            self.finished.emit(f"Error: Network issue during BLAST: {str(e)}")
            self.progress.emit(100)
        except Exception as e:
            self.finished.emit(f"Error during BLAST: {str(e)}")
            self.progress.emit(100)

    def parse_rid_rtoe(self, text):
        rid = None
        rtoe = None
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("RID ="):
                rid = line.split("=")[1].strip()
            elif line.startswith("RTOE ="):
                rtoe = line.split("=")[1].strip()
        return rid, rtoe

    def parse_status(self, text):
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("Status="):
                return line.split("=")[1].strip()
        return "UNKNOWN"

    def progress_bar_value(self):
        return 20

class BlastWindow(QMainWindow):
    def __init__(self, fasta_sequence=""):
        super().__init__()
        self.setWindowTitle('Run BLAST')
        self.setMinimumSize(1000, 700)
        self.setWindowIcon(QIcon("D:/Shreya_VS_projects/Modeller_automation/Images/Screenshot 2025-11-09 171245.png"))
        self.fasta_sequence = fasta_sequence
        self.cache = {} 
        self.chatbot = Chatbot() 
        self.tableWidget = None 
        self.initGUI()

    def initGUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        # Title 
        title = QLabel()
        title.setText("""
         <span style="font-family:\'Source Sans Pro\'; font-size:20pt; font-weight:400; color:#924511;">BLAST</span><br>
                            """)
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
        chatbot_label.setAlignment(Qt.AlignLeft)
        right_layout.addWidget(chatbot_label)

        self.chattext = QTextEdit()
        self.chattext.setReadOnly(True)
        self.chattext.setPlaceholderText("ChatBot responses will appear here...")
        right_layout.addWidget(self.chattext)

        # Chat Input 
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("How can I assist you?")
        self.chat_input.setFont(QFont("Segoe UI", 10))
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

        # Append user message
        self.chattext.append(f"You: {user_msg}")
        self.chattext.setFont(QFont("Segoe UI", 10))
        self.chat_input.clear()

        # Generate and append bot response
        try:
            response = self.chatbot.generate_response(user_msg)
            self.chattext.append(f"Bot: {response}")
        except Exception as e:
            self.chattext.append(f"Bot: Error generating response: {e}")

        # Scroll to end
        self.chattext.moveCursor(QTextCursor.End)
        self.chattext.ensureCursorVisible()


    def BLASTClicked(self):
        self.status_display.setPlainText("Running BLAST, please wait... (This may take a while due to remote server query)")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.worker = BlastWorker(self.fasta_sequence, self.cache)
        self.worker.finished.connect(self.HandleResult)
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
        try:
            data = json.loads(result)
            self.status_display.setPlainText('BLAST Finished, Preparing Result Table...')
            self.show_blast_table(data)
        except json.JSONDecodeError as e:
            self.status_display.setPlainText(f"Error: Failed to parse BLAST results as JSON: {str(e)}")
            self.progress_bar.setVisible(False)
        except Exception as e:
            self.status_display.setPlainText(f"Error: {str(e)}")
            self.progress_bar.setVisible(False)

    def show_blast_table(self, data):
     try:
        blast_output = data['BlastOutput2']
        hits = blast_output[0]['report']['results']['search']['hits'] if isinstance(blast_output, list) else blast_output['report']['results']['search']['hits']
        if not hits:
            self.status_display.setPlainText("No hits found in the BLAST results.")
            return
     except KeyError as e:
        self.status_display.setPlainText(f"Error processing BLAST results: {str(e)}")
        return

    # Updated headers to include Chain
     headers = ["Select", "PDB_ID", "Chain", "Accession", "Scientific_Name", "Score", "E_Value", "Identity", "Positive", "Gaps"]
     self.tableWidget = QTableWidget(len(hits), len(headers))
     self.tableWidget.setHorizontalHeaderLabels(headers)
     self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

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
        positive = hsps.get('positive', '')
        gaps = hsps.get('gaps', '')

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
        self.tableWidget.setItem(row_idx, 8, QTableWidgetItem(str(positive)))
        self.tableWidget.setItem(row_idx, 9, QTableWidgetItem(str(gaps))) 
     

     self.output_layout.addWidget(self.tableWidget)
     self.status_display.setPlainText('Blast Results are ready. Select templates and proceed')


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
                        'Positive': self.tableWidget.item(row, 8).text(),
                        'Gaps': self.tableWidget.item(row, 9).text()
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