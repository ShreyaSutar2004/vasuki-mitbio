
import os
import pandas as pd
from huggingface_hub import InferenceClient
from dotenv import load_dotenv


load_dotenv()

class Chatbot:
    def __init__(self, blast_path=None):
        self.model_name = "mistralai/Mistral-7B-Instruct-v0.2"
        self.client = None
        self.messages = []

        self.blast_manager = BlastManager(blast_path) if blast_path else None
        self.setup_client()

    def setup_client(self):
        self.client = InferenceClient(
            token=os.getenv("HUGGINGFACEHUB_API_TOKEN")
        )
        self.messages = [
            {"role": "system", "content": "You are a helpful bioinformatics assistant.Answer only in 3-4 relevant sentences, no lenghty explanations."}
        ]


    def _llm_response(self, text):
        self.messages.append({"role": "user", "content": text})

        response = self.client.chat_completion(
            messages=self.messages,
            model=self.model_name,
            max_tokens=200,
            temperature=0.7,
            stream=False
        )

        reply = response.choices[0].message.content.strip()
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    # -------- BLAST CHECK --------
    def blast_query(self, user_msg):
        keywords = ["blast", "e-value", "identity", "top", "template", "hit"]
        return any(k in user_msg.lower() for k in keywords)

    # -------- BLAST LOGIC --------
    def generate_blast_response(self, user_msg):
        q = user_msg.lower()

        if "lowest" in q and "e" in q:
            return str(self.blast_manager.lowest_evalue())

        if "highest" in q and "identity" in q:
            return str(self.blast_manager.highest_identity())

        blast_context = self.blast_manager.blast_db.head(5).to_string(index=False)

        prompt = f"""
    You are a bioinformatics assistant. Answer only in 3-4 relevant sentences, no lenghty explanations.

    BLAST RESULTS:
    {blast_context}

    Question:
    {user_msg}

    Answer strictly using the BLAST data.
    """
        return self._llm_response(prompt)

    # -------- ROUTER (MAIN ENTRY) --------
    def generate_response(self, user_msg):
        if self.blast_manager and self.blast_query(user_msg):
            return self.generate_blast_response(user_msg)

        return self._llm_response(user_msg)
    
class BlastManager:
    def __init__(self, blast_path):
        self.blast_db = self.load_blast(blast_path)

    def load_blast(self, path):
        cols = ["Select", "PDB_ID", "Chain", "Accession", "Scientific_Name",
                "Score", "E_Value", "Identity", "Positive", "Gaps"]
        return pd.read_csv(path, names=cols, sep="\t")

    def lowest_evalue(self):
        row = self.blast_db.loc[self.blast_db['E_Value'].idxmin()]
        return row.to_dict()

    def highest_identity(self):
        row = self.blast_db.loc[self.blast_db['Identity'].idxmax()]
        return row.to_dict()

def main():
    chatbot = Chatbot(blast_path="blast_results.tsv")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("Bot: Goodbye!")
            break

        if not user_input:
            continue

        response = chatbot.generate_response(user_input)
        print(f"Bot: {response}\n")
