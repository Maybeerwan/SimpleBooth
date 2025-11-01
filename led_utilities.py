import os
import sys
import logging

# Si tu veux forcer le mock dans l'env de dev : export LED_FORCE_MOCK=1
try:
    if os.environ.get('LED_FORCE_MOCK') == '1':
        raise ImportError("Forcer mock LED")
    from rpi_ws281x import PixelStrip, Color
    LED_MOCK = False
except Exception:
    LED_MOCK = True
    # Color: même format integer 0xRRGGBB que rpi_ws281x.Color
    def Color(r: int, g: int, b: int) -> int:
        return ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)

    class PixelStrip:
        """Mock minimal de PixelStrip pour dev sur un PC.
        - stocke l'état des pixels en mémoire
        - show() affiche une ligne colorée dans le terminal (ANSI) si possible
        """
        def __init__(self, led_count, pin=None, freq_hz=None, dma=None, invert=False, brightness=255, channel=0):
            self._n = int(led_count)
            self._pixels = [0] * self._n
            self._brightness = brightness

        def begin(self):
            pass

        def numPixels(self):
            return self._n

        def setPixelColor(self, i: int, color):
            self._pixels[int(i)] = int(color)

        def getPixelColor(self, i: int) -> int:
            return int(self._pixels[int(i)])

        def show(self):
            # tentative d'affichage coloré si le terminal supporte ANSI 24-bit
            out = []
            for v in self._pixels:
                r = (v >> 16) & 0xFF
                g = (v >> 8) & 0xFF
                b = v & 0xFF
                # bloc couleur compact
                out.append(f"\x1b[48;2;{r};{g};{b}m \x1b[0m")
            print("".join(out))

import time
import threading
import random
import math
from config_utils import SETTINGS
from typing import Optional


# couleurs différentes sur chaque LED
ROUGE=0 # rouge
VERT=1  # vert
BLEU=2 # bleu
JAUNE=3  # jaune
CYAN=4  # cyan
MAGENTA=5  # magenta
ORANGE=6  # orange
VIOLET=7  # violet
BLANC=8 # blanc


colors = [
    Color(255, 0, 0),    # rouge
    Color(0, 255, 0),    # vert
    Color(0, 0, 255),    # bleu
    Color(255, 255, 0),  # jaune
    Color(0, 255, 255),  # cyan
    Color(255, 0, 255),  # magenta
    Color(255, 128, 0),  # orange
    Color(128, 0, 255),  # violet
    Color(255, 255, 255) # blanc
]

colors_rainbow = [
  { "name": "rouge",   "rgb": [255, 0, 0],     "color_call": "Color(255, 0, 0)" },
  { "name": "orange",  "rgb": [255, 165, 0],   "color_call": "Color(255, 165, 0)" },
  { "name": "jaune",   "rgb": [255, 255, 0],   "color_call": "Color(255, 255, 0)" },
  { "name": "vert",    "rgb": [0, 255, 0],     "color_call": "Color(0, 255, 0)" },
  { "name": "bleu",    "rgb": [0, 0, 255],     "color_call": "Color(0, 0, 255)" },
  { "name": "indigo",  "rgb": [75, 0, 130],    "color_call": "Color(75, 0, 130)" },
  { "name": "violet",  "rgb": [148, 0, 211],   "color_call": "Color(148, 0, 211)" }
]

def rotate_colors_right(lst, k=1):
    k = k % len(lst)
    return lst[-k:] + lst[:-k]

# === GESTION DU SINGLETON DE RUBAN LED ===

_strip_singleton: Optional[PixelStrip] = None
_strip_lock = threading.Lock()
_strip_created_here = False

def get_strip() -> PixelStrip:
    """
    Retourne l'instance singleton de PixelStrip (lazy init, thread-safe).
    Utiliser release_strip() pour libérer / éteindre le ruban.
    """
    global _strip_singleton, _strip_created_here
    with _strip_lock:
        if _strip_singleton is None:
            LED_COUNT = SETTINGS.get('led_count', 9)         # Nombre total de LEDs dans ton ruban
            LED_PIN = SETTINGS.get('led_pin', 18)           # GPIO connecté à DIN du ruban (ici GPIO18, pin physique 12)
            LED_FREQ_HZ = SETTINGS.get('led_freq_hz', 800000)   # Fréquence de signal (800kHz pour WS2812)
            LED_DMA = SETTINGS.get('led_dma', 10)           # Canal DMA utilisé pour envoyer les données
            LED_BRIGHTNESS = SETTINGS.get('led_brightness', 255)   # Luminosité (0 à 255)
            LED_INVERT = SETTINGS.get('led_invert', False)     # Inverser le signal (False pour la plupart des montages)
            LED_CHANNEL = SETTINGS.get('LED_CHANNEL', 0)        # Canal PWM (0 si GPIO18, 1 si GPIO13/19)

            _strip_singleton = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA,
                                         LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
            try:
                _strip_singleton.begin()
            except Exception:
                # ignore pour mock / environnements sans accès hardware
                pass
            _strip_created_here = True
        return _strip_singleton

def release_strip():
    """
    Éteint et libère le singleton (safe). Appeler au shutdown ou si on veut
    s'assurer que le hardware est propre avant de quitter.
    """
    global _strip_singleton, _strip_created_here
    stop_led_animation_mode()
    with _strip_lock:
        if _strip_singleton is None:
            return
        try:
            for i in range(_strip_singleton.numPixels()):
                _strip_singleton.setPixelColor(i, Color(0, 0, 0))
            _strip_singleton.show()
        except Exception:
            pass
        _strip_singleton = None
        _strip_created_here = False



def _ensure_strip(use_strip):
    strip = use_strip
    created = False
    if strip is None:
        strip = get_strip()
        try:
            strip.begin()
        except Exception:
            pass
        created = True
    return strip, created


# === Nouveaux effets d'animation ===

def wheel(pos: int) -> Color:
    """Generate rainbow Color from 0-255."""
    pos = pos % 256
    if pos < 85:
        return Color(pos * 3, 255 - pos * 3, 0)
    if pos < 170:
        pos -= 85
        return Color(255 - pos * 3, 0, pos * 3)
    pos -= 170
    return Color(0, pos * 3, 255 - pos * 3)

def animation_color_wipe(strip, delay, iterations, stop_event):
    """Color wipe: each LED takes next color of provided palette (cyclic)."""
    palette = colors.copy()
    step = 0
    while not stop_event.is_set() and (iterations is None or step < iterations):
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, palette[i % len(palette)])
        strip.show()
        if stop_event.wait(delay):
            break
        palette = rotate_colors_right(palette, 1)
        step += 1

def animation_chase(strip, delay, iterations, stop_event):
    """Chase: une LED allumée se déplace le long du ruban, couleur cyclique."""
    palette = colors.copy()
    length = strip.numPixels()
    step = 0
    offset = 0
    while not stop_event.is_set() and (iterations is None or step < iterations):
        for i in range(length):
            color = palette[(i + offset) % len(palette)]
            strip.setPixelColor(i, color if (i % 3) == (offset % 3) else Color(0,0,0))
        strip.show()
        if stop_event.wait(delay):
            break
        offset = (offset + 1) % len(palette)
        step += 1

def animation_theater_chase(strip, delay, iterations, stop_event):
    """Theater chase: groupe de LEDs allumé puis décalé (cinéma)."""
    palette = colors.copy()
    q = 0
    step = 0
    length = strip.numPixels()
    while not stop_event.is_set() and (iterations is None or step < iterations):
        for i in range(length):
            strip.setPixelColor(i, palette[(i + q) % len(palette)] if (i % 3) == 0 else Color(0,0,0))
        strip.show()
        if stop_event.wait(delay):
            break
        q = (q + 1) % 3
        step += 1

def animation_rainbow_cycle(strip, delay, iterations, stop_event):
    """Rainbow cycle sur tout le ruban (utilise wheel)."""
    length = strip.numPixels()
    j = 0
    step = 0
    while not stop_event.is_set() and (iterations is None or step < iterations):
        for i in range(length):
            strip.setPixelColor(i, wheel((int((i * 256 / length) + j)) & 255))
        strip.show()
        if stop_event.wait(delay):
            break
        j = (j + 1) % 256
        step += 1

def animation_scanner(strip, delay, iterations, stop_event):
    """Scanner / Larson: une LED brillante va et vient (effet 'Cylon')."""
    color = colors[0] if colors else Color(255, 0, 0)
    length = strip.numPixels()
    pos = 0
    direction = 1
    step = 0
    while not stop_event.is_set() and (iterations is None or step < iterations):
        for i in range(length):
            # gradient trail
            dist = abs(i - pos)
            if dist == 0:
                strip.setPixelColor(i, color)
            elif dist == 1:
                strip.setPixelColor(i, Color(int((color >> 16) * 0.4), int(((color >> 8) & 0xFF) * 0.4), int((color & 0xFF) * 0.4)))
            else:
                strip.setPixelColor(i, Color(0,0,0))
        strip.show()
        if stop_event.wait(delay):
            break
        pos += direction
        if pos >= length - 1 or pos <= 0:
            direction *= -1
        step += 1

def animation_pulse(strip, delay, iterations, stop_event):
    """Pulse (respiration) : intensité de la palette varie."""
    palette = colors.copy()
    length = strip.numPixels()
    step = 0
    # compute brightness multiplier from 0.2 to 1.0
    while not stop_event.is_set() and (iterations is None or step < iterations):
        for t in range(0, 100):
            if stop_event.is_set():
                break
            factor = 0.2 + 0.8 * (0.5 * (1 + math.sin(2 * math.pi * t / 100)))
            for i in range(length):
                c = palette[i % len(palette)]
                r = int(((c >> 16) & 0xFF) * factor)
                g = int(((c >> 8) & 0xFF) * factor)
                b = int((c & 0xFF) * factor)
                strip.setPixelColor(i, Color(r, g, b))
            strip.show()
            if stop_event.wait(delay):
                break
        step += 1

def animation_twinkle(strip, delay, iterations, stop_event):
    """Twinkle aléatoire : LEDs clignotent avec couleurs aléatoires."""
    length = strip.numPixels()
    step = 0
    while not stop_event.is_set() and (iterations is None or step < iterations):
        # random subset
        for _ in range(max(1, length // 3)):
            i = random.randrange(0, length)
            c = random.choice(colors)
            strip.setPixelColor(i, c)
        strip.show()
        if stop_event.wait(delay):
            break
        # fade out a little
        for i in range(length):
            # small fade towards off
            c = strip.getPixelColor(i)
            r = max(0, ((c >> 16) & 0xFF) - 20)
            g = max(0, ((c >> 8) & 0xFF) - 20)
            b = max(0, (c & 0xFF) - 20)
            strip.setPixelColor(i, Color(r, g, b))
        strip.show()
        if stop_event.wait(delay):
            break
        step += 1

def animation_all_white(strip, delay, iterations, stop_event):
    """Met toutes les LEDs en blanc. Reste ainsi en boucle si iterations=None."""
    length = strip.numPixels()
    step = 0
    white = Color(255, 255, 255)
    try:
        while not stop_event.is_set() and (iterations is None or step < iterations):
            for i in range(length):
                strip.setPixelColor(i, white)
            strip.show()
            # attend de façon interruptible
            if stop_event.wait(delay):
                break
            step += 1
    finally:
        # si on a été arrêté et qu'on doit éteindre, ne rien faire (caller gère l'état)
        pass

# mapping name -> function
_ANIMATIONS = {
    "color_wipe": animation_color_wipe,
    "chase": animation_chase,
    "theater_chase": animation_theater_chase,
    "rainbow_cycle": animation_rainbow_cycle,
    "scanner": animation_scanner,
    "pulse": animation_pulse,
    "twinkle": animation_twinkle,
    "all_white": animation_all_white,  # ajouté : toutes les LEDs en blanc
}
# Mode controller (indépendant du LEDAnimator précédent)
_led_mode_thread = None
_led_mode_stop = None

def start_led_animation_mode(name: str = "color_wipe", delay: float = 0.5, iterations: int | None = None, use_strip: PixelStrip | None = None):
    """Start a named animation in background (interruptible)."""
    global _led_mode_thread, _led_mode_stop
    stop_led_animation_mode()
    func = _ANIMATIONS.get(name)
    if func is None:
        raise ValueError(f"Animation inconnue: {name}")
    strip, created = _ensure_strip(use_strip)
    _led_mode_stop = threading.Event()

    def _runner():
        try:
            func(strip, delay, iterations, _led_mode_stop)
        finally:
            if created:
                for i in range(strip.numPixels()):
                    strip.setPixelColor(i, Color(0,0,0))
                try:
                    strip.show()
                except Exception:
                    pass

    _led_mode_thread = threading.Thread(target=_runner, daemon=True)
    _led_mode_thread.start()

def stop_led_animation_mode(wait: bool = True):
    """Stop the named animation started with start_led_animation_mode."""
    global _led_mode_thread, _led_mode_stop
    if _led_mode_stop is not None:
        _led_mode_stop.set()
    if _led_mode_thread is not None and wait:
        _led_mode_thread.join(timeout=1.0)
    _led_mode_thread = None
    _led_mode_stop = None

# Usage examples (en Python):
# start_led_animation_mode("rainbow_cycle", delay=0.02)
# stop_led_animation_mode()