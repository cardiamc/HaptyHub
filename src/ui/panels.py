from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, 
                             QSpinBox, QLineEdit, QLabel, QTextEdit)
from src.prompts.templates import DirectGraphTemplate, UndirectGraphTemplate, FlowChartTemplate, SetTheoryTemplate

from src.prompts.templates import ELKFlowChartTemplate, ELKGraphTemplate # Per la pipeline Android/ELK

class BaseTemplatePanel(QWidget):
    """Interfaccia base per i pannelli. Tutti devono poter generare un oggetto Template."""
    def get_prompt_object(self):
        raise NotImplementedError("Devi implementare get_prompt_object()")


class GraphFormPanel(BaseTemplatePanel):
    """Grafi orientati e non: nodi, archi, pesi e prezzi li legge l'AI dall'immagine (nessun parametro)."""
    def __init__(self, is_directed: bool):
        super().__init__()
        self.is_directed = is_directed

    def get_prompt_object(self):
        if self.is_directed:
            return DirectGraphTemplate(0, 0, "")
        return UndirectGraphTemplate(0, 0, "")


class FlowChartPanel(BaseTemplatePanel):
    """Diagrammi di flusso: blocchi e frecce li legge l'AI dall'immagine (nessun parametro)."""
    def get_prompt_object(self):
        return FlowChartTemplate()


class SetTheoryPanel(BaseTemplatePanel):
    """Pannello per Set Theory, al momento senza parametri specifici."""
    def get_prompt_object(self):
        return SetTheoryTemplate()
    
# ELK BASED PANEL

class ELK_FlowChartPanel(BaseTemplatePanel):
    """Pannello per Flow Chart per la Pipeline Android, al momento senza parametri specifici."""
    def __init__(self):
        super().__init__()
        layout = QFormLayout(self)

    def get_prompt_object(self):
        # Raccoglie i dati dalla UI e crea l'oggetto pronto per le API
        return ELKFlowChartTemplate()
    
class ELK_GraphPanel(BaseTemplatePanel):
    """Pannello per Grafi per la Pipeline Android, al momento senza parametri specifici."""
    def __init__(self):
        super().__init__()
        layout = QFormLayout(self)

    def get_prompt_object(self):
        # Raccoglie i dati dalla UI e crea l'oggetto pronto per le API
        return ELKGraphTemplate()