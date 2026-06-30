import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

class Config:
    HOST  = os.getenv("HOST", "0.0.0.0")
    PORT  = int(os.getenv("PORT", 5055))
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    DATA_DIR      = DATA_DIR
    LOTES_DIR     = DATA_DIR / "lotes"
    RESPOSTAS_DIR = DATA_DIR / "respostas"
    PDFS_DIR      = DATA_DIR / "pdfs"
    LOGS_DIR      = DATA_DIR / "logs"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama3-8b-8192")

    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_URL   = os.getenv("WHATSAPP_URL", "")
    META_APP_SECRET = os.getenv("META_APP_SECRET", "")