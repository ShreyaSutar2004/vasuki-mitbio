def get_api_key():
    import os
    from dotenv import load_dotenv

    # Force correct path (project root)
    env_path = os.path.join(os.getcwd(), ".env")

    load_dotenv(dotenv_path=env_path)

    token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    # print("ChatBot Enabled")
    print("ENV PATH:", env_path)
    # print("DEBUG TOKEN:", token)

    if not token:
        print("No API key found. AI features will be disabled.")
        return None

    return token