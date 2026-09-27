# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A terminal music player (TUI) written in a single file, `player.py`. It is deliberately
dependency-free: only the Python standard library (`curses`) plus external binaries from
`ffmpeg` (`ffplay` for playback, `ffprobe` for duration). Optional `pactl` (PulseAudio) is
used for live volume control. There is no package, no build, no test suite, and no git repo.

Note: code comments, docstrings, README, and user-facing strings are in Spanish. Match that
language when editing them.

## Running

```bash
./reproductor              # uses ~/Música (or Music/musica/Musica)
./reproductor /other/path  # uses another folder
python3 player.py [path]   # equivalent; the `reproductor` script just cd's + execs this
```

Music-root resolution lives in `find_music_root()`: CLI arg first, then `~/Música`,
`~/Music`, `~/musica`, `~/Musica`, then a `musica/` folder next to the script, then `$HOME`.

There is no automated way to test the TUI — it requires an interactive terminal and an audio
device. Verify changes by running it manually.

## Architecture

Everything is in `player.py`, organized as three classes plus module-level helpers:

- **`NoRepeatQueue`** — playback ordering, modeled as `history` (played; `history[-1]` is the
  current track) + `upcoming` (what's next). The shuffle guarantee is "100% random without
  repeats until the list is exhausted": a cycle is shuffled, played start to finish, then
  `_refill()` reshuffles — swapping the first element if it would repeat the track that just
  played across the cycle boundary. `peek_next()` shows the upcoming track without advancing
  and `reroll_next()` swaps it for another (shuffle only); both back the UI's "next track"
  display and the `r` key. Also handles sequential order, where it clamps at the end.

- **`AudioPlayer`** — wraps one `ffplay` subprocess per track. Pause/resume is done with
  `SIGSTOP`/`SIGCONT` signals (not by killing the process). Elapsed time is tracked manually
  via `time.monotonic()` with paused-duration accounting, because `ffplay` exposes no position.
  Volume is set live by parsing `pactl list sink-inputs` to find this process's sink-input
  index — best-effort, silently no-ops if `pactl` is absent.

- **`App`** — `curses` UI + main loop + navigation/playback orchestration. Holds the current
  directory (`cwd`), the entry list, the `AudioPlayer`, and the active `NoRepeatQueue`.

The main loop (`App.run`) is a non-blocking poll (`nodelay`, ~0.15s idle sleep). Each iteration
it checks `player.is_finished()` to auto-advance the queue, redraws, then reads one key.

### Things to watch when editing

- All screen writes go through `App._put()`, which clips to width and never touches the last
  cell of a row — this avoids the classic curses `ERR` on the bottom-right corner. Use it
  rather than calling `addstr` directly.
- `is_finished()` deliberately returns False while paused (a paused process also has
  `poll() is None`), so auto-advance doesn't fire on pause.
- The three "play" entry points build a queue and call `_play_current()`:
  `play_folder_from()` (sequential, current folder only), `shuffle_folder()` (recursive
  from `cwd`, key `s`), `shuffle_global()` (recursive from root, key `g`). All three set
  `self.follow = False`, since starting an explicit queue opts out of follow mode.
- **Follow mode** (`self.follow`, key `f`): when on, auto-advance ignores the queue and
  `next_track()`/`prev_track()` pick a random track from the *current* `cwd` (recursive,
  via `_pick_follow_next()`), keeping `follow_history` for `b`. The upcoming pick is
  precomputed in `follow_next` (recomputed on each advance) so the displayed "next track"
  stays honest. `upcoming_track()` is the single accessor the UI uses across both modes.
- Colors are set up in `run()` (guarded by `curses.has_colors()`); `_c(pair, fallback)`
  returns a color attr or the fallback so the UI degrades on color-less terminals.
- Animation is driven by `self.anim`, incremented once per main-loop iteration *only while
  playing and not paused* (so it freezes on pause). `_equalizer()` (sine-wave bars) and
  `_marquee()` (scrolling long titles) both read it. The idle `sleep` is shortened to 0.1s
  while playing for smoother frames.
- The terminal **tab/window title** is set via an OSC escape (`\033]0;…\007`) in
  `_update_title()`/`_set_title()` — a steady `♫` while playing, with a `·` that blinks
  briefly once a minute (timed off `time.monotonic()`, not `self.anim`), `⏸` when paused —
  so you can spot which tab is playing. Writes go straight to `sys.stdout` (guarded by
  `isatty()` and a no-op if unchanged); this is safe under curses because OSC title
  sequences are zero-width and don't move the cursor. The title is cleared on quit.
- **Global search** (`self.searching`, key `/`): `start_search()` lazily builds
  `self.all_tracks` (one `collect_tracks(root)`), then `update_search()` filters it into
  `self.entries` by AND-ing space-separated query terms against each track's path (case-
  insensitive, capped at 800 hits). While `searching`, the main loop routes the keyboard
  into `self.query` instead of the normal bindings; `enter()` plays the selected result and
  builds a sequential queue of all current results; `ESC`/`exit_search()` restores the
  folder view. `_draw()` branches its header and status line on `self.searching`. This is
  distinct from the in-folder incremental `search_jump()`/`self.search` (typing to jump).
- **Persistent data** lives in `~/.local/share/reproductor/` (module-level `PLAYLIST_DIR`):
  every playlist is a plain `.m3u` of absolute paths (`load_m3u`/`save_m3u`; favorites is just
  `favoritos.m3u` = `FAV_FILE`, kept mirrored in `App.favorites`), plus `conteo.json` (play
  counts per track, incremented in `App._play`) and `estado.json` (cwd/volume/track/position,
  written by `_save_state()` on quit and offered back via the `c` key → `resume_last()`).
- **Virtual list views** are driven by `self.listview` (view title, or `None`). Entries carry a
  kind that `enter()` dispatches on: `file` (build sequential queue of visible tracks), `list`
  (open that `.m3u`, or add `pending_add` to it when set), `newlist` (opens the text prompt),
  `top` (most-played view), `queued` (jump the live queue forward to that track). Keys: `v`
  favorites, `V` playlist chooser, `A` add-to-list chooser (`pending_add` holds the track),
  `u` queue view. ESC/`←`/Backspace exits via `exit_listview()` (which clears `pending_add`);
  `start_search()` clears `listview` so search and list views never overlap. `s` inside a list
  view shuffles the visible tracks.
- **Text prompt mode** (`self.prompt`/`self.prompt_text`, used for naming a new playlist): when
  `prompt is not None` the main loop routes keys into `prompt_text` (Enter → `_prompt_done()`,
  ESC cancels) and `_draw()` shows it in the status bar.
- **`App._play()` is the single playback entry point** (wraps `player.play`): sets the ▶ status
  and bumps the play count. Call it instead of `player.play()` directly.
- **Seek** (`,`/`.` = ±10s, `<`/`>` = ±60s): `ffplay` can't seek a live process, so
  `AudioPlayer.seek()` computes the target from `elapsed()` and relaunches via
  `play(path, start=pos)`, which passes `-ss` and back-dates `_start`. `play()` skips the
  `ffprobe` re-probe when the path is unchanged (so seeks are cheap) — that probe also returns
  real ID3 tags (`probe()`), stored in `AudioPlayer.tags`.
- `App.track_label()` renders `Canción — Artista · Álbum`: for the currently playing track it
  prefers the real ID3 tags; otherwise it derives the label from the path relative to the root
  (the library layout is almost always artist/album folders). Used everywhere a track is
  announced: search results, list views, playing panel, next-track line, status, tab title.
- **Sleep timer** (`t` cycles 15/30/60/90/off): `sleep_until` is a `time.monotonic()` deadline
  checked in the main loop; on expiry the player is stopped and `player.path` cleared.
  **Mute** (`m`): `AudioPlayer.muted` — `_apply_volume()` sends 0% while keeping `volume`;
  changing volume unmutes.
- Supported audio extensions are in the module-level `AUDIO_EXTS` set.
