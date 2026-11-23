from PyQt6.QtCore import QThread

# Riferimenti ai thread ancora in esecuzione la cui finestra e' stata chiusa.
# Senza questo riferimento Python distruggerebbe il QThread mentre run() e'
# ancora attivo, causando "QThread: Destroyed while thread is still running"
# e la chiusura forzata dell'applicazione.
_orphan_threads = set()


def release_thread(thread):
    """
    Rilascia un worker QThread in modo sicuro.

    - Scollega i segnali personalizzati (progress/finished/error) cosi' la UI,
      magari gia' distrutta, non riceve piu' nulla.
    - Se il thread ha finito, lo elimina subito.
    - Se e' ancora in esecuzione (es. chiamata a Gemini o compilazione
      OpenSCAD in corso), lo tiene in vita finche' run() non termina e solo
      allora lo elimina, senza bloccare l'interfaccia.
    """
    if thread is None:
        return

    for name in ("progress", "finished", "error"):
        try:
            getattr(thread, name).disconnect()
        except (AttributeError, TypeError, RuntimeError):
            pass

    if not thread.isRunning():
        thread.deleteLater()
        return

    _orphan_threads.add(thread)
    # I worker ridefiniscono "finished" con un segnale proprio: usiamo il
    # segnale nativo di QThread, emesso quando run() e' davvero terminato.
    native_finished = QThread.finished.__get__(thread, QThread)

    def _on_done():
        _orphan_threads.discard(thread)
        thread.deleteLater()

    native_finished.connect(_on_done)
