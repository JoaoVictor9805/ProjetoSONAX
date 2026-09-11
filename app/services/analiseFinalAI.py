import os
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from dotenv import load_dotenv

load_dotenv()

client = ChatNVIDIA(
  model="deepseek-ai/deepseek-v4-pro-0813",
  api_key=os.getenv("NVIDIA_API_KEY"),
  temperature=1,
  top_p=0.95,
  max_tokens=16384,
  seed=42,
)

for chunk in client.stream([{"role":"user","content":"Write a limerick about the wonders of GPU computing."}]):
  
    print(chunk.content, end="")