#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reproductor de musica en terminal (TUI).
Offline, sin dependencias externas: usa la libreria estandar de Python
(curses) + ffplay/ffprobe (de ffmpeg) como motor de audio.

Funciones:
  - Navegacion rapida por carpetas anidadas (artista/album/track).
  - Salto incremental escribiendo el nombre.
  - Reproduccion secuencial dentro de una carpeta.
  - Shuffle de carpeta (recursivo) y shuffle GLOBAL de toda la biblioteca.
  - Aleatoriedad 100%: sin repeticiones hasta agotar todas las pistas.
  - Favoritos y listas propias (.m3u en ~/.local/share/reproductor/).
  - Adelantar/retroceder dentro de la pista, silencio rapido, vista de cola.
  - Continuar la sesion anterior donde quedo (carpeta, volumen y pista).
  - Temporizador de apagado, contador de reproducciones, tags ID3 reales.
  - Pausa, siguiente, anterior, volumen, barra de progreso.

Controles:
  Flechas ↑/↓ ......... mover cursor
  Enter ............... entrar a carpeta / reproducir pista
  ← / Backspace ....... subir un nivel
  / ................... buscar en toda la biblioteca (Enter reproduce, ESC sale)
  s ................... shuffle de la carpeta actual (recursivo)
  g ................... shuffle GLOBAL de toda la biblioteca
  f ................... seguir navegacion (la siguiente sale de donde estes)
  a ................... marcar / desmarcar favorito ♥
  v ................... ver la lista de favoritos
  A / V ............... agregar a una lista / abrir listas guardadas
  u ................... ver la cola (Enter salta a esa pista)
  r ................... cambiar la siguiente pista anunciada
  Espacio ............. pausa / reanudar
  n / b ............... siguiente / anterior
  , / . ............... retroceder / adelantar 10s  (< / > = 60s)
  + / - ............... subir / bajar volumen
  m ................... silenciar / restaurar
  t ................... temporizador de apagado (15/30/60/90 min)
  c ................... continuar donde quedaste (sesion anterior)
  escribir letras ..... saltar a la entrada que coincide
  ESC ................. limpiar busqueda
  q ................... salir
"""

import os
import sys
import json
import time
import math
import random
import signal
import subprocess
import curses

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav", ".wma", ".aac", ".m4b"}

# bloques de menor a mayor altura, para la animacion del ecualizador
EQ_BLOCKS = "▁▂▃▄▅▆▇█"

# (tecla, descripcion) para la pantalla de ayuda (tecla '?' o 'h')
HELP_LINES = [
    ("↑ ↓  ·  j k", "mover el cursor"),
    ("RePág / AvPág", "saltar 10 entradas"),
    ("Inicio / Fin", "ir al principio / al final"),
    ("Enter", "entrar a la carpeta / reproducir pista"),
    ("← / Backspace", "subir un nivel"),
    ("escribir letras", "salto incremental a la entrada que coincide"),
    ("/", "buscar en TODA la biblioteca"),
    ("s", "shuffle de la carpeta actual (recursivo)"),
    ("g", "shuffle GLOBAL de toda la biblioteca"),
    ("f", "seguir navegación (la siguiente sale de donde estés)"),
    ("a", "marcar / desmarcar favorito ♥ (pista del cursor o la que suena)"),
    ("v", "ver la lista de favoritos (Enter reproduce, s shuffle)"),
    ("A", "agregar la pista a una lista (o crear una nueva)"),
    ("V", "abrir las listas guardadas y las más escuchadas"),
    ("u", "ver la cola: Enter salta directo a esa pista"),
    ("r", "cambiar la siguiente pista anunciada"),
    ("Espacio", "pausa / reanudar"),
    ("n / b", "siguiente / anterior canción"),
    (", / .", "retroceder / adelantar 10 s   (< / > = 60 s)"),
    ("+ / -", "subir / bajar volumen"),
    ("m", "silenciar / restaurar volumen"),
    ("t", "temporizador de apagado: 15 / 30 / 60 / 90 min / off"),
    ("c", "continuar donde quedaste en la sesión anterior"),
    ("? / h", "mostrar esta ayuda"),
    ("ESC", "limpiar búsqueda / cerrar buscador"),
    ("q", "salir"),
]


def find_music_root():
    """Localiza la carpeta de musica. Acepta un argumento de linea de comandos."""
    if len(sys.argv) > 1:
        p = os.path.expanduser(sys.argv[1])
        if os.path.isdir(p):
            return os.path.abspath(p)
    home = os.path.expanduser("~")
    for name in ("Música", "Music", "musica", "Musica"):
        cand = os.path.join(home, name)
        if os.path.isdir(cand):
            return cand
    # ultima opcion: carpeta "musica" junto al script
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "musica")
    if os.path.isdir(here):
        return here
    return home


def is_audio(path):
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


def list_dir(path):
    """Devuelve (carpetas, archivos_audio) ordenados alfabeticamente."""
    dirs, files = [], []
    try:
        for entry in os.scandir(path):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append(entry.name)
            elif entry.is_file() and is_audio(entry.name):
                files.append(entry.name)
    except PermissionError:
        pass
    dirs.sort(key=str.lower)
    files.sort(key=str.lower)
    return dirs, files


def collect_tracks(path):
    """Todas las pistas de audio bajo 'path', recursivo, ordenadas por ruta."""
    tracks = []
    for root, dnames, fnames in os.walk(path):
        dnames[:] = [d for d in dnames if not d.startswith(".")]
        for f in fnames:
            if is_audio(f):
                tracks.append(os.path.join(root, f))
    tracks.sort(key=str.lower)
    return tracks


def probe(path):
    """Duracion y tags reales (titulo/artista/album) via ffprobe, en un solo llamado."""
    info = {"duration": 0.0, "title": "", "artist": "", "album": ""}
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:format_tags=title,artist,album",
             "-of", "default=noprint_wrappers=1", path],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for line in out.splitlines():
            key, _, val = line.partition("=")
            key = key.strip().lower().replace("tag:", "")
            val = val.strip()
            if key == "duration":
                info["duration"] = float(val)
            elif key in info:
                info[key] = val
    except Exception:
        pass
    return info


def fmt_time(secs):
    secs = int(max(0, secs))
    return f"{secs // 60:02d}:{secs % 60:02d}"


# ---- datos persistentes (listas, contador, estado) ----
# Las listas se guardan como .m3u normales (una ruta por linea), asi tambien
# sirven en otros reproductores. Favoritos es simplemente favoritos.m3u.
PLAYLIST_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "reproductor")
FAV_FILE = os.path.join(PLAYLIST_DIR, "favoritos.m3u")
CNT_FILE = os.path.join(PLAYLIST_DIR, "conteo.json")     # reproducciones por pista
STATE_FILE = os.path.join(PLAYLIST_DIR, "estado.json")   # para continuar la sesion


def load_m3u(path):
    """Lee las rutas de un .m3u; lista vacia si no existe."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return [ln.strip() for ln in fh
                    if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []


def save_m3u(path, tracks):
    """Escribe un .m3u (best-effort)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#EXTM3U\n")
            for p in tracks:
                fh.write(p + "\n")
    except OSError:
        pass


def load_favorites():
    return load_m3u(FAV_FILE)


def save_favorites(favs):
    save_m3u(FAV_FILE, favs)


def list_playlists():
    """Todas las listas guardadas: [(nombre, ruta)], favoritos primero."""
    try:
        files = [f for f in os.listdir(PLAYLIST_DIR) if f.endswith(".m3u")]
    except OSError:
        files = []
    out = [(os.path.splitext(f)[0], os.path.join(PLAYLIST_DIR, f)) for f in files]
    out.sort(key=lambda t: (t[1] != FAV_FILE, t[0].lower()))
    return out


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception:
        pass


class NoRepeatQueue:
    """
    Cola de reproduccion aleatoria SIN repeticiones hasta agotar la lista.
    Cuando se agota, vuelve a barajar; evita que la primera pista del nuevo
    ciclo sea igual a la ultima reproducida (sin repeticion en el empalme).
    Tambien soporta orden secuencial (shuffle=False).

    Internamente lleva 'history' (lo ya reproducido; el ultimo elemento es la
    pista actual) y 'upcoming' (lo que viene). Asi se puede mirar la siguiente
    pista (peek_next) o cambiarla (reroll_next) sin romper el no-repeticion.
    """

    def __init__(self, tracks, shuffle=True, start_index=0):
        self.base = list(tracks)
        self.shuffle = shuffle
        self.history = []      # indices reproducidos; history[-1] = pista actual
        self.upcoming = []     # indices por venir, en orden de reproduccion
        if not self.base:
            return
        if shuffle:
            order = list(range(len(self.base)))
            random.shuffle(order)
            self.upcoming = order
            self.history.append(self.upcoming.pop(0))
        else:
            start = max(0, min(start_index, len(self.base) - 1))
            self.history = list(range(start + 1))           # actual = start
            self.upcoming = list(range(start + 1, len(self.base)))

    def _refill(self):
        """Baraja un ciclo nuevo, sin repetir la pista actual en el empalme."""
        last = self.history[-1] if self.history else None
        order = list(range(len(self.base)))
        random.shuffle(order)
        if last is not None and len(order) > 1 and order[0] == last:
            order[0], order[1] = order[1], order[0]
        self.upcoming = order

    def current(self):
        if not self.history:
            return None
        return self.base[self.history[-1]]

    def peek_next(self):
        """La pista que sonaria al avanzar, sin avanzar. None si no hay."""
        if not self.base:
            return None
        if not self.upcoming:
            if self.shuffle:
                self._refill()
            else:
                return None                                 # secuencial: fin
        return self.base[self.upcoming[0]] if self.upcoming else None

    def reroll_next(self):
        """Cambia la proxima pista por otra del ciclo restante (solo shuffle)."""
        if not self.shuffle or not self.base:
            return self.peek_next()
        if not self.upcoming:
            self._refill()
        if len(self.upcoming) > 1:
            j = random.randrange(1, len(self.upcoming))
            self.upcoming[0], self.upcoming[j] = self.upcoming[j], self.upcoming[0]
        return self.peek_next()

    def advance(self):
        if not self.base:
            return None
        if not self.upcoming:
            if self.shuffle:
                self._refill()
            else:
                return self.current()                       # secuencial: se queda al final
        if self.upcoming:
            self.history.append(self.upcoming.pop(0))
        return self.current()

    def back(self):
        if len(self.history) > 1:
            self.upcoming.insert(0, self.history.pop())
        return self.current()


class AudioPlayer:
    """Motor de audio basado en ffplay, controlado por senales del proceso."""

    def __init__(self):
        self.proc = None
        self.path = None
        self.duration = 0.0
        self.volume = 80
        self.muted = False
        self.paused = False
        self.tags = {}                 # titulo/artista/album reales de la pista actual
        self._start = 0.0
        self._paused_at = 0.0
        self._paused_total = 0.0

    def play(self, path, start=0.0):
        """Reproduce 'path'; con start > 0 arranca en esa posicion (via -ss)."""
        self.stop()
        if path != self.path or self.duration <= 0:
            info = probe(path)         # una sola sonda por pista (seek no re-sondea)
            self.duration = info["duration"]
            self.tags = {k: info[k] for k in ("title", "artist", "album")}
        self.path = path
        self.paused = False
        self._paused_total = 0.0
        self._start = time.monotonic() - start
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
               "-volume", str(0 if self.muted else self.volume)]
        if start > 0:
            cmd += ["-ss", f"{start:.2f}"]
        self.proc = subprocess.Popen(
            cmd + [path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._apply_volume()

    def seek(self, delta):
        """Salta dentro de la pista. ffplay no permite seek en vivo, asi que se
        relanza el proceso con -ss en la nueva posicion (quita la pausa)."""
        if not self.path or not self.proc:
            return
        pos = max(0.0, self.elapsed() + delta)
        if self.duration > 0:
            pos = min(pos, max(0.0, self.duration - 1.0))
        self.play(self.path, start=pos)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                if self.paused:
                    self.proc.send_signal(signal.SIGCONT)
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.paused = False

    def toggle_pause(self):
        if not self.proc or self.proc.poll() is not None:
            return
        if self.paused:
            self.proc.send_signal(signal.SIGCONT)
            self._paused_total += time.monotonic() - self._paused_at
            self.paused = False
        else:
            self.proc.send_signal(signal.SIGSTOP)
            self._paused_at = time.monotonic()
            self.paused = True

    def is_finished(self):
        """True cuando la pista termino sola (no en pausa)."""
        return self.proc is not None and not self.paused and self.proc.poll() is not None

    def elapsed(self):
        if not self.proc:
            return 0.0
        if self.paused:
            return self._paused_at - self._start - self._paused_total
        return time.monotonic() - self._start - self._paused_total

    def change_volume(self, delta):
        self.muted = False
        self.volume = max(0, min(100, self.volume + delta))
        self._apply_volume()

    def toggle_mute(self):
        self.muted = not self.muted
        self._apply_volume()

    def _apply_volume(self):
        """Ajusta el volumen en vivo via PulseAudio (best-effort)."""
        if not self.proc:
            return
        try:
            # LC_ALL=C fuerza la salida en ingles ("Sink Input #"); si no, en
            # sistemas localizados (p.ej. espanol -> "Entrada del destino #")
            # el encabezado no coincide y el volumen nunca se aplica.
            env = dict(os.environ, LC_ALL="C")
            out = subprocess.run(["pactl", "list", "sink-inputs"],
                                 capture_output=True, text=True, timeout=3,
                                 env=env).stdout
            index = None
            cur = None
            for line in out.splitlines():
                s = line.strip()
                if s.startswith("Sink Input #"):
                    cur = s.split("#")[1].strip()
                elif "application.process.id" in s and str(self.proc.pid) in s:
                    index = cur
            if index is not None:
                vol = 0 if self.muted else self.volume
                subprocess.run(["pactl", "set-sink-input-volume", index, f"{vol}%"],
                               capture_output=True, timeout=3, env=env)
        except Exception:
            pass


class App:
    def __init__(self, stdscr, root):
        self.scr = stdscr
        self.root = root
        self.cwd = root
        self.cursor = 0
        self.top = 0
        self.entries = []          # lista de (label, kind, path)  kind: up|dir|file
        self.player = AudioPlayer()
        self.queue = None
        self.queue_label = ""
        self.search = ""
        self.follow = False            # modo "sigue mi navegacion"
        self.follow_next = None        # siguiente pista precalculada (modo follow)
        self.follow_history = []        # pistas anteriores (modo follow), para 'b'
        self.searching = False         # buscador global activo
        self.query = ""                # texto del buscador
        self.favorites = load_favorites()  # rutas favoritas, en orden de marcado
        self.listview = None           # titulo de la lista virtual activa (favoritos, cola…)
        self.counts = load_json(CNT_FILE)  # reproducciones por pista
        self.pending_add = None        # pista esperando lista destino (tecla 'A')
        self.prompt = None             # etiqueta del prompt de texto activo (o None)
        self.prompt_text = ""
        self.sleep_until = None        # temporizador de apagado (time.monotonic)
        self.sleep_choice = None       # minutos elegidos, para ciclar con 't'
        self.resume = None             # (pista, posicion) de la sesion anterior
        self.all_tracks = None         # indice de toda la biblioteca (lazy)
        self.show_help = False         # pantalla de ayuda visible
        self.anim = 0                  # reloj de animacion; solo avanza al sonar
        self.has_colors = False
        self._title = None             # ultimo titulo de pestaña escrito
        self._tty = sys.stdout.isatty()
        # restaurar la sesion anterior: carpeta, volumen y pista para continuar
        st = load_json(STATE_FILE)
        if isinstance(st.get("volume"), (int, float)):
            self.player.volume = max(0, min(100, int(st["volume"])))
        if st.get("cwd") and os.path.isdir(st["cwd"]):
            self.cwd = st["cwd"]
        if st.get("track") and os.path.exists(st["track"]):
            self.resume = (st["track"], float(st.get("pos", 0.0)))
        self.status = "Listo. [g] global  [s] carpeta  [f] seguir navegación  [?] ayuda"
        self.refresh_entries()
        if self.resume:
            self.status = ("⏯ 'c' continúa: " + self.track_label(self.resume[0])
                           + f" ({fmt_time(self.resume[1])})")

    # ---- navegacion ----
    def refresh_entries(self):
        dirs, files = list_dir(self.cwd)
        self.entries = []
        if os.path.abspath(self.cwd) != os.path.abspath(self.root):
            self.entries.append(("..", "up", os.path.dirname(self.cwd)))
        for d in dirs:
            self.entries.append((d + "/", "dir", os.path.join(self.cwd, d)))
        for f in files:
            p = os.path.join(self.cwd, f)
            mark = "♥ " if p in self.favorites else ""
            self.entries.append((mark + f, "file", p))
        self.cursor = min(self.cursor, max(0, len(self.entries) - 1))
        self.search = ""

    def track_label(self, path):
        """Etiqueta 'Cancion — Artista · Album'. Para la pista que esta sonando
        usa los tags reales (ID3, ya sondeados por ffprobe); para el resto la
        deriva de las carpetas, que casi siempre son artista/disco."""
        mark = "♥ " if path in self.favorites else ""
        tags = self.player.tags if path == self.player.path else {}
        if tags.get("title"):
            ctx = " · ".join(t for t in (tags.get("artist"), tags.get("album")) if t)
            return mark + tags["title"] + (f"  —  {ctx}" if ctx else "")
        rel = os.path.relpath(path, self.root)
        parts = rel.split(os.sep)
        name = os.path.splitext(parts[-1])[0]
        if len(parts) > 1:
            return f"{mark}{name}  —  {' · '.join(parts[:-1])}"
        return mark + name

    def enter(self):
        if not self.entries:
            return
        if self.searching or self.listview:
            label, kind, path = self.entries[self.cursor]
            if kind == "list":
                if self.pending_add:                    # elegir lista destino ('A')
                    self.add_to_playlist(path, self.pending_add)
                    self.pending_add = None
                    self.exit_listview()
                else:                                   # abrir la lista ('V')
                    self.open_playlist(path)
                return
            if kind == "newlist":
                self.prompt = "Nombre de la nueva lista: "
                self.prompt_text = ""
                return
            if kind == "top":
                self.open_top()
                return
            if kind == "queued":
                # saltar la cola hasta la pista elegida (la cola sigue viva)
                for _ in range(self.cursor + 1):
                    self.queue.advance()
                self._play(self.queue.current())
                self.exit_listview()
                return
            # pista: reproduce y deja una cola secuencial con toda la lista visible
            tracks = [p for (_l, k, p) in self.entries if k == "file"]
            self.follow = False
            self.queue = NoRepeatQueue(tracks, shuffle=False, start_index=self.cursor)
            self.queue_label = (self.listview if self.listview
                                else "🔍 Resultados: " + (self.query or ""))
            self._play_current()
            return
        label, kind, path = self.entries[self.cursor]
        if kind in ("dir", "up"):
            self.cwd = path
            self.cursor = 0
            self.top = 0
            self.refresh_entries()
        elif kind == "file":
            self.play_folder_from(path)

    def go_up(self):
        if self.listview:
            self.exit_listview()
            return
        if os.path.abspath(self.cwd) != os.path.abspath(self.root):
            child = self.cwd
            self.cwd = os.path.dirname(self.cwd)
            self.refresh_entries()
            # dejar el cursor sobre la carpeta de la que salimos
            for i, (lbl, kind, p) in enumerate(self.entries):
                if p == child:
                    self.cursor = i
                    break

    # ---- reproduccion ----
    def play_folder_from(self, file_path):
        """Reproduce la carpeta actual en orden, empezando por file_path."""
        self.follow = False
        _, files = list_dir(self.cwd)
        tracks = [os.path.join(self.cwd, f) for f in files]
        try:
            start = tracks.index(file_path)
        except ValueError:
            start = 0
        self.queue = NoRepeatQueue(tracks, shuffle=False, start_index=start)
        self.queue_label = "Carpeta: " + os.path.basename(self.cwd or self.root)
        self._play_current()

    def shuffle_folder(self):
        self.follow = False
        if self.listview:
            # en una lista virtual, 's' baraja las pistas visibles
            tracks = [p for (_l, k, p) in self.entries if k in ("file", "queued")]
            if tracks:
                self.queue = NoRepeatQueue(tracks, shuffle=True)
                self.queue_label = f"🔀 {self.listview} · {len(tracks)} pistas"
                self._play_current()
            return
        tracks = collect_tracks(self.cwd)
        if not tracks:
            self.status = "No hay pistas en esta carpeta."
            return
        self.queue = NoRepeatQueue(tracks, shuffle=True)
        self.queue_label = f"🔀 Carpeta (recursivo): {os.path.basename(self.cwd or self.root)} · {len(tracks)} pistas"
        self._play_current()

    def shuffle_global(self):
        self.follow = False
        self.status = "Indexando biblioteca…"
        self._draw()
        tracks = collect_tracks(self.root)
        if not tracks:
            self.status = "No se encontraron pistas en la biblioteca."
            return
        self.queue = NoRepeatQueue(tracks, shuffle=True)
        self.queue_label = f"🔀 GLOBAL · {len(tracks)} pistas (sin repetir)"
        self._play_current()

    def _play(self, track, start=0.0):
        """Punto central de arranque: reproduce, anuncia y cuenta."""
        self.player.play(track, start=start)
        self.status = "▶ " + self.track_label(track)
        self.counts[track] = self.counts.get(track, 0) + 1
        save_json(CNT_FILE, self.counts)

    def _play_current(self):
        track = self.queue.current() if self.queue else None
        if track:
            self._play(track)

    def _pick_follow_next(self, exclude=None):
        """Una pista al azar de la carpeta actual (recursivo); evita 'exclude'."""
        tracks = collect_tracks(self.cwd)
        if not tracks:
            return None
        pool = [t for t in tracks if t != exclude] if (exclude and len(tracks) > 1) else tracks
        return random.choice(pool)

    def toggle_follow(self):
        """Activa/desactiva el modo 'sigue mi navegacion'."""
        self.follow = not self.follow
        if self.follow:
            self.follow_next = self._pick_follow_next(exclude=self.player.path)
            self.status = "🧭 Seguir navegación: ON · la siguiente saldrá de donde estés"
        else:
            self.status = "🧭 Seguir navegación: OFF"

    def upcoming_track(self):
        """La pista que sonara despues, segun el modo actual."""
        if self.follow:
            return self.follow_next
        if self.queue:
            return self.queue.peek_next()
        return None

    def reroll_next(self):
        """Cambia por otra la siguiente pista anunciada."""
        if self.follow:
            self.follow_next = self._pick_follow_next(exclude=self.player.path)
        elif self.queue:
            self.queue.reroll_next()
        nxt = self.upcoming_track()
        if nxt:
            self.status = "↻ Siguiente: " + self.track_label(nxt)

    def next_track(self):
        if self.follow:
            nxt = self.follow_next or self._pick_follow_next(exclude=self.player.path)
            if nxt:
                if self.player.path:
                    self.follow_history.append(self.player.path)
                self._play(nxt)
                self.follow_next = self._pick_follow_next(exclude=nxt)
        elif self.queue:
            self.queue.advance()
            self._play_current()

    def prev_track(self):
        if self.follow:
            if self.follow_history:
                prev = self.follow_history.pop()
                self.follow_next = self.player.path   # la actual pasa a ser la sugerida
                self._play(prev)
        elif self.queue:
            self.queue.back()
            self._play_current()

    # ---- favoritos (teclas 'a' y 'v') ----
    def toggle_favorite(self):
        """Marca/desmarca como favorita la pista bajo el cursor (o la que suena)."""
        path = None
        if self.entries and self.entries[self.cursor][1] == "file":
            path = self.entries[self.cursor][2]
        elif self.player.path:
            path = self.player.path
        if not path:
            self.status = "Nada que marcar como favorito."
            return
        if path in self.favorites:
            self.favorites.remove(path)
            self.status = "♡ Quitada de favoritos: " + os.path.basename(path)
        else:
            self.favorites.append(path)
            self.status = "♥ Añadida a favoritos: " + os.path.basename(path)
        save_favorites(self.favorites)
        self._rebuild_view()

    def _rebuild_view(self):
        """Redibuja la lista actual conservando el cursor (tras cambiar ♥)."""
        cur = self.cursor
        if self.searching:
            self.update_search()
        elif self.listview:
            # re-etiquetar en el lugar para refrescar los ♥ sin perder la vista
            self.entries = [(self.track_label(p) if k == "file" else l, k, p)
                            for (l, k, p) in self.entries]
        else:
            self.refresh_entries()
        self.cursor = min(cur, max(0, len(self.entries) - 1))

    def open_favorites(self, keep_cursor=False):
        """Abre la lista de favoritos como una carpeta virtual."""
        favs = [p for p in self.favorites if os.path.exists(p)]
        if not favs:
            self.status = "No hay favoritos todavía · marca con 'a'."
            if self.listview:
                self.exit_listview()
            return
        self.searching = False
        self.listview = "❤ Favoritos"
        self.entries = [(self.track_label(p), "file", p) for p in favs]
        if not keep_cursor:
            self.cursor = 0
            self.top = 0
            self.status = f"❤ {len(favs)} favoritos · Enter reproduce · s shuffle · ESC vuelve"

    def exit_listview(self):
        self.listview = None
        self.pending_add = None
        self.refresh_entries()

    # ---- listas propias, top y cola (teclas 'A', 'V', 'u') ----
    def open_playlist_chooser(self, adding=None):
        """Selector de listas: abrirlas ('V') o elegir destino al agregar ('A')."""
        self.pending_add = adding
        entries = []
        if adding:
            entries.append(("➕ Nueva lista…", "newlist", ""))
        for name, path in list_playlists():
            mark = "❤ " if path == FAV_FILE else "🎵 "
            entries.append((mark + name, "list", path))
        if not adding and self.counts:
            entries.append(("🏆 Más escuchadas", "top", ""))
        if not entries:
            self.status = "No hay listas todavía · 'a' marca favoritos, 'A' crea una lista."
            return
        self.searching = False
        self.listview = "➕ Agregar a…" if adding else "📂 Listas"
        self.entries = entries
        self.cursor = 0
        self.top = 0
        self.status = ("Elige la lista destino · Enter confirma · ESC cancela" if adding
                       else "Enter abre la lista · ESC vuelve")

    def open_playlist(self, m3u_path):
        """Abre un .m3u guardado como carpeta virtual."""
        if m3u_path == FAV_FILE:
            self.open_favorites()
            return
        tracks = [p for p in load_m3u(m3u_path) if os.path.exists(p)]
        name = os.path.splitext(os.path.basename(m3u_path))[0]
        if not tracks:
            self.status = f"La lista «{name}» está vacía."
            return
        self.searching = False
        self.listview = "🎵 " + name
        self.entries = [(self.track_label(p), "file", p) for p in tracks]
        self.cursor = 0
        self.top = 0
        self.status = f"🎵 {name} · {len(tracks)} pistas · Enter reproduce · s shuffle · ESC vuelve"

    def add_to_playlist(self, m3u_path, track):
        """Agrega la pista al .m3u indicado (sin duplicar)."""
        name = os.path.splitext(os.path.basename(m3u_path))[0]
        if m3u_path == FAV_FILE:
            if track not in self.favorites:
                self.favorites.append(track)
                save_favorites(self.favorites)
        else:
            tracks = load_m3u(m3u_path)
            if track not in tracks:
                tracks.append(track)
                save_m3u(m3u_path, tracks)
        self.status = f"♪ Añadida a «{name}»: " + os.path.basename(track)

    def add_current_to_list(self):
        """Tecla 'A': agrega la pista bajo el cursor (o la que suena) a una lista."""
        path = None
        if self.entries and self.entries[self.cursor][1] in ("file", "queued"):
            path = self.entries[self.cursor][2]
        elif self.player.path:
            path = self.player.path
        if not path:
            self.status = "Nada que agregar a una lista."
            return
        self.open_playlist_chooser(adding=path)

    def _prompt_done(self):
        """Confirma el prompt de texto (crear lista nueva y agregar la pista)."""
        name = self.prompt_text.strip().replace(os.sep, "-")
        self.prompt = None
        self.prompt_text = ""
        if not name or not self.pending_add:
            self.status = "Cancelado."
            self.exit_listview()
            return
        self.add_to_playlist(os.path.join(PLAYLIST_DIR, name + ".m3u"), self.pending_add)
        self.exit_listview()

    def open_top(self):
        """Vista de las pistas mas reproducidas (contador local)."""
        items = sorted(self.counts.items(), key=lambda kv: -kv[1])
        items = [(p, n) for p, n in items if os.path.exists(p)][:50]
        if not items:
            self.status = "Aún no hay reproducciones contadas."
            return
        self.searching = False
        self.listview = "🏆 Más escuchadas"
        self.entries = [(f"{n:3d}×  " + self.track_label(p), "file", p) for p, n in items]
        self.cursor = 0
        self.top = 0
        self.status = f"🏆 top {len(items)} · Enter reproduce · s shuffle · ESC vuelve"

    def open_queue(self):
        """Muestra lo que viene en la cola; Enter salta directo a esa pista."""
        if self.follow or not self.queue:
            self.status = "No hay cola activa (en modo seguir, la siguiente es al azar)."
            return
        self.queue.peek_next()          # asegura que el proximo ciclo este barajado
        nxt = [self.queue.base[i] for i in self.queue.upcoming[:100]]
        if not nxt:
            self.status = "La cola llegó al final."
            return
        self.searching = False
        self.listview = "⏭ Cola"
        self.entries = [(f"{i + 1:3d}. " + self.track_label(p), "queued", p)
                        for i, p in enumerate(nxt)]
        self.cursor = 0
        self.top = 0
        self.status = f"⏭ próximas {len(nxt)} pistas · Enter salta a esa pista · ESC vuelve"

    # ---- continuar sesion y temporizador (teclas 'c' y 't') ----
    def resume_last(self):
        """Continua la pista de la sesion anterior donde quedo, con su carpeta en cola."""
        if not self.resume:
            self.status = "No hay nada que continuar."
            return
        track, pos = self.resume
        self.resume = None
        folder = os.path.dirname(track)
        _, files = list_dir(folder)
        tracks = [os.path.join(folder, f) for f in files] or [track]
        start = tracks.index(track) if track in tracks else 0
        self.follow = False
        self.queue = NoRepeatQueue(tracks, shuffle=False, start_index=start)
        self.queue_label = "Carpeta: " + os.path.basename(folder)
        self._play(track, start=pos)

    def _save_state(self):
        """Guarda carpeta, volumen y pista actual para la proxima sesion."""
        st = {"cwd": self.cwd, "volume": self.player.volume}
        if self.player.path and self.player.proc and self.player.proc.poll() is None:
            st["track"] = self.player.path
            st["pos"] = round(self.player.elapsed(), 1)
        save_json(STATE_FILE, st)

    def toggle_sleep(self):
        """Cicla el temporizador de apagado: 15 → 30 → 60 → 90 → off."""
        steps = [15, 30, 60, 90]
        if self.sleep_choice in steps[:-1]:
            self.sleep_choice = steps[steps.index(self.sleep_choice) + 1]
        elif self.sleep_choice is None:
            self.sleep_choice = steps[0]
        else:
            self.sleep_choice = None
        if self.sleep_choice:
            self.sleep_until = time.monotonic() + self.sleep_choice * 60
            self.status = f"💤 La música se detendrá en {self.sleep_choice} min ('t' para cambiar)"
        else:
            self.sleep_until = None
            self.status = "💤 Temporizador apagado."

    # ---- buscador global (tecla '/') ----
    def start_search(self):
        """Abre el buscador recursivo sobre toda la biblioteca."""
        if self.all_tracks is None:
            self.status = "Indexando biblioteca…"
            self._draw()
            self.all_tracks = collect_tracks(self.root)
        self.listview = None
        self.searching = True
        self.query = ""
        self.cursor = 0
        self.top = 0
        self.update_search()

    def update_search(self):
        """Filtra el indice por todos los terminos escritos (AND, sin importar mayusculas)."""
        q = self.query.lower().split()
        self.entries = []
        if q:
            for t in self.all_tracks:
                rel = os.path.relpath(t, self.root)
                low = rel.lower()
                if all(term in low for term in q):
                    self.entries.append((self.track_label(t), "file", t))
                    if len(self.entries) >= 800:
                        break
        self.cursor = min(self.cursor, max(0, len(self.entries) - 1))
        self.top = 0

    def exit_search(self):
        self.searching = False
        self.query = ""
        self.refresh_entries()

    # ---- busqueda incremental ----
    def search_jump(self, ch):
        self.search += ch
        q = self.search.lower()
        for i, (label, kind, path) in enumerate(self.entries):
            if q in label.lower():
                self.cursor = i
                break

    # ---- dibujo ----
    def _c(self, pair, fallback=curses.A_NORMAL):
        """Atributo de color si la terminal lo soporta; si no, el de respaldo."""
        return curses.color_pair(pair) if self.has_colors else fallback

    def _equalizer(self, n=4):
        """Barritas tipo ecualizador en onda; la fase la marca self.anim."""
        out = []
        for i in range(n):
            v = (math.sin(self.anim * 0.4 + i * 1.2) + 1) / 2     # 0..1
            out.append(EQ_BLOCKS[int(v * (len(EQ_BLOCKS) - 1))])
        return "".join(out)

    def _marquee(self, text, width):
        """Desplaza el texto si no cabe (marquesina). Se mueve con self.anim."""
        if len(text) <= width:
            return text
        s = text + "   •   "
        off = (self.anim // 2) % len(s)
        return (s + s)[off:off + width]

    def _set_title(self, text):
        """Cambia el titulo de la ventana/pestaña de la terminal (OSC).
        Sirve para identificar QUE pestaña esta reproduciendo musica."""
        if not self._tty or text == self._title:
            return
        self._title = text
        try:
            sys.stdout.write("\033]0;" + text + "\007")
            sys.stdout.flush()
        except Exception:
            pass

    def _update_title(self):
        """Titulo de la pestaña: ♫ fijo mientras suena; un parpadeo breve con un
        punto una vez por minuto (⏸ en pausa)."""
        p = self.player
        if not p.path:
            self._set_title("🎵 Reproductor de música")
            return
        name = self.track_label(p.path)
        if p.paused:
            self._set_title(f"⏸ {name}")
            return
        # parpadeo discreto: el punto aparece ~1.5 s una vez por minuto
        mark = "·" if (time.monotonic() % 60) < 1.5 else "♫"
        self._set_title(f"{mark} {name}")

    def _put(self, y, x, text, attr=curses.A_NORMAL):
        """Escribe texto recortado al ancho seguro; nunca toca la ultima celda
        (evita el error ERR de curses en la esquina inferior derecha)."""
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        avail = w - x - 1  # dejar libre la ultima columna
        if avail <= 0:
            return
        try:
            self.scr.addnstr(y, x, text, avail, attr)
        except curses.error:
            pass

    def _draw_help(self):
        """Pantalla de ayuda a pantalla completa con todos los controles."""
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        self._put(0, 0, " 🎵 Ayuda — controles ".ljust(w), self._c(1, curses.A_REVERSE))
        kw = max(len(k) for k, _ in HELP_LINES)
        y = 2
        for key, desc in HELP_LINES:
            if y >= h - 1:
                break
            self._put(y, 2, key.rjust(kw), self._c(8, curses.A_BOLD) | curses.A_BOLD)
            self._put(y, 2 + kw + 2, desc, self._c(4))
            y += 1
        self._put(h - 1, 0, " pulsa cualquier tecla para volver ".ljust(w),
                  self._c(6, curses.A_REVERSE))
        scr.refresh()

    def _draw(self):
        if self.show_help:
            self._draw_help()
            return
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 8 or w < 30:
            self._put(0, 0, "Ventana muy pequeña")
            scr.refresh()
            return

        # cabecera
        if self.searching:
            header = f" 🔍 Buscar: {self.query}▏   ({len(self.entries)} resultados)"
        elif self.listview:
            header = f" {self.listview}   ({len(self.entries)} pistas)"
        else:
            rel = os.path.relpath(self.cwd, self.root)
            header = " 🎵 " + ("Música/" if rel == "." else "Música/" + rel)
            if self.follow:
                header += "   [🧭 sigue navegación]"
        self._put(0, 0, header.ljust(w), self._c(1, curses.A_REVERSE))

        list_h = h - 6  # filas para la lista
        # ventana de scroll
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + list_h:
            self.top = self.cursor - list_h + 1

        for row in range(list_h):
            idx = self.top + row
            y = 1 + row
            if idx >= len(self.entries):
                break
            label, kind, path = self.entries[idx]
            prefix = "▶ " if idx == self.cursor else "  "
            if idx == self.cursor:
                attr = self._c(3, curses.A_REVERSE) | curses.A_BOLD
            elif kind in ("dir", "up"):
                attr = self._c(2, curses.A_BOLD) | curses.A_BOLD
            else:
                attr = curses.A_NORMAL
            self._put(y, 0, (prefix + label).ljust(w), attr)

        # separador
        sep_y = 1 + list_h
        self._put(sep_y, 0, "─" * w, self._c(2))

        # panel de reproduccion
        p = self.player
        py = sep_y + 1
        if p.path:
            state = "⏸" if p.paused else self._equalizer()
            avail = max(10, w - len(state) - 2)
            name = self._marquee(self.track_label(p.path), avail)
            self._put(py, 0, state, self._c(7, curses.A_BOLD) | curses.A_BOLD)
            self._put(py, len(state) + 1, name, self._c(4, curses.A_BOLD) | curses.A_BOLD)

            elapsed = p.elapsed()
            dur = p.duration
            pct = (elapsed / dur) if dur > 0 else 0.0
            barw = max(10, w - 28)
            filled = min(int(barw * pct), barw)
            head = f"{fmt_time(elapsed)}/{fmt_time(dur)} ["
            self._put(py + 1, 0, head)
            x = len(head)
            self._put(py + 1, x, "█" * filled, self._c(5, curses.A_BOLD))
            self._put(py + 1, x + filled, "░" * (barw - filled), self._c(2, curses.A_DIM))
            vol_s = "MUT " if p.muted else f"{p.volume:3d}%"
            extra = ""
            if self.sleep_until:
                rem = max(1, math.ceil((self.sleep_until - time.monotonic()) / 60))
                extra = f"  💤{rem}m"
            self._put(py + 1, x + barw, f"] {int(pct * 100):3d}%  vol {vol_s}{extra}")
        else:
            self._put(py, 0, "(nada reproduciendo)")
            self._put(py + 1, 0, self.queue_label)

        # siguiente pista (se puede cambiar con 'r')
        nxt = self.upcoming_track()
        if nxt:
            self._put(py + 2, 0,
                      "⏭ Siguiente: " + self.track_label(nxt) + "   (r para cambiar)",
                      self._c(8, curses.A_DIM))

        # barra de estado
        sy = h - 1
        if self.prompt is not None:
            line = self.prompt + self.prompt_text + "▏  (Enter confirma · ESC cancela)"
        elif self.searching:
            line = "Escribe para filtrar · ↑↓ mover · Enter reproducir · ESC salir"
        elif self.search:
            line = f"buscar: {self.search}"
        else:
            line = self.status
        self._put(sy, 0, line.ljust(w), self._c(6, curses.A_REVERSE))
        scr.refresh()

    # ---- bucle principal ----
    def run(self):
        scr = self.scr
        scr.nodelay(True)
        scr.keypad(True)
        curses.curs_set(0)
        self.has_colors = curses.has_colors()
        if self.has_colors:
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)    # cabecera
            curses.init_pair(2, curses.COLOR_CYAN, bg)                    # carpetas / separador
            curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # cursor
            curses.init_pair(4, curses.COLOR_GREEN, bg)                   # pista sonando
            curses.init_pair(5, curses.COLOR_GREEN, bg)                   # barra llena
            curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)   # barra de estado
            curses.init_pair(7, curses.COLOR_MAGENTA, bg)                 # ecualizador
            curses.init_pair(8, curses.COLOR_YELLOW, bg)                  # siguiente pista
        while True:
            # auto-avance al terminar la pista
            if self.player.is_finished():
                self.next_track()

            # temporizador de apagado
            if self.sleep_until and time.monotonic() >= self.sleep_until:
                self.player.stop()
                self.player.path = None
                self.sleep_until = None
                self.sleep_choice = None
                self.status = "💤 Temporizador cumplido: música detenida."

            # la animacion solo avanza mientras suena (se congela en pausa)
            if self.player.proc and not self.player.paused:
                self.anim += 1

            self._update_title()
            self._draw()

            try:
                ch = scr.getch()
            except KeyboardInterrupt:
                break

            if ch == -1:
                # refresco mas vivo mientras suena (para la animacion)
                time.sleep(0.1 if (self.player.proc and not self.player.paused) else 0.2)
                continue

            # con la ayuda abierta, cualquier tecla la cierra
            if self.show_help:
                self.show_help = False
                continue

            # ---- prompt de texto (nombre de lista nueva) ----
            if self.prompt is not None:
                if ch in (curses.KEY_ENTER, 10, 13):
                    self._prompt_done()
                elif ch == 27:  # ESC
                    self.prompt = None
                    self.prompt_text = ""
                    self.status = "Cancelado."
                    self.exit_listview()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    self.prompt_text = self.prompt_text[:-1]
                elif 32 <= ch < 127:
                    self.prompt_text += chr(ch)
                continue

            # ---- modo buscador: el teclado escribe la consulta ----
            if self.searching:
                if ch in (curses.KEY_UP,):
                    self.cursor = max(0, self.cursor - 1)
                elif ch in (curses.KEY_DOWN,):
                    self.cursor = min(len(self.entries) - 1, self.cursor + 1)
                elif ch in (curses.KEY_NPAGE,):
                    self.cursor = min(len(self.entries) - 1, self.cursor + 10)
                elif ch in (curses.KEY_PPAGE,):
                    self.cursor = max(0, self.cursor - 10)
                elif ch in (curses.KEY_ENTER, 10, 13):
                    self.enter()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    self.query = self.query[:-1]
                    self.update_search()
                elif ch == 27:  # ESC
                    self.exit_search()
                elif 32 <= ch < 127:
                    self.query += chr(ch)
                    self.update_search()
                continue

            if ch in (curses.KEY_UP, ord("k")):
                self.cursor = max(0, self.cursor - 1)
                self.search = ""
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.cursor = min(len(self.entries) - 1, self.cursor + 1)
                self.search = ""
            elif ch in (curses.KEY_NPAGE,):
                self.cursor = min(len(self.entries) - 1, self.cursor + 10)
            elif ch in (curses.KEY_PPAGE,):
                self.cursor = max(0, self.cursor - 10)
            elif ch in (curses.KEY_HOME,):
                self.cursor = 0
            elif ch in (curses.KEY_END,):
                self.cursor = len(self.entries) - 1
            elif ch in (curses.KEY_ENTER, 10, 13):
                self.enter()
            elif ch in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8):
                if self.search:
                    self.search = self.search[:-1]
                else:
                    self.go_up()
            elif ch == ord("s"):
                self.shuffle_folder()
            elif ch == ord("g"):
                self.shuffle_global()
            elif ch == ord("f"):
                self.toggle_follow()
            elif ch == ord("a"):
                self.toggle_favorite()
            elif ch == ord("v"):
                self.open_favorites()
            elif ch == ord("V"):
                self.open_playlist_chooser()
            elif ch == ord("A"):
                self.add_current_to_list()
            elif ch == ord("u"):
                self.open_queue()
            elif ch == ord("c"):
                self.resume_last()
            elif ch == ord("t"):
                self.toggle_sleep()
            elif ch == ord("m"):
                self.player.toggle_mute()
            elif ch == ord(","):
                self.player.seek(-10)
            elif ch == ord("."):
                self.player.seek(+10)
            elif ch == ord("<"):
                self.player.seek(-60)
            elif ch == ord(">"):
                self.player.seek(+60)
            elif ch == ord("r"):
                self.reroll_next()
            elif ch == ord("/"):
                self.start_search()
            elif ch == ord(" "):
                self.player.toggle_pause()
            elif ch == ord("n"):
                self.next_track()
            elif ch == ord("b"):
                self.prev_track()
            elif ch in (ord("+"), ord("=")):
                self.player.change_volume(+5)
            elif ch in (ord("-"), ord("_")):
                self.player.change_volume(-5)
            elif ch in (ord("?"), ord("h")):
                self.show_help = True
            elif ch == 27:  # ESC
                if self.listview:
                    self.exit_listview()
                else:
                    self.search = ""
            elif ch == ord("q"):
                break
            elif 32 < ch < 127:
                self.search_jump(chr(ch))

        self._save_state()    # recordar carpeta/volumen/pista para la proxima sesion
        self.player.stop()
        self._set_title("")   # restaurar/limpiar el titulo de la pestaña al salir


def main():
    root = find_music_root()
    if not os.path.isdir(root):
        print("No se encontro carpeta de musica.")
        sys.exit(1)
    try:
        curses.wrapper(lambda scr: App(scr, root).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
