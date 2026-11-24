import os
import hashlib
import threading
from pathlib import Path

from huggingface_hub import hf_hub_download
from llama_cpp import Llama


# ============================================================
# MODEL CONFIGURATION
# ============================================================

MODEL_REPO_ID = "InventoryWomen/vasuki-qwen3.5-0.8b-gguf"

# Optional: pin to the full 40-character commit hash from the repo's
# "Files and versions" -> commit history. None = latest on main.
MODEL_REVISION = None

MODEL_FILENAME = "Qwen3.5-0.8B-Q4_K_M.gguf"

MODEL_SHA256 = (
    "b4e71cb32694733ba40c69e595a0524dfbc2cabe3c28fb7fef99eed4cf8730bf"
)


# ============================================================
# VASUKI MODEL CACHE
# ============================================================

# Windows:
# C:\Users\<username>\AppData\Local\VASUKI\models

DEFAULT_CACHE_ROOT = (
    Path(
        os.environ.get(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local")
        )
    )
    / "VASUKI"
    / "models"
)

# Allow an advanced user to override the cache directory.
CACHE_ROOT = Path(
    os.environ.get("VASUKI_MODEL_CACHE", str(DEFAULT_CACHE_ROOT))
)

MODEL_PATH = CACHE_ROOT / MODEL_FILENAME


# ============================================================
# MODEL STATE
# ============================================================

_llm = None
_model_lock = threading.Lock()


# ============================================================
# SHA-256 VERIFICATION
# ============================================================

def calculate_sha256(file_path):
    """Calculate the SHA-256 checksum of a model file."""

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as model_file:
        for chunk in iter(lambda: model_file.read(8 * 1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def verify_model(file_path):
    """Verify that the downloaded model matches the published checksum."""

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Model file does not exist: {file_path}"
        )

    actual_hash = calculate_sha256(file_path)

    if actual_hash.lower() != MODEL_SHA256.lower():
        raise ValueError(
            "Qwen model checksum verification failed.\n"
            f"Expected SHA-256: {MODEL_SHA256}\n"
            f"Actual SHA-256:   {actual_hash}\n"
            "The model file may be corrupted or incomplete."
        )

    print("VASUKI: Model SHA-256 verified successfully.")

    return True


# ============================================================
# MODEL DOWNLOAD
# ============================================================

def download_model():
    """
    Download Qwen on the first run.

    Reuse the cached model on subsequent runs.
    Verify the SHA-256 before allowing model loading.
    """

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    # Check whether a valid model is already cached.
    if MODEL_PATH.exists():

        print("VASUKI: Checking cached Qwen model...")

        try:
            verify_model(MODEL_PATH)

            print(f"VASUKI: Using cached model: {MODEL_PATH}")

            return str(MODEL_PATH)

        except (ValueError, OSError) as error:

            print(f"VASUKI: Cached model verification failed: {error}")
            print("VASUKI: Removing invalid cached model...")

            MODEL_PATH.unlink(missing_ok=True)

    # Download model from Hugging Face.
    print("VASUKI: Downloading Qwen model.")
    print("VASUKI: First-time download is approximately 542 MB.")
    print(f"VASUKI: Repository: {MODEL_REPO_ID}")
    print(f"VASUKI: Cache directory: {CACHE_ROOT}")

    downloaded_path = hf_hub_download(
        repo_id=MODEL_REPO_ID,
        filename=MODEL_FILENAME,
        revision=MODEL_REVISION,
        local_dir=str(CACHE_ROOT)
    )

    downloaded_path = Path(downloaded_path)

    if not downloaded_path.exists():
        raise FileNotFoundError(
            f"VASUKI could not locate the downloaded model: "
            f"{downloaded_path}"
        )

    print("VASUKI: Download completed. Verifying model...")

    try:
        verify_model(downloaded_path)

    except (ValueError, OSError):
        downloaded_path.unlink(missing_ok=True)
        raise

    print("VASUKI: Model downloaded and verified.")

    return str(downloaded_path)


# ============================================================
# MODEL LOADING
# ============================================================

def load_model():
    """
    Load Qwen into memory.

    The model is loaded only once per application session.
    Subsequent calls reuse the existing Llama instance.
    """

    global _llm

    if _llm is not None:
        return _llm

    with _model_lock:

        if _llm is not None:
            return _llm

        model_path = download_model()

        print("VASUKI: Initializing Qwen inference engine...")

        cpu_count = os.cpu_count() or 4

        threads = max(2, cpu_count - 2)

        _llm = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_threads=threads,
            verbose=False
        )

        print("VASUKI: Qwen model loaded successfully.")

        return _llm


# ============================================================
# MODEL UNLOADING
# ============================================================

def unload_model():
    """Release the model from memory when explicitly requested."""

    global _llm

    with _model_lock:

        if _llm is not None:
            _llm.close()
            _llm = None

            print("VASUKI: Qwen model unloaded.")