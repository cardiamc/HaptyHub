
from PyQt6.QtCore import QThread, Qt, pyqtSignal

from src.api_client import GeminiClient, ClaudeClient
from src.api_client import TestClient # Classe di test senza chiamate API reali

import config, time, os, random


class _ServerBusyError(Exception):
    """Tutti i tentativi sono falliti per sovraccarico dei server (503)."""


# Errori temporanei: server sovraccarichi (Gemini 503, Claude 529)
_BUSY_MARKERS = ("503", "UNAVAILABLE", "529", "overloaded")
# Quota esaurita / troppe richieste: inutile insistere, meglio cambiare provider
_QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED", "rate_limit")

_PROVIDER_CLASSES = {"gemini": GeminiClient, "claude": ClaudeClient}
_PROVIDER_KEYS = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


# Pacchetto Python necessario a ciascun provider
_PROVIDER_PACKAGES = {"gemini": "google.genai", "claude": "anthropic"}


def _package_installed(provider):
    import importlib.util
    try:
        return importlib.util.find_spec(_PROVIDER_PACKAGES[provider]) is not None
    except ModuleNotFoundError:
        return False


def available_providers():
    """
    Provider (in ordine di config.AI_PROVIDERS) utilizzabili: chiave configurata
    nel .env e libreria installata. Quelli non utilizzabili vengono saltati con un
    avviso nel terminale, invece di far chiudere l'applicazione.
    """
    providers = []
    for p in config.AI_PROVIDERS:
        if p not in _PROVIDER_CLASSES or not getattr(config, _PROVIDER_KEYS[p], None):
            continue
        if not _package_installed(p):
            print(f"[AVVISO] Provider '{p}' saltato: libreria '{_PROVIDER_PACKAGES[p]}' non installata. "
                  f"Esegui: pip install -r requirements.txt")
            continue
        providers.append(p)
    return providers

# --- Worker Thread per l'integrazione API con Gemini ---
class GeminiWorker(QThread):
    # Segnali per comunicare con la UI (Thread principale)
    progress = pyqtSignal(str)   # Per aggiornare lo stato (es. "Fase 1 in corso...")
    finished = pyqtSignal(str)   # Quando ha generato il file .scad
    error = pyqtSignal(str)      # In caso di problemi di rete

    def __init__(self, image_path, prompt_fase_1, prompt_fase_2=None):
        super().__init__()
        self.image_path = image_path
        self.prompt_fase_1 = prompt_fase_1
        self.prompt_fase_2 = prompt_fase_2

        if config.DEBUG_MODE:
            self.providers = [("test", TestClient())]  # Usa il client di test
        else:
            # Lista ordinata di (nome, client): si passa al successivo se uno fallisce
            self.providers = [(p, _PROVIDER_CLASSES[p]()) for p in available_providers()]
            if not self.providers:
                self.providers = [("gemini", GeminiClient())]  # darà un errore chiaro sulla chiave
        self._current = 0  # indice del provider in uso (resta sull'ultimo che ha funzionato)

    @property
    def client(self):
        return self.providers[self._current][1]

    # Parametri di retry per errori temporanei dei server (503 / sovraccarico)
    MAX_RETRIES = 6          # tentativi sull'ultimo provider disponibile
    RETRIES_BEFORE_FALLBACK = 2  # tentativi prima di passare al provider successivo
    BASE_DELAY = 2.0         # secondi: 2 -> 4 -> 8 -> 16 -> 30 (max)
    MAX_DELAY = 30.0

    def run(self):
        try:
            # --- FASE 1: Immagine -> Testo (Sempre eseguita) ---
            risultato_fase_1 = self._with_retry("Fase 1", self.phase_1_only)

            # --- FASE 2: Testo -> OpenSCAD (Condizionale) ---
            if self.prompt_fase_2:
                # In caso di errore si ritenta solo la fase 2, senza rifare l'analisi dell'immagine
                filepath = self._with_retry("Fase 2", self.phase_2_only, risultato_fase_1)
                self.finished.emit(filepath)
            else:
                # Se non c'è il prompt 2, siamo nella logica Android/ELK!
                # Segnaliamo la fine passando direttamente il JSON testuale
                self.progress.emit("Fase 1 completata. JSON estratto.")
                self.finished.emit(risultato_fase_1)

        except _ServerBusyError:
            self.error.emit("I server AI sono attualmente troppo carichi. Riprova tra qualche minuto.")
        except Exception as e:
            # Errori non temporanei (es. API Key errata, quota esaurita, niente Internet)
            self.error.emit(f"Errore API: {str(e)}")

    def _with_retry(self, fase, func, *args):
        """
        Esegue func con il provider corrente. Sugli errori temporanei ritenta con
        exponential backoff (+ jitter); se il provider resta sovraccarico o ha la
        quota esaurita, passa al provider successivo (es. da Gemini a Claude).
        """
        while True:
            nome = self.providers[self._current][0]
            ultimo = self._current == len(self.providers) - 1
            max_tentativi = self.MAX_RETRIES if ultimo else self.RETRIES_BEFORE_FALLBACK

            for attempt in range(max_tentativi):
                if attempt == 0:
                    self.progress.emit(f"{fase}: in corso ({nome})...")
                else:
                    self.progress.emit(f"{fase}: nuovo tentativo con {nome}... ({attempt + 1}/{max_tentativi})")
                try:
                    return func(*args)
                except Exception as e:
                    error_msg = str(e)
                    occupato = any(m in error_msg for m in _BUSY_MARKERS)
                    quota = any(m in error_msg for m in _QUOTA_MARKERS)

                    if quota and not ultimo:
                        self.progress.emit(f"Quota {nome} esaurita (429).")
                        break  # inutile ritentare: si passa al prossimo provider
                    if not occupato:
                        raise  # errore non temporaneo (chiave errata, rete, ...)
                    if attempt == max_tentativi - 1:
                        if ultimo:
                            raise _ServerBusyError() from e
                        break
                    # 2s -> 4s -> 8s -> 16s -> 30s, con una piccola variazione casuale
                    delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                    delay = round(delay * random.uniform(0.8, 1.2), 1)
                    self.progress.emit(f"Server {nome} temporaneamente occupati. Attendo {delay} secondi e riprovo...")
                    time.sleep(delay)  # Mettiamo in pausa questo Thread (la GUI non si blocca!)

            # Passaggio al provider successivo
            self._current += 1
            self.progress.emit(f"Passo a {self.providers[self._current][0]}.")

    def phase_1_only(self):
        """Metodo alternativo per eseguire solo la Fase 1 (analisi immagine) e restituire il testo."""\
        # chiamata reale a Gemini per analizzare l'immagine e restituire il testo (JSON o descrizione)
        if config.DEBUG_MODE == False:
            return self.client.analyze_image(self.image_path, self.prompt_fase_1)
        else:
            # returniamo una risposta prefatta di Gemini per testare la logica senza chiamate API reali
            # usando il json temp/GeminiOutput_Debug.json
            with open(os.path.join(config.TEMP_DIR, "GeminiOutput_Debug.json"), "r", encoding="utf-8") as f:
                return f.read()
    def phase_2_only(self, risultato_fase_1):
        scad_code = self.client.generate_scad(risultato_fase_1, self.prompt_fase_2)
                
        # Salviamo il file in locale (Logica Circuito)
        timestamp = int(time.time())
        filepath = os.path.join(config.OUTPUT_DIR, f"modello_{timestamp}.scad")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(scad_code)
        return filepath
                