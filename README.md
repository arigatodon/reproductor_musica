# 🎵 Reproductor de música (terminal)

Un reproductor de música para la terminal, escrito en **un solo archivo** de Python
y **sin dependencias que instalar**. Usa la librería estándar (`curses`) más los
binarios de `ffmpeg` (`ffplay` para reproducir, `ffprobe` para leer duración y etiquetas),
que casi siempre ya están en el sistema.

Está pensado para quien tiene su música ordenada en carpetas (`Artista/Álbum/…`) y
quiere escucharla sin abrir una aplicación pesada: se lanza al instante, funciona
100% offline y se maneja entero con el teclado.

```
┌─ Reproductor ─────────────────────────────┐
│  Pink Floyd/                               │
│  Radiohead/                                │
│ ▶ The Beatles/                             │
│    Abbey Road/                             │
│    Revolver/                               │
├────────────────────────────────────────────┤
│ ▶ Here Comes the Sun — The Beatles · Abbey │
│   ▁▃▅▇▅▃▁  01:42 / 03:05  ████████░░░░ 55% │
│ Siguiente: Because — The Beatles           │
└────────────────────────────────────────────┘
```

## Instalación y uso

No hay nada que compilar ni instalar. Solo clona el repositorio y ejecútalo:

```bash
git clone <url-del-repo>
cd reproductor_musica
./reproductor              # usa ~/Música (o ~/Music, ~/musica, ~/Musica)
./reproductor /otra/ruta   # usa otra carpeta como biblioteca
```

Equivale a `python3 player.py [ruta]`; el script `reproductor` solo se coloca en la
carpeta correcta y llama a Python. Puedes crear un enlace en tu `PATH` (por ejemplo
`ln -s .../reproductor ~/.local/bin/music`) para lanzarlo desde cualquier sitio.

### Requisitos

- **Python 3** con `curses` (viene de serie en Linux y macOS).
- **`ffplay` y `ffprobe`** (paquete `ffmpeg`): `sudo apt install ffmpeg` en Debian/Ubuntu.
- Opcional: **`pactl`** (PulseAudio/PipeWire) para ajustar el volumen en vivo, y
  `notify-send` para las notificaciones de escritorio.

## Qué sabe hacer

- **Navegar** tu biblioteca por carpetas y reproducir pistas o álbumes enteros.
- **Shuffle sin repeticiones** de una carpeta o de toda la biblioteca (ver más abajo).
- **Buscar** en toda la colección por varias palabras a la vez.
- **Favoritos y playlists** propias, guardadas como archivos `.m3u` estándar.
- **Cola de reproducción** visible y editable, con anuncio de la siguiente pista.
- **Controles de reproducción**: pausa, siguiente/anterior, volumen, silencio,
  avance/retroceso (seek) y **temporizador de apagado**.
- **Reanudar la última sesión** justo donde la dejaste (carpeta, pista, minuto y volumen).
- **Más escuchadas**: lleva la cuenta de reproducciones de cada pista.
- **Detalles bonitos**: ecualizador animado, barra de progreso, marquesina para títulos
  largos, colores por tipo, notificación de escritorio al cambiar de pista y el título de
  la pestaña de la terminal indicando qué está sonando.

Todo esto sin salir del teclado y sin ventanas emergentes.

## Controles

| Tecla             | Acción                                                        |
|-------------------|---------------------------------------------------------------|
| ↑ / ↓  (o k / j)  | mover el cursor                                               |
| Enter             | entrar a la carpeta / reproducir la pista                     |
| ← / Backspace     | subir un nivel (o salir de una vista/búsqueda)                |
| RePág / AvPág     | saltar de página                                              |
| Inicio / Fin      | ir al principio / al final de la lista                        |
| Espacio           | pausa / reanudar                                              |
| **n** / **b**     | siguiente / anterior                                          |
| **+** / **-**     | subir / bajar volumen                                         |
| **m**             | silenciar / quitar silencio                                   |
| **,** / **.**     | retroceder / avanzar 10 s                                     |
| **<** / **>**     | retroceder / avanzar 60 s                                     |
| **s**             | shuffle de la carpeta actual (recursivo)                      |
| **g**             | shuffle **global** de toda la biblioteca                      |
| **f**             | seguir navegación (la siguiente sale de donde estés)          |
| **r**             | cambiar la siguiente pista anunciada                          |
| **/**             | buscar en toda la biblioteca (Enter reproduce, ESC sale)      |
| escribir letras   | salto incremental a la entrada que coincide                   |
| **a**             | marcar / desmarcar la pista como favorita                     |
| **v**             | ver favoritos                                                 |
| **V**             | abrir / elegir una playlist                                   |
| **A**             | añadir la pista actual a una lista                            |
| **u**             | ver la cola de reproducción                                   |
| **c**             | reanudar la última sesión                                     |
| **t**             | temporizador de apagado (15 / 30 / 60 / 90 min / off)         |
| **?** o **h**     | mostrar ayuda en la barra de estado                           |
| ESC               | salir de la vista actual / limpiar la búsqueda                |
| **q**             | salir                                                         |

## Cómo funciona la aleatoriedad

El shuffle es **100% aleatorio sin repeticiones**: se baraja toda la lista y se
reproduce de principio a fin antes de que vuelva a sonar cualquier pista. Al completar
un ciclo se vuelve a barajar y, además, se evita que la primera pista del nuevo ciclo
coincida con la última que sonó (sin repetición en el empalme).

- **`s`** baraja **solo la carpeta donde estás** (incluyendo subcarpetas).
- **`g`** baraja **toda la biblioteca**.
- **`f`** activa **seguir navegación**: al terminar cada pista, la siguiente se elige
  al azar de la carpeta donde estés *en ese momento*. Si te mueves a otra carpeta, el
  azar te sigue. (Elegir `s`/`g` o reproducir una pista concreta lo desactiva.)

En el panel inferior siempre se anuncia la **siguiente pista**; con **`r`** la cambias
por otra sin esperar a que termine la actual.

## Buscador (`/`)

Pulsa `/` y escribe: filtra **toda la biblioteca** por nombre, buscando por varias
palabras a la vez y sin importar mayúsculas (p. ej. `beatles yesterday`). Con ↑/↓ te
mueves por los resultados, `Enter` reproduce el seleccionado (y deja en cola el resto)
y `ESC` cierra el buscador.

## Favoritos y playlists

- **`a`** marca o desmarca la pista actual como favorita; **`v`** abre la lista de favoritos.
- **`V`** abre el selector de playlists (y permite crear una nueva).
- **`A`** añade la pista seleccionada a una lista existente.
- **`u`** muestra la cola de reproducción actual.

Las listas son archivos **`.m3u` de rutas absolutas**, así que puedes editarlas a mano
o usarlas con otros reproductores.

## Dónde se guardan los datos

En `~/.local/share/reproductor/`:

- `favoritos.m3u` y el resto de tus playlists (`.m3u`).
- `conteo.json` — número de reproducciones por pista (para las "más escuchadas").
- `estado.json` — carpeta, volumen, pista y posición al salir, para poder **reanudar**
  con la tecla `c`.

Estos archivos son personales y **no** forman parte del repositorio (están en `.gitignore`).

## Formatos soportados

Cualquier extensión de audio que `ffplay` sepa reproducir. Las reconocidas por defecto
están en el conjunto `AUDIO_EXTS` dentro de `player.py` (mp3, flac, ogg, m4a, wav, opus…).

## Estructura del proyecto

- **`player.py`** — todo el reproductor (un único archivo). Contiene la cola de
  reproducción sin repeticiones, el envoltorio de `ffplay` y la interfaz `curses`.
- **`reproductor`** — pequeño lanzador en bash.
- **`CLAUDE.md`** — notas de arquitectura (útiles si quieres entender o modificar el código).

## Licencia

Publicado bajo la licencia **MIT** (ver [`LICENSE`](LICENSE)): puedes usar, copiar,
modificar y compartir el código libremente, conservando el aviso de copyright.
