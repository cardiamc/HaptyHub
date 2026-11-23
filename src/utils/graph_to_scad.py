"""
Generazione deterministica di un bassorilievo tattile (OpenSCAD) a partire dalla
struttura di un grafo estratta dall'AI in formato JSON.

L'AI si limita a leggere l'immagine (nodi, posizioni, archi, pesi, prezzi);
tutta la geometria è calcolata qui, così il risultato è sempre coerente:
archi che toccano i nodi, frecce solo nei grafi orientati, dimensioni adatte al tatto.

Formato JSON atteso (vedi src/prompts/basic/Graph/phase1_json.txt):
{
  "directed": bool,
  "nodes": [{"id": "A", "x": 0-100, "y": 0-100, "price": "5" | null}],
  "edges": [{"from": "A", "to": "B", "weight": "3" | null}]
}
x: da sinistra (0) a destra (100); y: dal basso (0) all'alto (100) dell'immagine.
"""
import json
import math
import re

# ---- Parametri fisici del modello (mm) ----
BASE_SIZE = 200.0       # base quadrata fissa 200 x 200
BASE_THICKNESS = 3.0
MARGIN = 10.0           # margine minimo tra il bordo della base e qualsiasi elemento
NODE_HEIGHT = 5.0       # altezza dei nodi sopra la base
NODE_R_MIN, NODE_R_MAX = 3.5, 7.0
LABEL_HEIGHT = 1.2      # rilievo delle etichette sopra il nodo
TEXT_HEIGHT = 1.0       # rilievo di pesi e prezzi sulla base
EDGE_R_MIN, EDGE_R_MAX = 1.0, 1.6
FN = 48


class GraphDataError(ValueError):
    """Il JSON restituito dall'AI non descrive un grafo valido."""


def parse_graph_json(raw_text):
    """Estrae e valida il JSON del grafo dalla risposta testuale dell'AI."""
    testo = raw_text.strip()
    blocco = re.search(r"```(?:json)?\s*(.*?)```", testo, flags=re.S)
    if blocco:
        testo = blocco.group(1)
    # Tolleriamo testo prima/dopo l'oggetto JSON
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio == -1 or fine == -1:
        raise GraphDataError("La risposta dell'AI non contiene un oggetto JSON.")
    try:
        data = json.loads(testo[inizio:fine + 1])
    except json.JSONDecodeError as e:
        raise GraphDataError(f"JSON non valido: {e}") from e

    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    if not nodes:
        raise GraphDataError("Nessun nodo trovato nell'immagine.")

    ids = set()
    for n in nodes:
        if "id" not in n or "x" not in n or "y" not in n:
            raise GraphDataError(f"Nodo incompleto: {n}")
        n["id"] = str(n["id"])
        n["x"], n["y"] = float(n["x"]), float(n["y"])
        if n["id"] in ids:
            raise GraphDataError(f"Nodo duplicato: {n['id']}")
        ids.add(n["id"])
    for e in edges:
        e["from"], e["to"] = str(e.get("from")), str(e.get("to"))
        if e["from"] not in ids or e["to"] not in ids:
            raise GraphDataError(f"Arco che collega nodi inesistenti: {e}")

    data["directed"] = bool(data.get("directed", False))
    data["nodes"], data["edges"] = nodes, edges
    return data


def _scad_str(s):
    """Stringa letterale OpenSCAD con escape."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _f(v):
    return f"{v:.3f}"


def _text_block(label, size, x, y, z, height):
    return (f"translate([{_f(x)}, {_f(y)}, {_f(z)}]) linear_extrude(height = {_f(height)}) "
            f"text({_scad_str(label)}, size = {_f(size)}, halign = \"center\", valign = \"center\", "
            f"font = \"Liberation Sans:style=Bold\");")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def generate_scad_from_graph(data, image_aspect=1.0, directed=None):
    """
    Restituisce il sorgente OpenSCAD del bassorilievo.

    :param data: dizionario restituito da parse_graph_json
    :param image_aspect: larghezza / altezza dell'immagine originale (corregge la
                         griglia 0-100, che altrimenti deformerebbe le immagini non quadrate)
    :param directed: forza orientato/non orientato (es. scelta dell'utente nella UI);
                     None = usa il valore letto dall'AI
    """
    is_directed = data["directed"] if directed is None else bool(directed)
    nodes, edges = data["nodes"], data["edges"]

    # Coordinate in unità proporzionali all'immagine reale
    pts = {n["id"]: (n["x"] * image_aspect, n["y"]) for n in nodes}
    xs = [p[0] for p in pts.values()]
    ys = [p[1] for p in pts.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w, h = max(xs) - min(xs), max(ys) - min(ys)

    # Distanza minima tra due nodi (in unità immagine), per dimensionare i nodi
    ids = list(pts)
    min_d = min((math.dist(pts[a], pts[b]) for i, a in enumerate(ids) for b in ids[i + 1:]),
                default=0.0)

    # Scala: il grafo (nodi compresi) deve stare nella base con il margine.
    # Due passaggi perché il raggio dei nodi dipende dalla scala e viceversa.
    node_r = NODE_R_MAX
    for _ in range(2):
        usable = BASE_SIZE - 2 * (MARGIN + node_r)
        dims = [d for d in (w, h) if d > 1e-9]
        scale = min(usable / d for d in dims) if dims else 1.0
        node_r = _clamp(0.3 * min_d * scale, NODE_R_MIN, NODE_R_MAX) if min_d > 0 else NODE_R_MAX
    edge_r = _clamp(node_r * 0.25, EDGE_R_MIN, EDGE_R_MAX)
    arrow_len, arrow_w = node_r * 1.2, node_r * 1.25
    arrow_t = edge_r * 1.5
    small_font = _clamp(node_r * 0.9, 4.0, 6.0)
    limit = BASE_SIZE / 2 - MARGIN

    def to_mm(p):
        return ((p[0] - cx) * scale, (p[1] - cy) * scale)

    pos = {nid: to_mm(p) for nid, p in pts.items()}

    out = []
    out.append("// ============================================================")
    out.append("// Bassorilievo tattile generato automaticamente da HaptyHub")
    out.append(f"// Grafo {'orientato' if is_directed else 'non orientato'}: "
               f"{len(nodes)} nodi, {len(edges)} archi")
    out.append("// Compatibile con OpenSCAD 2021.01")
    out.append("// ============================================================")
    out.append(f"base_size = {_f(BASE_SIZE)};")
    out.append(f"base_thickness = {_f(BASE_THICKNESS)};")
    out.append(f"margin = {_f(MARGIN)};")
    out.append(f"scale_factor = {_f(scale)};")
    out.append(f"node_radius = {_f(node_r)};")
    out.append(f"node_height = {_f(NODE_HEIGHT)};")
    out.append(f"edge_radius = {_f(edge_r)};")
    out.append(f"$fn = {FN};")
    out.append("")
    out.append("module edge_segment(p1, p2) {")
    out.append("    dx = p2[0] - p1[0]; dy = p2[1] - p1[1];")
    out.append("    len = sqrt(dx*dx + dy*dy);")
    out.append("    // cilindro sdraiato, per metà sopra la base")
    out.append("    translate([p1[0], p1[1], base_thickness])")
    out.append("        rotate([0, 0, atan2(dy, dx)]) rotate([0, 90, 0])")
    out.append("            cylinder(h = len, r = edge_radius);")
    out.append("}")
    out.append("")
    out.append("module arrow_head(tip, angle, length, width, thickness) {")
    out.append("    translate([tip[0], tip[1], base_thickness]) rotate([0, 0, angle])")
    out.append("        linear_extrude(height = thickness)")
    out.append("            polygon(points = [[0, 0], [-length, -width/2], [-length, width/2]]);")
    out.append("}")
    out.append("")
    out.append("union() {")
    out.append("    // Base")
    out.append("    translate([-base_size/2, -base_size/2, 0]) cube([base_size, base_size, base_thickness]);")

    # ---- Nodi + etichette ----
    out.append("")
    out.append("    // Nodi")
    for n in nodes:
        x, y = pos[n["id"]]
        label = n["id"]
        # la larghezza del testo è circa 0.65 * size per carattere: deve stare nel nodo
        size = min(node_r * 1.0, (1.5 * node_r) / (0.65 * max(1, len(label))))
        out.append(f"    // nodo {label}")
        out.append(f"    translate([{_f(x)}, {_f(y)}, base_thickness - 0.01]) "
                   f"cylinder(h = node_height + 0.01, r = node_radius);")
        out.append("    " + _text_block(label, size, x, y, BASE_THICKNESS + NODE_HEIGHT - 0.01,
                                         LABEL_HEIGHT + 0.01))

    # ---- Archi ----
    out.append("")
    out.append("    // Archi")
    edge_set = {(e["from"], e["to"]) for e in edges}
    gcx = sum(p[0] for p in pos.values()) / len(pos)
    gcy = sum(p[1] for p in pos.values()) / len(pos)
    seen_undirected = set()
    for e in edges:
        a, b = e["from"], e["to"]
        if a == b:
            out.append(f"    // cappio su {a}: non rappresentato")
            continue
        if not is_directed:
            key = frozenset((a, b))
            if key in seen_undirected:
                continue
            seen_undirected.add(key)
        (x1, y1), (x2, y2) = pos[a], pos[b]
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            continue
        ux, uy = dx / dist, dy / dist
        nx, ny = -uy, ux  # normale (a sinistra della direzione a -> b)

        # Archi opposti A->B e B->A: li affianchiamo invece di sovrapporli
        shift = edge_r * 2.5 if is_directed and (b, a) in edge_set else 0.0
        x1s, y1s, x2s, y2s = x1 + nx * shift, y1 + ny * shift, x2 + nx * shift, y2 + ny * shift

        overlap = node_r * 0.1  # entra leggermente nel nodo per fondersi
        start = (x1s + ux * (node_r - overlap), y1s + uy * (node_r - overlap))
        if is_directed:
            tip = (x2s - ux * node_r, y2s - uy * node_r)
            end = (tip[0] - ux * (arrow_len - overlap), tip[1] - uy * (arrow_len - overlap))
        else:
            end = (x2s - ux * (node_r - overlap), y2s - uy * (node_r - overlap))

        out.append(f"    // arco {a} {'->' if is_directed else '--'} {b}")
        if math.dist(start, end) > 0.1:
            out.append(f"    edge_segment([{_f(start[0])}, {_f(start[1])}], [{_f(end[0])}, {_f(end[1])}]);")
        if is_directed:
            angle = math.degrees(math.atan2(dy, dx))
            out.append(f"    arrow_head([{_f(tip[0])}, {_f(tip[1])}], {_f(angle)}, "
                       f"{_f(arrow_len)}, {_f(arrow_w)}, {_f(arrow_t)});")

        # Peso dell'arco: sulla base, a lato del punto medio, dal lato esterno del grafo
        weight = e.get("weight")
        if weight not in (None, ""):
            mx, my = (x1s + x2s) / 2, (y1s + y2s) / 2
            side = 1 if (nx * (mx - gcx) + ny * (my - gcy)) >= 0 else -1
            if shift:
                side = 1  # per gli archi affiancati, ognuno sul proprio lato
            off = edge_r + small_font * 0.9 + 1.0
            wx = _clamp(mx + nx * off * side, -limit, limit)
            wy = _clamp(my + ny * off * side, -limit, limit)
            out.append("    " + _text_block(weight, small_font, wx, wy, BASE_THICKNESS - 0.01,
                                             TEXT_HEIGHT + 0.01))

    # ---- Prezzi dei nodi ----
    prezzi = [n for n in nodes if n.get("price") not in (None, "")]
    if prezzi:
        out.append("")
        out.append("    // Prezzi dei nodi (sopra il nodo se nella metà alta, sotto altrimenti)")
        for n in prezzi:
            x, y = pos[n["id"]]
            off = node_r + small_font * 0.8 + 1.0
            py = y + off if y >= 0 else y - off
            if abs(py) > limit:  # non c'è spazio: lato opposto
                py = y - off if y >= 0 else y + off
            py = _clamp(py, -limit, limit)
            out.append("    " + _text_block(n["price"], small_font, x, py, BASE_THICKNESS - 0.01,
                                             TEXT_HEIGHT + 0.01))

    out.append("}")
    return "\n".join(out) + "\n"
