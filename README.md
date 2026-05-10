# VASUKI: Automated GUI for Comparative Protein Modeling

[![PyPI version](https://badge.fury.io/py/vasuki-mitbio.svg)](https://pypi.org/project/vasuki-mitbio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

---

## What is VASUKI?

**VASUKI** (named after the mythical serpent king) is a full-featured, automated GUI tool for **comparative protein modeling**. It brings together the most essential steps of homology-based protein structure prediction — BLAST search, sequence alignment, 3D model building, structure visualization, Ramachandran plot validation, and an AI-powered chat assistant: all within a single, user-friendly desktop interface.

Designed for researchers, students, and bioinformaticians, VASUKI eliminates the need for command-line expertise and manual pipeline management, making protein structure prediction more accessible than ever.

---

## Key Features

- **End-to-End Automated Pipeline** — From a raw amino acid sequence (FASTA format) to a validated 3D protein model, VASUKI handles the entire workflow in one place.
- **BLAST Integration** — Performs automated sequence similarity searches against protein databases to identify the best homologous templates.
- **Dynamic Sequence Alignment** — Flexible sequence alignment tools optimized for homology modeling.
- **3D Model Building with MODELLER** — Leverages the industry-standard MODELLER engine to generate high-quality 3D protein structures.
- **Structure Visualization** — Built-in HTML-based interactive model viewer for exploring protein structures directly within the app.
- **Ramachandran Plot Validation** — Generates both 2D and 3D Ramachandran plots with automated residue analysis (favoured, allowed, disallowed regions) to assess model quality.
- **AI Chat Assistant (Modssistant)** — Powered by Meta-Llama-3-8B via the HuggingFace Inference API, the integrated chatbot answers questions about BLAST results, model quality, and Ramachandran statistics in real time.
- **Intuitive PyQt5 GUI** — Clean, modern interface designed for scientists, not developers. No command-line knowledge required.

---

## Installation

### Prerequisites

- Python 3.9 or higher
- MODELLER (free academic license from [salilab.org](https://salilab.org/modeller/))
- Ensure the Modeller executable directory is added to your system's PATH environment variable.
- Internet connection (for BLAST searches and AI chatbot)

### Create a virtual environment (Recommended)

```bash
python -m venv venv
.\venv\Scripts\activate
```

### From Source

```bash
git clone https://github.com/ShreyaSutar2004/vasuki-mitbio.git
cd vasuki-mitbio
pip install .
```

---

## Usage

### Launch the GUI

```bash
run-vasuki
```

### Setting Up the AI Chatbot

VASUKI's built-in AI assistant requires a free HuggingFace API token:

1. Go to [huggingface.co](https://huggingface.co/) and log in or create an account.
2. Navigate to **Settings → Access Tokens** and generate a token with **Read** access.
3. An `.env` file will be automatically created in your working directory on first launch. Add your token:

```env
HUGGINGFACEHUB_API_TOKEN=your_token_here
```

4. Restart the application if needed.

### Workflow

1. **Input** your target protein sequence in FASTA format.
2. **BLAST Search** — Find homologous template structures from the PDB.
3. **Align Sequences** — Dynamically align your query with the selected template(s).
4. **Build 3D Model** — Generate protein structures using MODELLER.
5. **Visualize** — Explore your model interactively in the built-in viewer.
6. **Validate** — Run Ramachandran plot analysis to assess model quality.
7. **Ask Modssistant** — Query the AI chatbot about your results.

---

## Dependencies

| Package | Purpose |
|---|---|
| PyQt5 | GUI framework |
| MODELLER | Protein structure modeling |
| Biopython | Bioinformatics utilities |
| Requests | BLAST HTTP requests |
| LangChain & Transformers | AI chat backend |
| HuggingFace Hub | LLM API integration |
| Pandas | Data handling |
| ramplot | Ramachandran plot generation |
| python-dotenv | API key management |
| setuptools (≤69.5.1) | Required by ramplot |

---

## Contributing

Contributions are welcome!

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Submit a pull request with a clear description of your changes.

For major changes, please open an issue first to discuss your proposal.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Authors

- **Ms. Shreya Sutar** — Developer
- **Dr. K V Swamy** — Supervisor


*VASUKI — bridging the gap between sequence and structure, one model at a time.*
