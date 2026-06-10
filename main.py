"""
AirClick v5.0 — Gestos Simples, Coherentes y Sin Confusión
Autores: Diter & Hord

FILOSOFÍA DE GESTOS v5:
  Se usan solo 3 gestos de acción + 1 de cambio de modo + puño de reset.
  Cada gesto es VISUALMENTE MUY DIFERENTE a los demás.
  El sistema YA NO depende de contar 3 vs 4 dedos (confundibles).

  PUÑO   ✊  (0 dedos) → Reset / neutro — mano completamente cerrada
  ÍNDICE ☝️  (1 dedo)  → Cambiar modo   — solo el índice apuntando
  PAZ    ✌️  (2 dedos) → Acción A       — índice + medio en V
  MANO   🖐️  (5 dedos) → Acción B       — todos los dedos abiertos
  OK     👌  (especial)→ Acción C       — índice + meñique separados (solo esos 2)

  DETECCIÓN OK: si índice Y meñique levantados pero medio Y anular NO.
  Es el gesto más distinto visualmente — no se confunde con ningún otro.

MODO se cambia con ☝️ y hay 4 modos: APPS, SISTEMA, VENTANAS, WEB
"""

import customtkinter as ctk
import cv2
import mediapipe as mp
from PIL import Image, ImageTk
import time
import subprocess
import ctypes
import threading
from collections import deque

# ══════════════════════════════════════════════════════════════════
#  CALIBRACIÓN
# ══════════════════════════════════════════════════════════════════
DEBOUNCE_MS      = 700     # ms de estabilidad antes de ejecutar
COOLDOWN_S       = 2.5     # pausa entre acciones
STABILITY_FRAMES = 9       # frames para votar el gesto estable
FINGER_THRESH    = 0.045   # umbral Y para dedo levantado
CAM_W, CAM_H     = 640, 480
VID_W, VID_H     = 480, 360

# ══════════════════════════════════════════════════════════════════
#  IDs DE GESTOS (internos)
# ══════════════════════════════════════════════════════════════════
G_PUNO   = 0   # ✊ puño — reset
G_INDICE = 1   # ☝️ índice — cambiar modo
G_PAZ    = 2   # ✌️ paz/V — acción A
G_MANO   = 5   # 🖐️ mano abierta — acción B
G_OK     = 9   # 👌 cuernos (índice+meñique) — acción C
G_OTROS  = -1  # cualquier otro conteo ambiguo → ignorar

GESTO_INFO = {
    G_PUNO:   {"nombre": "PUÑO",    "simbolo": "✊", "instruccion": "Mano cerrada = reset"},
    G_INDICE: {"nombre": "ÍNDICE",  "simbolo": "☝️",  "instruccion": "Solo índice = cambiar modo"},
    G_PAZ:    {"nombre": "PAZ  V",  "simbolo": "✌️",  "instruccion": "Índice + medio"},
    G_MANO:   {"nombre": "MANO",    "simbolo": "🖐️",  "instruccion": "Todos los dedos abiertos"},
    G_OK:     {"nombre": "CUERNOS", "simbolo": "🤘",  "instruccion": "Índice + meñique"},
    G_OTROS:  {"nombre": "—",       "simbolo": "…",   "instruccion": "Gesto no reconocido"},
}

# ══════════════════════════════════════════════════════════════════
#  FUNCIONES WINDOWS
# ══════════════════════════════════════════════════════════════════
def _key(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

def _combo(*vks):
    for v in vks:   ctypes.windll.user32.keybd_event(v, 0, 0, 0)
    for v in reversed(vks): ctypes.windll.user32.keybd_event(v, 0, 2, 0)

def _abrir(cmd, shell=False):
    subprocess.Popen(cmd, shell=shell)

def _vol_up():
    for _ in range(4): _key(0xAF)   # VK_VOLUME_UP ×4 pasos

def _vol_down():
    for _ in range(4): _key(0xAE)   # VK_VOLUME_DOWN

def _mute():       _key(0xAD)       # VK_VOLUME_MUTE
def _screenshot(): _key(0x2C)       # PrintScreen

def _escritorio(): _combo(0x5B, 0x44)  # Win+D
def _maximizar():  _combo(0x5B, 0x26)  # Win+Arriba
def _minimizar():  _combo(0x5B, 0x28)  # Win+Abajo
def _cerrar():     _combo(0x12, 0x73)  # Alt+F4

def _alt_tab():
    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
    time.sleep(0.06)
    ctypes.windll.user32.keybd_event(0x09, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x09, 0, 2, 0)
    time.sleep(0.9)
    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)

# ══════════════════════════════════════════════════════════════════
#  MODOS
#  3 acciones por modo: PAZ(A), MANO(B), OK/CUERNOS(C)
#  Coherencia: la acción "crece" en intensidad del gesto A→B→C
# ══════════════════════════════════════════════════════════════════
MODES = {
    # ── APPS ──────────────────────────────────────────────────────
    # ✌️  PAZ    → Calculadora  (2 dedos = operación = calcular)
    # 🖐️  MANO   → Explorador   (mano abierta = explorar archivos)
    # 🤘  CUERNOS→ Navegador    (cuernos = navegar libre = internet)
    "APPS": {
        "icon": "🖥️", "name": "Aplicaciones", "color": "#00D4AA",
        "acciones": {
            G_PAZ:  {"label": "Calculadora",  "icon": "🧮",
                     "razon": "✌️ 2 dedos = contar/calcular",
                     "fn": lambda: _abrir(["calc.exe"])},
            G_MANO: {"label": "Explorador",   "icon": "📁",
                     "razon": "🖐️ mano abierta = abrir carpetas",
                     "fn": lambda: _abrir(["explorer.exe"])},
            G_OK:   {"label": "Navegador Web","icon": "🌐",
                     "razon": "🤘 cuernos = navegar libremente",
                     "fn": lambda: _abrir("start https://www.google.com", shell=True)},
        },
    },
    # ── SISTEMA ───────────────────────────────────────────────────
    # ✌️  PAZ    → Subir volumen   (2 dedos = señal de +)
    # 🖐️  MANO   → Bajar volumen   (mano abierta = parar/bajar)
    # 🤘  CUERNOS→ Silenciar       (cuernos = shh! silencio)
    "SISTEMA": {
        "icon": "⚙️", "name": "Sistema", "color": "#FFB700",
        "acciones": {
            G_PAZ:  {"label": "Subir Volumen", "icon": "🔊",
                     "razon": "✌️ 2 dedos = señal de subir",
                     "fn": _vol_up},
            G_MANO: {"label": "Bajar Volumen", "icon": "🔉",
                     "razon": "🖐️ mano abierta = parar/bajar",
                     "fn": _vol_down},
            G_OK:   {"label": "Silenciar",     "icon": "🔇",
                     "razon": "🤘 cuernos = shh, silencio",
                     "fn": _mute},
        },
    },
    # ── VENTANAS ──────────────────────────────────────────────────
    # ✌️  PAZ    → Mostrar escritorio  (2 dedos = separar / peinar)
    # 🖐️  MANO   → Cambiar ventana     (mano completa = Alt+Tab)
    # 🤘  CUERNOS→ Cerrar ventana      (cuernos = X = cerrar)
    "VENTANAS": {
        "icon": "🪟", "name": "Ventanas", "color": "#9B88FF",
        "acciones": {
            G_PAZ:  {"label": "Mostrar Escritorio", "icon": "🗔",
                     "razon": "✌️ 2 dedos = separar ventanas",
                     "fn": _escritorio},
            G_MANO: {"label": "Cambiar Ventana",    "icon": "🔄",
                     "razon": "🖐️ mano = cambiar todo (Alt+Tab)",
                     "fn": _alt_tab},
            G_OK:   {"label": "Cerrar Ventana",     "icon": "✖️",
                     "razon": "🤘 cuernos = X = cerrar",
                     "fn": _cerrar},
        },
    },
    # ── WEB ───────────────────────────────────────────────────────
    # ✌️  PAZ    → YouTube   (2 dedos = pantalla / reproducir)
    # 🖐️  MANO   → WhatsApp  (mano = hola / saludo = chat)
    # 🤘  CUERNOS→ ChatGPT   (cuernos = IA / robótico)
    "WEB": {
        "icon": "🌍", "name": "Web Rápida", "color": "#FF6B9D",
        "acciones": {
            G_PAZ:  {"label": "YouTube",    "icon": "▶️",
                     "razon": "✌️ 2 dedos = pantalla de video",
                     "fn": lambda: _abrir("start https://youtube.com", shell=True)},
            G_MANO: {"label": "WhatsApp",   "icon": "💬",
                     "razon": "🖐️ mano = saludo = chat",
                     "fn": lambda: _abrir("start https://web.whatsapp.com", shell=True)},
            G_OK:   {"label": "ChatGPT",    "icon": "🤖",
                     "razon": "🤘 cuernos = IA / robot",
                     "fn": lambda: _abrir("start https://chat.openai.com", shell=True)},
        },
    },
}

MODE_ORDER = ["APPS", "SISTEMA", "VENTANAS", "WEB"]

# ══════════════════════════════════════════════════════════════════
#  ESTADOS
# ══════════════════════════════════════════════════════════════════
class GS:
    IDLE = "IDLE"; DETECTING = "DETECTING"
    CONFIRMED = "CONFIRMED"; LOCKED = "LOCKED"

# ══════════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════════
class AirClickApp:

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("AirClick v5.0")
        self.root.resizable(True, True)

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False, max_num_hands=1,
            min_detection_confidence=0.75, min_tracking_confidence=0.75)
        self.mp_draw  = mp.solutions.drawing_utils
        self.mp_style = mp.solutions.drawing_styles

        self.current_mode   = "APPS"
        self.state          = GS.IDLE
        self.candidate_gest = G_PUNO
        self.last_gest      = G_PUNO
        self.debounce_start = 0.0
        self.last_action_t  = 0.0
        self.frame_buf: deque[int] = deque(maxlen=STABILITY_FRAMES)

        self.cap = None
        self.running = False

        self._build_gui()

    # ─────────────────────────────────────────────────────────────
    #  GUI
    # ─────────────────────────────────────────────────────────────
    def _build_gui(self):
        self.root.configure(fg_color="#0B0B14")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=0)

        # ══ HEADER ════════════════════════════════════════════════
        header = ctk.CTkFrame(self.root, fg_color="#111120", corner_radius=0, height=54)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        header.grid_propagate(False)

        ctk.CTkLabel(header, text="✋  AirClick",
                     font=ctk.CTkFont("Arial", 20, "bold"),
                     text_color="#00D4AA").grid(row=0, column=0, padx=18, pady=14)

        self.lbl_modo_header = ctk.CTkLabel(header,
            text="MODO  🖥️  APLICACIONES",
            font=ctk.CTkFont("Arial", 13, "bold"),
            text_color="#FFB700")
        self.lbl_modo_header.grid(row=0, column=1, sticky="w", padx=6)

        self.lbl_gesto_header = ctk.CTkLabel(header,
            text="✊  PUÑO",
            font=ctk.CTkFont("Arial", 13),
            text_color="#555566")
        self.lbl_gesto_header.grid(row=0, column=2, sticky="e", padx=18)

        # ══ BODY ══════════════════════════════════════════════════
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(10, 6))
        body.columnconfigure(0, weight=5)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # ── Columna izquierda: cámara ──────────────────────────
        cam_frame = ctk.CTkFrame(body, fg_color="#0D0D1C", corner_radius=12)
        cam_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cam_frame.columnconfigure(0, weight=1)
        cam_frame.rowconfigure(1, weight=1)

        self.lbl_video = ctk.CTkLabel(cam_frame,
            text="Presiona  ▶  para iniciar la cámara",
            width=VID_W, height=VID_H,
            fg_color="#080812", corner_radius=10,
            text_color="#2A2A44",
            font=ctk.CTkFont("Arial", 12))
        self.lbl_video.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="nsew")

        # Barra de estabilidad
        prog_row = ctk.CTkFrame(cam_frame, fg_color="transparent")
        prog_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        prog_row.columnconfigure(0, weight=1)

        ctk.CTkLabel(prog_row, text="ESTABILIDAD",
                     font=ctk.CTkFont("Arial", 8, "bold"),
                     text_color="#333344").grid(row=0, column=0, sticky="w")
        self.lbl_pct = ctk.CTkLabel(prog_row, text="0%",
                     font=ctk.CTkFont("Arial", 8, "bold"),
                     text_color="#00D4AA")
        self.lbl_pct.grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(cam_frame, height=5,
                                           corner_radius=3,
                                           fg_color="#111122",
                                           progress_color="#00D4AA")
        self.progress.set(0)
        self.progress.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

        # Estado (mensaje de feedback)
        self.lbl_estado = ctk.CTkLabel(cam_frame,
            text="● IDLE  —  Esperando mano…",
            font=ctk.CTkFont("Arial", 11),
            text_color="#444455")
        self.lbl_estado.grid(row=3, column=0, pady=(0, 10))

        # ── Columna derecha: panel de control ──────────────────
        panel = ctk.CTkFrame(body, fg_color="#0D0D1C", corner_radius=12)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)

        # Selector de modo (tabs estilo botones)
        ctk.CTkLabel(panel, text="MODO ACTIVO",
                     font=ctk.CTkFont("Arial", 9, "bold"),
                     text_color="#333344").grid(row=0, column=0, pady=(12, 4))

        tabs = ctk.CTkFrame(panel, fg_color="#080812", corner_radius=8)
        tabs.grid(row=1, column=0, padx=10, sticky="ew")
        tabs.columnconfigure((0,1), weight=1)

        self._tab_btns: dict[str, ctk.CTkButton] = {}
        for i, m in enumerate(MODE_ORDER):
            info = MODES[m]
            r, c = divmod(i, 2)
            btn = ctk.CTkButton(tabs,
                text=f"{info['icon']}\n{info['name']}",
                command=lambda mode=m: self._cambiar_modo_manual(mode),
                font=ctk.CTkFont("Arial", 10, "bold"),
                height=46, corner_radius=6,
                fg_color="#141428",
                hover_color="#1E1E3A",
                text_color="#777788",
                border_width=1,
                border_color="#222233")
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
            self._tab_btns[m] = btn

        ctk.CTkLabel(panel, text="☝️  1 dedo = ciclar modo",
                     font=ctk.CTkFont("Arial", 8),
                     text_color="#2A2A40").grid(row=2, column=0, pady=(2, 8))

        # Gestos disponibles (3 tarjetas)
        ctk.CTkLabel(panel, text="GESTOS DEL MODO",
                     font=ctk.CTkFont("Arial", 9, "bold"),
                     text_color="#333344").grid(row=3, column=0, pady=(0, 4))

        cards = ctk.CTkFrame(panel, fg_color="transparent")
        cards.grid(row=4, column=0, padx=10, sticky="ew")
        cards.columnconfigure(0, weight=1)

        self._cards: list[dict] = []
        GESTURE_KEYS = [G_PAZ, G_MANO, G_OK]
        for i, gk in enumerate(GESTURE_KEYS):
            card = ctk.CTkFrame(cards, fg_color="#0A0A18",
                                corner_radius=8,
                                border_width=1, border_color="#1A1A2E")
            card.grid(row=i, column=0, sticky="ew", pady=3)
            card.columnconfigure(1, weight=1)

            sym_lbl = ctk.CTkLabel(card,
                text=GESTO_INFO[gk]["simbolo"],
                font=ctk.CTkFont("Arial", 18),
                width=40)
            sym_lbl.grid(row=0, column=0, rowspan=2, padx=(8,4), pady=6)

            accion_lbl = ctk.CTkLabel(card, text="—",
                font=ctk.CTkFont("Arial", 12, "bold"),
                text_color="#CCCCDD", anchor="w")
            accion_lbl.grid(row=0, column=1, sticky="w", padx=4, pady=(6, 0))

            razon_lbl = ctk.CTkLabel(card, text="—",
                font=ctk.CTkFont("Arial", 9),
                text_color="#44445A", anchor="w")
            razon_lbl.grid(row=1, column=1, sticky="w", padx=4, pady=(0, 6))

            self._cards.append({
                "card": card, "accion": accion_lbl, "razon": razon_lbl
            })

        # Reset hint
        reset_f = ctk.CTkFrame(panel, fg_color="#1A0A0A",
                               corner_radius=6, border_width=1,
                               border_color="#3A1A1A")
        reset_f.grid(row=5, column=0, padx=10, pady=(8, 4), sticky="ew")
        ctk.CTkLabel(reset_f,
                     text="✊  Puño cerrado  →  Resetear",
                     font=ctk.CTkFont("Arial", 10, "bold"),
                     text_color="#994444").pack(pady=6)

        # Log
        ctk.CTkLabel(panel, text="HISTORIAL",
                     font=ctk.CTkFont("Arial", 9, "bold"),
                     text_color="#333344").grid(row=6, column=0, pady=(6, 2))

        self.log_box = ctk.CTkTextbox(panel, height=100,
            font=ctk.CTkFont("Consolas", 9),
            fg_color="#060610", text_color="#00BB66",
            state="disabled", corner_radius=6)
        self.log_box.grid(row=7, column=0, padx=10, pady=(0, 12), sticky="ew")

        # ══ FOOTER ════════════════════════════════════════════════
        footer = ctk.CTkFrame(self.root, fg_color="#0D0D1C",
                              corner_radius=0, height=56)
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        footer.grid_propagate(False)

        self.btn_cam = ctk.CTkButton(footer,
            text="▶  Iniciar Cámara",
            command=self._start_camera,
            fg_color="#1A6B35", hover_color="#28a745",
            font=ctk.CTkFont("Arial", 13, "bold"),
            width=180, height=36, corner_radius=8)
        self.btn_cam.grid(row=0, column=0, padx=14, pady=10)

        ctk.CTkLabel(footer,
            text="AirClick v5  •  Diter & Hord  •  Proyecto Universitario",
            font=ctk.CTkFont("Arial", 9),
            text_color="#222233").grid(row=0, column=1, sticky="e", padx=14)

        # Inicializar panel
        self._actualizar_panel()

        self.root.update_idletasks()
        w = max(self.root.winfo_reqwidth() + 20, 820)
        h = max(self.root.winfo_reqheight() + 20, 640)
        self.root.geometry(f"{w}x{h}")

    # ─────────────────────────────────────────────────────────────
    #  ACTUALIZAR PANEL DERECHO
    # ─────────────────────────────────────────────────────────────
    def _actualizar_panel(self):
        m     = MODES[self.current_mode]
        color = m["color"]

        # Header
        self.lbl_modo_header.configure(
            text=f"MODO  {m['icon']}  {m['name'].upper()}",
            text_color=color)

        # Barra de estabilidad
        self.progress.configure(progress_color=color)

        # Tab activo resaltado
        for k, btn in self._tab_btns.items():
            if k == self.current_mode:
                btn.configure(
                    fg_color="#1A1A36",
                    border_color=color,
                    text_color=color)
            else:
                btn.configure(
                    fg_color="#141428",
                    border_color="#222233",
                    text_color="#555566")

        # Tarjetas de gestos
        GESTURE_KEYS = [G_PAZ, G_MANO, G_OK]
        for i, gk in enumerate(GESTURE_KEYS):
            act = m["acciones"].get(gk, {})
            self._cards[i]["accion"].configure(
                text=f"{act.get('icon','')}  {act.get('label','—')}")
            self._cards[i]["razon"].configure(
                text=act.get("razon", "—"))

    def _cambiar_modo_manual(self, mode: str):
        self.current_mode = mode
        self._actualizar_panel()
        self._reset_machine()
        self._log(f"Modo → {mode}")

    def _ciclar_modo(self):
        idx = MODE_ORDER.index(self.current_mode)
        self.current_mode = MODE_ORDER[(idx + 1) % len(MODE_ORDER)]
        self._actualizar_panel()
        self._log(f"→ {self.current_mode} {MODES[self.current_mode]['icon']}")

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────
    #  CÁMARA
    # ─────────────────────────────────────────────────────────────
    def _start_camera(self):
        if self.running: return
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            self.lbl_estado.configure(
                text="❌ Cámara no detectada", text_color="#FF4444")
            return
        self.running = True
        self.btn_cam.configure(state="disabled", text="📷  Activa")
        self._update()

    # ─────────────────────────────────────────────────────────────
    #  DETECCIÓN DE GESTOS
    #
    #  Reconoce exactamente 5 gestos definidos.
    #  Todo lo demás devuelve G_OTROS (-1) = ignorado.
    #
    #  PUNTOS MediaPipe usados:
    #    Índice:  punta=8,  base=5
    #    Medio:   punta=12, base=9
    #    Anular:  punta=16, base=13
    #    Meñique: punta=20, base=17
    # ─────────────────────────────────────────────────────────────
    def _dedo_levantado(self, lm, tip: int, base: int) -> bool:
        return (lm[base].y - lm[tip].y) > FINGER_THRESH

    def get_gesture(self, rgb) -> int:
        results = self.hands.process(rgb)

        if not results.multi_hand_landmarks:
            self.frame_buf.append(G_PUNO)
            return G_PUNO

        hand = results.multi_hand_landmarks[0]
        self.mp_draw.draw_landmarks(
            rgb, hand,
            self.mp_hands.HAND_CONNECTIONS,
            self.mp_style.get_default_hand_landmarks_style(),
            self.mp_style.get_default_hand_connections_style())

        lm = hand.landmark
        idx = self._dedo_levantado(lm, 8,  5)   # índice
        mid = self._dedo_levantado(lm, 12, 9)   # medio
        anu = self._dedo_levantado(lm, 16, 13)  # anular
        men = self._dedo_levantado(lm, 20, 17)  # meñique

        # Clasificar gesto según patrón booleano exacto
        # Solo aceptamos patrones bien definidos; cualquier otro → G_OTROS
        pattern = (idx, mid, anu, men)

        if   pattern == (False, False, False, False): raw = G_PUNO    # ✊ puño
        elif pattern == (True,  False, False, False): raw = G_INDICE  # ☝️ índice
        elif pattern == (True,  True,  False, False): raw = G_PAZ     # ✌️ paz
        elif pattern == (True,  True,  True,  True ): raw = G_MANO    # 🖐️ mano (sin pulgar)
        elif pattern == (True,  False, False, True ): raw = G_OK      # 🤘 cuernos
        else: raw = G_OTROS  # patrón ambiguo → ignorar

        self.frame_buf.append(raw)
        return max(set(self.frame_buf), key=self.frame_buf.count)

    # ─────────────────────────────────────────────────────────────
    #  EJECUTAR ACCIÓN
    # ─────────────────────────────────────────────────────────────
    def execute_action(self, g: int):
        if g == G_INDICE:
            self._ciclar_modo()
            return

        mode   = MODES[self.current_mode]
        action = mode["acciones"].get(g)
        if not action:
            return

        label = f"{action['icon']} {action['label']}"
        try:
            threading.Thread(target=action["fn"], daemon=True).start()
            self.last_action_t = time.time()
            self.lbl_estado.configure(
                text=f"✅  {label}", text_color="#00FF88")
            self._log(f"[{self.current_mode}] {label}")
        except Exception as e:
            self.lbl_estado.configure(text=f"❌ {e}", text_color="#FF4444")

    # ─────────────────────────────────────────────────────────────
    #  STATE MACHINE
    # ─────────────────────────────────────────────────────────────
    def _reset_machine(self):
        self.state          = GS.IDLE
        self.candidate_gest = G_PUNO
        self.last_gest      = G_PUNO
        self.frame_buf.clear()
        self.progress.set(0)
        self.lbl_pct.configure(text="0%")

    def tick(self, g: int):
        now   = time.time()
        deb_s = DEBOUNCE_MS / 1000.0
        pval  = 0.0
        color = MODES[self.current_mode]["color"]

        gi  = GESTO_INFO.get(g, GESTO_INFO[G_OTROS])
        sym = gi["simbolo"]

        # Actualizar header gesto
        self.lbl_gesto_header.configure(
            text=f"{sym}  {gi['nombre']}",
            text_color=color if g not in (G_PUNO, G_OTROS) else "#555566")

        # ── IDLE ─────────────────────────────────────────────────
        if self.state == GS.IDLE:
            if g in (G_INDICE, G_PAZ, G_MANO, G_OK):
                self.state          = GS.DETECTING
                self.candidate_gest = g
                self.debounce_start = now
                self.lbl_estado.configure(
                    text=f"🔍  {sym}  {gi['nombre']}  detectado…",
                    text_color=color)
            elif g == G_PUNO:
                self.lbl_estado.configure(
                    text="✊  Listo — levanta un gesto",
                    text_color="#444455")

        # ── DETECTING ────────────────────────────────────────────
        elif self.state == GS.DETECTING:
            if g == G_OTROS:
                # Gesto ambiguo → esperar sin reiniciar
                return
            if g != self.candidate_gest:
                # Gesto distinto → reiniciar con el nuevo
                self.candidate_gest = g
                self.debounce_start = now
                gi2 = GESTO_INFO.get(g, GESTO_INFO[G_OTROS])
                self.lbl_estado.configure(
                    text=f"🔄  Cambiando a {gi2['simbolo']} {gi2['nombre']}…",
                    text_color=color)
                self.progress.set(0)
                return

            elapsed = now - self.debounce_start
            pval    = min(elapsed / deb_s, 1.0)
            if elapsed >= deb_s:
                self.state = GS.CONFIRMED

        # ── CONFIRMED ────────────────────────────────────────────
        elif self.state == GS.CONFIRMED:
            pval = 1.0
            if self.candidate_gest == self.last_gest:
                self.state = GS.LOCKED
                self.lbl_estado.configure(
                    text="🔒  Ejecutado — cierra la mano ✊",
                    text_color="#555566")
                return
            if now - self.last_action_t < COOLDOWN_S:
                rem = COOLDOWN_S - (now - self.last_action_t)
                self.lbl_estado.configure(
                    text=f"⏳  Cooldown {rem:.1f}s…", text_color="#888899")
                return

            self.execute_action(self.candidate_gest)
            self.last_gest = self.candidate_gest
            self.state     = GS.LOCKED

        # ── LOCKED ───────────────────────────────────────────────
        elif self.state == GS.LOCKED:
            pval = 1.0
            if g == G_PUNO:
                self._reset_machine()
                self.lbl_estado.configure(
                    text="✊  Reseteado — listo para otro gesto",
                    text_color="#00D4AA")
                return

        self.progress.set(pval)
        self.lbl_pct.configure(text=f"{int(pval*100)}%")

    # ─────────────────────────────────────────────────────────────
    #  BUCLE PRINCIPAL
    # ─────────────────────────────────────────────────────────────
    def _update(self):
        if not self.running: return

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            g  = self.get_gesture(rgb)
            self.tick(g)

            # Overlay limpio en video
            gi   = GESTO_INFO.get(g, GESTO_INFO[G_OTROS])
            col  = (0, 212, 170) if g not in (G_PUNO, G_OTROS) else (80, 80, 100)

            cv2.rectangle(rgb, (0, 0), (260, 60), (8, 8, 20), -1)
            cv2.putText(rgb, f"MODO: {self.current_mode}",
                        (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (180, 180, 200), 1, cv2.LINE_AA)
            cv2.putText(rgb, f"GESTO: {gi['nombre']}",
                        (8, 44), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, col, 2, cv2.LINE_AA)
            cv2.putText(rgb, f"[ {self.state} ]",
                        (8, CAM_H - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.42, (60, 60, 90), 1, cv2.LINE_AA)

            img   = Image.fromarray(rgb).resize((VID_W, VID_H), Image.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.lbl_video.configure(image=imgtk, text="")
            self.lbl_video.image = imgtk

        self.root.after(10, self._update)


# ══════════════════════════════════════════════════════════════════
#  ARRANQUE
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    app  = AirClickApp(root)
    root.mainloop()