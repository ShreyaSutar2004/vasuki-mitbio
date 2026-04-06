from .gui_launcher import launch
from .config import get_api_key
import os

def ensure_env():
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write("HUGGINGFACEHUB_API_TOKEN=  ")
        print("Created .env file. Please add your API key and restart.")
    else:
        print(".env already exists. Using existing configuration.")

def main():
    print("Launching VASUKI...")

    ensure_env()
    api_key = get_api_key()
    launch(api_key)
    # launch()


if __name__ == "__main__":
    main()
    