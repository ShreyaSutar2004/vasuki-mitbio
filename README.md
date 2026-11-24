# VASUKI

**An Automated GUI for Comparative (Homology) Protein Modelling**

VASUKI takes you from a target sequence to a validated 3D model in one desktop application: template search, alignment, model building, refinement, validation and visualisation, with a built-in local AI assistant that explains your BLAST and Ramachandran results.

Version 1.2.0 | Windows | Python 3.9 - 3.11 | MIT licence

---

## Features

- **Template search (BLAST):** search for templates and rank hits by identity, coverage, E-value and score.
- **Alignment:** target-template alignment before modelling.
- **Model building:** comparative modelling with MODELLER.
- **Relaxation:** energy minimisation and structure clean-up with OpenMM and PDBFixer.
- **Validation:** Ramachandran 2D/3D plot analysis (six-category statistics per model) using ramplot.
- **3D visualisation:** interactive structure viewer inside the application.
- **AI assistant (offline):** a small Qwen model runs locally on your CPU. It recommends a template from your BLAST table and interprets your Ramachandran statistics in a few short lines. No API key, no internet needed after the first download.

---

## Requirements

- Windows 10/11
- Python 3.9, 3.10 or 3.11
- A MODELLER licence key (free for academic use, from the Sali lab: https://salilab.org/modeller/)
- About 1 GB of free disk space (the AI model is about 542 MB)

---

## Installation

```powershell
git clone https://github.com/ShreyaSutar2004/vasuki-mitbio.git
cd vasuki-mitbio

python -m venv venv
venv\Scripts\activate

# Prebuilt CPU wheel for the AI assistant (avoids needing a C++ compiler)
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

pip install .
```

Make sure MODELLER is installed and licensed before you build models. See the MODELLER installation guide for how to enter your licence key.

---

## Running VASUKI

```powershell
run-vasuki
```

or

```powershell
python -m vasuki.main
```

---

## The AI assistant

On first launch VASUKI downloads the Qwen3.5-0.8B (Q4_K_M, GGUF) model automatically:

- **Size:** about 542 MB, one time only.
- **Source:** `InventoryWomen/vasuki-qwen3.5-0.8b-gguf` on Hugging Face. No account, token or API key is needed.
- **Location:** `%LOCALAPPDATA%\VASUKI\models`
- **Integrity:** the file's SHA-256 checksum is verified before it is loaded. A corrupted download is removed and fetched again.
- **After that:** everything runs locally and offline.

To store the model somewhere else, set the `VASUKI_MODEL_CACHE` environment variable to a folder path before launching.

How to use it:

- **BLAST window:** run a search, then ask for example "which template should I use?". VASUKI ranks the hits and explains its pick.
- **Ramachandran window:** generate the plots first, then ask about the statistics. The assistant reads the numbers from the Analysis Results panel.

Answers are intentionally short (at most 5 lines). It is a 0.8B model: treat its output as a quick helper, not a replacement for your own judgement.

---

## Project structure

```
vasuki-mitbio/
  pyproject.toml
  vasuki/
    main.py              entry point
    gui_launcher.py      Qt setup and launcher
    home.py              main window
    blast.py             template search and BLAST chat
    dynamic_align.py     alignment
    modelbuilding.py     MODELLER model building
    relax.py             OpenMM / PDBFixer refinement
    validation.py        Ramachandran validation and chat
    visualize.py         3D viewer
    chatmodel.py         local Qwen chatbot logic and prompts
    model_manager.py     model download, cache and checksum
    Images/              GUI images
  configs/, examples/    configuration and example files
```

---

## Troubleshooting

- **`llama-cpp-python` fails to install:** use the prebuilt wheel command in the installation section, or install the Visual Studio C++ build tools.
- **Chatbot says it is unavailable:** check the console for a `Qwen preload failed` message. It is usually a network problem during the first download. Restart the app to retry.
- **Re-download the model:** delete the file in `%LOCALAPPDATA%\VASUKI\models` and relaunch.
- **Ramachandran chat says no statistics are available:** click **Generate Plots** first.

---

## Citation

If you use VASUKI in your work, please cite:

> Sutar S., Swamy K. V. VASUKI: An Automated GUI for Comparative Protein Modeling. (publication details to be added)

---

## Authors

- Shreya Sutar
- Dr. K. V. Swamy

---

## Acknowledgements

- [MODELLER](https://salilab.org/modeller/) for comparative modelling
- [OpenMM](https://openmm.org/) and PDBFixer for refinement
- [ramplot](https://pypi.org/project/ramplot/) for Ramachandran analysis
- [Qwen](https://huggingface.co/Qwen) team (Alibaba Cloud) for the Qwen3.5 model, used here as an unmodified Q4_K_M quantised copy under its original licence
- [llama.cpp](https://github.com/ggml-org/llama.cpp) / llama-cpp-python for local inference

---

## Licence

MIT. See `LICENSE`.
