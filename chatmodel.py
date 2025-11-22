
import os
from huggingface_hub import InferenceClient


class Chatbot:
    def __init__(self):
        self.model_name = "meta-llama/Llama-3.2-1B-Instruct"
        self.client = None
        self.messages = [] 
        self.setup_client()
    
    def setup_client(self):
        """Initialize InferenceClient for cloud inference."""
        print("Setting up Hugging Face InferenceClient... (Uses cloud API)")
        
        try:
            self.client = InferenceClient(
                token=os.getenv("HUGGINGFACEHUB_API_TOKEN") 
            )
            
            # Initialize with system message
            self.messages = [
                {"role": "system", "content": "You are a helpful assistant."}
            ]
            
            print("Chatbot ready! Type 'quit' to exit.\n")
        
        except Exception as e:
            print(f"Client setup error: {e}")
            print("Tip: Set HUGGINGFACEHUB_API_TOKEN env var with your HF token.")
            raise
    
    def generate_response(self, user_msg):
        """Generate a response using chat_completion."""
        # Add user message to history
        self.messages.append({"role": "user", "content": user_msg})
        
        # Generate response
        response = self.client.chat_completion(
            messages=self.messages,
            model=self.model_name,
            max_tokens=00,
            temperature=0.7,
            stream=False  
        )
        
        # Extract content
        new_response = response.choices[0].message.content.strip()
        
        # Append assistant response to history
        self.messages.append({"role": "assistant", "content": new_response})
        
        return new_response

def main():
    chatbot = Chatbot()
    
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("Bot: Goodbye!")
            break
        
        if not user_input:
            continue
        
        response = chatbot.generate_response(user_input)
        print(f"Bot: {response}\n")

if __name__ == "__main__":
    main()