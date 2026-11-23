import os
from dotenv import load_dotenv

DEBUG_MODE = True #used to turn of the real API calls

#===========================================================================
#   ESEMPIO DI CONFIGURAZIONE
# --------------------------------------------------------------------------
# Path globali (in chiaro)
# Esempio: 
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# OUTPUT_DIR = os.path.join(BASE_DIR, "output_models")
# Per convenzione, si scrivono in maiuscolo per indicare che sono costanti.

# Chiavi API (NON METTERE IN CHIARO)
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# if not OPENAI_API_KEY: raise ValueError("OpenAI API Key not found")
#===========================================================================

#====================
#---- Gemini Key ----
#====================
# Carica le variabili d'ambiente dal file .env
load_dotenv()
# Legge la chiave definita nel file .env, se non presente
# va creato
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

#GEMINI_MODEL_ID = "gemini-3.1-pro-preview"
#GEMINI_MODEL_ID = "gemini-2.5-flash"
GEMINI_MODEL_ID = "gemini-3.5-flash-lite"

#====================
#---- Claude --------
#====================
# Chiave Anthropic (https://console.anthropic.com), da inserire nel file .env
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Modello più economico ($0.10 / $0.50 per milione di token in/out).
# Se la qualità non basta: "claude-sonnet-5-5" ($2 / $10) o "claude-opus-5-5" ($4 / $20)
CLAUDE_MODEL_ID = "claude-haiku-5-5"
# Quanto "ragiona" il modello prima di rispondere: low | medium | high
# "medium": buon compromesso (≈0,5 cent a generazione); "low" costa un po' meno ma è meno preciso
CLAUDE_EFFORT = "medium"

#====================
#---- Provider AI ---
#====================
# Ordine in cui provare i provider. Se il primo è sovraccarico (503) o ha la
# quota esaurita (429), si passa al successivo. Vengono usati solo quelli con
# la chiave configurata nel .env.
# Gemini per primo (gratuito), Claude come riserva (a pagamento).
AI_PROVIDERS = ["gemini", "claude"]

#====================
#---- Path Utili ----
#====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Cartella dove salveremo i file .scad generati

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPT_DIR = os.path.join(BASE_DIR, "src", "prompts")
# Cartella degli asset (icone, immagini, ecc.)
ASSET_DIR = os.path.join(BASE_DIR, "assets")

DEVICES_FILE = os.path.join(BASE_DIR, "devices.json")
ACTIVE_DEVICE = None # Memorizza l'istanza del Device attualmente selezionato

# Cartella temporanea per file intermedi (es. log, cache, ecc.)
UTILS_DIR = os.path.join(BASE_DIR,"src", "utils")

TEMP_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

#====================
#---- OpenSCAD ------
#====================
def _find_openscad():
    """
    Restituisce il comando/percorso di OpenSCAD.
    Su Windows l'installer non lo aggiunge al PATH, quindi lo cerchiamo
    anche nelle cartelle di installazione standard.
    """
    import shutil
    found = shutil.which("openscad")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            exe = os.path.join(base, "OpenSCAD", "openscad.exe")
            if os.path.isfile(exe):
                return exe
    return "openscad"  # ultimo tentativo: lasciamo decidere al sistema

OPENSCAD_CMD = _find_openscad()
