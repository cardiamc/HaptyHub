from google import genai
from google.genai import types
import PIL.Image
import config, os

class GeminiClient:
    def __init__(self):
        # Inizializza il client passando la chiave API esplicitamente
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        
        self.model_id = config.GEMINI_MODEL_ID

    def analyze_image(self, image_path: str, prompt: str) -> str:
        """Fase 1: Analizza l'immagine e restituisce la descrizione testuale."""
        img = PIL.Image.open(image_path)
        
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=[prompt, img]
        )
        return response.text

    def generate_scad(self, description: str, system_prompt: str) -> str:
        """[DEPRECATED] Fase 2: Prende la descrizione e genera il codice OpenSCAD."""
        
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=description,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=1.0 # Abbassiamo la temperatura per avere codice più prevedibile e meno "creativo"
            )
        )
        
        # Pulisce l'output nel caso in cui Gemini usi la formattazione markdown
        testo_pulito = response.text.replace("```scad", "").replace("```openscad", "").replace("```", "").strip()
        return testo_pulito


class ClaudeClient:
    """
    Client per le API di Anthropic (Claude), con la stessa interfaccia di GeminiClient.
    Configurato per contenere i costi: modello ed effort sono in config.py.
    """

    # Lato lungo massimo dell'immagine inviata. Le immagini più grandi vengono
    # comunque ridotte dal server, ma ridurle qui fa risparmiare banda e token.
    MAX_IMAGE_SIDE = 1568

    def __init__(self):
        import anthropic
        # max_retries: l'SDK ritenta da solo su 429 / 5xx / sovraccarico
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=3)
        self.model_id = config.CLAUDE_MODEL_ID
        self.effort = config.CLAUDE_EFFORT
        self.last_usage = None  # token usati dall'ultima chiamata (per stimare i costi)

    def _image_block(self, image_path: str) -> dict:
        """Converte l'immagine in PNG base64, ridimensionandola se troppo grande."""
        import base64, io
        img = PIL.Image.open(image_path)
        img.thumbnail((self.MAX_IMAGE_SIDE, self.MAX_IMAGE_SIDE))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
        return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}

    def _call(self, content, system=None) -> str:
        kwargs = dict(
            model=self.model_id,
            max_tokens=16000,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": content}],
        )
        if system:
            kwargs["system"] = system
        response = self.client.messages.create(**kwargs)
        self.last_usage = response.usage
        print(f"[Claude] {self.model_id}: {response.usage.input_tokens} token in, "
              f"{response.usage.output_tokens} token out")

        if response.stop_reason == "refusal":
            raise RuntimeError("Claude ha rifiutato la richiesta.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Risposta di Claude troncata (limite di token raggiunto).")
        return "".join(b.text for b in response.content if b.type == "text")

    def analyze_image(self, image_path: str, prompt: str) -> str:
        """Fase 1: Analizza l'immagine e restituisce la descrizione testuale."""
        return self._call([self._image_block(image_path), {"type": "text", "text": prompt}])

    # Aggiunta al prompt di sistema: senza, Claude tende ad accompagnare il codice
    # con spiegazioni e controlli, che rompono il file .scad (e costano token).
    SCAD_ONLY = (
        "\n\nOUTPUT FORMAT: reply with ONLY the complete OpenSCAD source code, inside a single "
        "```openscad code block. No explanations, notes, computed values or checks outside "
        "the code block; put any necessary remarks inside the code as // comments."
    )

    def generate_scad(self, description: str, system_prompt: str) -> str:
        """Fase 2: Prende la descrizione e genera il codice OpenSCAD."""
        import re
        testo = self._call(description, system=system_prompt + self.SCAD_ONLY)
        # Se c'è un blocco di codice, teniamo solo quello (il più lungo, se più d'uno)
        blocchi = re.findall(r"```[a-zA-Z]*\n(.*?)```", testo, flags=re.S)
        if blocchi:
            return max(blocchi, key=len).strip()
        return testo.replace("```scad", "").replace("```openscad", "").replace("```", "").strip()


class TestClient:
    """Classe di test per verificare il funzionamento del client senza chiamare l'API."""

    def __init__(self):
        self.client = None

        # Definisci il percorso del file temporaneo (rispetto a dove esegui lo script)
        self.temp_graph_path = os.path.join(config.TEMP_DIR, "output_coordinates.json")
    
    def analyze_image(self, image_path: str, prompt: str) -> str:
        """
        In modalità test, cerca un file JSON pre-generato. 
        Se lo trova, lo restituisce, altrimenti genera un JSON fittizio.
        """

        # Se il file temp_graph.json esiste, leggilo e restituiscilo
        if os.path.exists(self.temp_graph_path):
            print(f"🛠️ [TEST CLIENT] Trovato {self.temp_graph_path}. Caricamento dati mock...")
            try:
                # Usiamo f.read() e NON json.load() perché l'API vera restituisce 
                # una stringa di testo, non un dizionario Python.
                with open(self.temp_graph_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"❌ Errore nella lettura del file di test: {e}")
                return f'{{"error": "Impossibile leggere il file di test: {e}"}}'
        
        # Fallback se il file non c'è (JSON base fittizio per non far crashare l'app)
        print("🛠️ [TEST CLIENT] File temp_graph.json non trovato. Uso JSON di fallback.")
        fallback_json = """
        {
            "nodes": [{"id": "n1", "label": "Nodo Test"}],
            "edges": []
        }
        """
        return fallback_json.strip()
    
    def generate_scad(self, description: str, system_prompt: str) -> str:
        return "System prompt: " + system_prompt