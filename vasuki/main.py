
# IMPORTANT:
# Import llama_cpp before loading GUI modules or pandas.
from llama_cpp import Llama as _LlamaRuntime

from .gui_launcher import launch


def main():
    print("Launching VASUKI...")
    launch(api_key=None)


if __name__ == "__main__":
    main()
