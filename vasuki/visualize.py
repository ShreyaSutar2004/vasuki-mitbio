from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt5.QtGui import QIcon
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl
import tempfile, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, 'Images')

class Visualizer(QWidget):
    def __init__(self, output_dir):
        super().__init__()
        self.setWindowTitle("Protein Model Visualizer")
        self.setWindowIcon(QIcon(os.path.join(IMAGE_DIR, "Screenshot 2025-11-09 171245.png")))
        self.output_dir = output_dir

        # Create main layout ONCE here
        self.layout = QVBoxLayout(self)
        self.web = QWebEngineView()
        self.info_label = QLabel("Model details will appear here.")
        self.info_label.setWordWrap(True)

        # Give the label a small stretch and the web view a larger stretch
        # so the model area occupies ~80% and the title/label ~20%.
        self.layout.addWidget(self.info_label, 1)
        self.layout.addWidget(self.web, 4)
        self.setLayout(self.layout)

    def visualize_model(self, model):
        """Load model PDB content into an HTML page and show with 3Dmol.js."""
        filename = model.get('filename', '')
        pdb_path = os.path.join(self.output_dir, filename)

        if not os.path.exists(pdb_path):
            self.info_label.setText(f"File not found: {pdb_path}")
            return

        # read PDB text
        try:
            with open(pdb_path, 'r', encoding='utf-8') as fh:
                pdb_text = fh.read()
        except Exception as e:
            self.info_label.setText(f"Could not read file: {e}")
            return

        import json
        pdb_js = json.dumps(pdb_text)

        html_content = f"""<!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>3Dmol Viewer</title>
    <script src="https://3dmol.org/build/3Dmol-min.js"></script>
    <style>html,body,#container{{height:100%; margin:0; font-size:14px; font-family: Arial}}</style>
    </head>
    <body>
    <div id="container" style="width:100%; height:100%;"></div>
    <script>
        const pdbData = {pdb_js};
        const viewer = $3Dmol.createViewer('container', {{ backgroundColor: 'white' }});
        viewer.addModel(pdbData, 'pdb');             // load model from string
        viewer.setStyle({{}}, {{cartoon: {{color: 'spectrum'}}}});
        viewer.zoomTo();
        viewer.render();
        // optional: allow rotate with mouse and show info
    </script>
    </body>
    </html>
    """

        # write temporary html and load it into the web view
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        try:
            tmp.write(html_content.encode('utf-8'))
            tmp.flush()
        finally:
            tmp.close()

        self.web.load(QUrl.fromLocalFile(tmp.name))
        self.info_label.setText(f"Visualizing: {filename}")
        self.show()
