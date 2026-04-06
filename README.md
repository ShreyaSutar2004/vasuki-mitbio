# VASUKI: Automated GUI for Comparative Protein Modeling

[![PyPI version](https://badge.fury.io/py/vasuki-mitbio.svg)](https://pypi.org/project/vasuki-mitbio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

VASUKI is an automated graphical user interface (GUI) tool for comparative protein modeling, designed to simplify homology modeling workflows. Built with PyQt5, it integrates BLAST searches, dynamic alignments, MODELLER for generating 3D protein structures from amino acid sequences and generating Ramachandran plots. 

## Features

- **User-Friendly GUI**: Intuitive interface for protein modeling without command-line expertise.
- **BLAST Integration**: Automated sequence similarity searches against protein databases.
- **Dynamic Alignment**: Flexible sequence alignment tools for homology modeling.
- **3D Model Building**: Uses MODELLER to generate high-quality protein structures.
- **Visualization**: Built-in HTML-based model visualization.
- **Validation**: Generates 2D and 3D Ramachandran plots. 
- **Chat Interface**: AI-powered chat model for guidance and troubleshooting.
- **Cross-Platform**: Supports Windows (primary), with potential for other OS.

## Installation

### Prerequisites
- Python 3.9 or higher
- MODELLER (requires license from [salilab.org](https://salilab.org/modeller/))
- Internet connection for BLAST searches

### From PyPI (Recommended)
```bash
pip install vasuki-mitbio
```

### From Source
1. Clone the repository:
   ```bash
   git clone https://github.com/ShreyaSutar2004/vasuki-mitbio.git
   cd vasuki
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # Or using pyproject.toml
   pip install .
   ```

3. Chatbot Setup
 Go to (https://huggingface.co/)
 Login or Create a new account
 Navigate to Settings --> Access Tokens
 Select Read access
 Copy the generated token.
 
## Usage

### Launch the GUI
After installation, run:
```bash
run-vasuki
```

### Command-Line Scripts
- `run-vasuki`: Launches the main GUI application.

### Initializing Chatbot
An .env file will be automatically created in your working directory. 
```bash
HUGGINGFACEHUB_API_TOKEN= your_api_key_here
```
(restart the application if needed)

### Workflow
1. Input your target protein sequence (FASTA format).
2. Perform BLAST search to find homologous templates.
3. Align sequences dynamically.
4. Build 3D models using MODELLER.
5. Visualize and validate results.


## Dependencies

- PyQt5: GUI framework
- MODELLER: Protein structure modeling
- Biopython: Bioinformatics tools
- Requests: HTTP requests for BLAST
- LangChain & Transformers: AI chat functionality
- Pandas: Data handling
- Other utilities: python-dotenv, ramplot

## Configuration

Create a `.env` file in the project root for API keys and custom settings (e.g., for the chat model).

## Contributing

Contributions are welcome! Please:

1. Fork the repository.
2. Create a feature branch.
3. Submit a pull request with detailed changes.

For major changes, open an issue first to discuss.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Authors

- **Ms. Shreya Sutar**: Developer
- **Dr. K V Swamy**: Supervisor

If you use VASUKI in your research, please cite:

Sutar, S., & Swamy, K. V. (2024). VASUKI: An Automated GUI for Comparative Protein Modeling. [Repository/Preprint Link]

*VASUKI is named after the mythical serpent king, symbolizing precision and automation in protein modeling.* 
