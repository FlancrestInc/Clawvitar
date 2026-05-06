#!/usr/bin/env python3

import ctypes
from dataclasses import dataclass
import fcntl
import json
import os
import time

from PIL import Image

from pi_avatar.config import load_config
from pi_avatar.constants import (
    DEFAULT_STATE,
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    STATE_CHECK_SECONDS,
    STATE_FPS,
    VALID_STATES,
)


FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602


class FbBitField(ctypes.Structure):
    _fields_ = [
        ("offset", ctypes.c_uint32),
        ("length", ctypes.c_uint32),
        ("msb_right", ctypes.c_uint32),
    ]


class FbVarScreenInfo(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_uint32),
        ("yres", ctypes.c_uint32),
        ("xres_virtual", ctypes.c_uint32),
        ("yres_virtual", ctypes.c_uint32),
        ("xoffset", ctypes.c_uint32),
        ("yoffset", ctypes.c_uint32),
        ("bits_per_pixel", ctypes.c_uint32),
        ("grayscale", ctypes.c_uint32),
        ("red", FbBitField),
        ("green", FbBitField),
        ("blue", FbBitField),
        ("transp", FbBitField),
        ("nonstd", ctypes.c_uint32),
        ("activate", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("accel_flags", ctypes.c_uint32),
        ("pixclock", ctypes.c_uint32),
        ("left_margin", ctypes.c_uint32),
        ("right_margin", ctypes.c_uint32),
        ("upper_margin", ctypes.c_uint32),
        ("lower_margin", ctypes.c_uint32),
        ("hsync_len", ctypes.c_uint32),
        ("vsync_len", ctypes.c_uint32),
        ("sync", ctypes.c_uint32),
        ("vmode", ctypes.c_uint32),
        ("rotate", ctypes.c_uint32),
        ("colorspace", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 4),
    ]


class FbFixScreenInfo(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char * 16),
        ("smem_start", ctypes.c_ulong),
        ("smem_len", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("type_aux", ctypes.c_uint32),
        ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16),
        ("ypanstep", ctypes.c_uint16),
        ("ywrapstep", ctypes.c_uint16),
        ("line_length", ctypes.c_uint32),
        ("mmio_start", ctypes.c_ulong),
        ("mmio_len", ctypes.c_uint32),
        ("accel", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16 * 2),
    ]


@dataclass(frozen=True)
class BitField:
    offset: int
    length: int


@dataclass(frozen=True)
class FramebufferInfo:
    width: int
    height: int
    bits_per_pixel: int
    line_length: int
    red: BitField
    green: BitField
    blue: BitField
    transp: BitField


def read_state(config=None):
    config = config or load_config(os.environ)
    try:
        data = json.loads(config.state_file.read_text())
        state = data.get("state", DEFAULT_STATE)
        detail = data.get("detail", "")

        if state not in VALID_STATES:
            return DEFAULT_STATE, "Unknown state"

        return state, detail
    except Exception:
        return "offline", "State file unavailable"


def load_frames_for_state(state, config, pygame_module):
    folder = config.asset_dir / state
    frames = []

    if not folder.exists():
        return frames

    for path in sorted(folder.glob("*.png")):
        image = pygame_module.image.load(str(path)).convert()
        image = pygame_module.transform.smoothscale(image, (SCREEN_WIDTH, SCREEN_HEIGHT))
        frames.append(image)

    return frames


def load_all_animations(config, pygame_module):
    animations = {}

    for state in VALID_STATES:
        frames = load_frames_for_state(state, config, pygame_module)
        if frames:
            animations[state] = frames

    if DEFAULT_STATE not in animations:
        raise RuntimeError(f"No frames found for default state: {DEFAULT_STATE}")

    return animations


def hide_mouse():
    import pygame

    try:
        pygame.mouse.set_visible(False)
    except Exception:
        pass


def configure_sdl_environment(env):
    env.setdefault("SDL_FBDEV", "/dev/fb0")

    if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        env.setdefault("SDL_VIDEODRIVER", "kmsdrm")


def read_framebuffer_info(framebuffer_path):
    var = FbVarScreenInfo()
    fix = FbFixScreenInfo()

    with open(framebuffer_path, "rb", buffering=0) as framebuffer:
        fcntl.ioctl(framebuffer, FBIOGET_VSCREENINFO, var)
        fcntl.ioctl(framebuffer, FBIOGET_FSCREENINFO, fix)

    return FramebufferInfo(
        width=var.xres,
        height=var.yres,
        bits_per_pixel=var.bits_per_pixel,
        line_length=fix.line_length,
        red=BitField(var.red.offset, var.red.length),
        green=BitField(var.green.offset, var.green.length),
        blue=BitField(var.blue.offset, var.blue.length),
        transp=BitField(var.transp.offset, var.transp.length),
    )


def _scale_channel(value, bitfield):
    if bitfield.length <= 0:
        return 0

    return (value * ((1 << bitfield.length) - 1) // 255) << bitfield.offset


def pack_framebuffer_image(image, info):
    image = image.convert("RGB").resize((info.width, info.height))
    bytes_per_pixel = info.bits_per_pixel // 8

    if bytes_per_pixel not in (2, 3, 4):
        raise RuntimeError(f"Unsupported framebuffer depth: {info.bits_per_pixel}")

    row_bytes = info.width * bytes_per_pixel
    if row_bytes > info.line_length:
        raise RuntimeError("Framebuffer line length is smaller than the visible row")

    output = bytearray(info.line_length * info.height)
    pixels = image.load()

    for y in range(info.height):
        row_offset = y * info.line_length
        for x in range(info.width):
            red, green, blue = pixels[x, y]
            value = (
                _scale_channel(red, info.red)
                | _scale_channel(green, info.green)
                | _scale_channel(blue, info.blue)
            )
            output[row_offset + x * bytes_per_pixel : row_offset + (x + 1) * bytes_per_pixel] = value.to_bytes(
                bytes_per_pixel,
                byteorder="little",
            )

    return bytes(output)


def load_framebuffer_animations(config, info):
    animations = {}

    for state in VALID_STATES:
        folder = config.asset_dir / state
        frames = []

        if folder.exists():
            for path in sorted(folder.glob("*.png")):
                frames.append(pack_framebuffer_image(Image.open(path), info))

        if frames:
            animations[state] = frames

    if DEFAULT_STATE not in animations:
        raise RuntimeError(f"No frames found for default state: {DEFAULT_STATE}")

    return animations


def run_framebuffer_renderer(config, framebuffer_path="/dev/fb0"):
    info = read_framebuffer_info(framebuffer_path)
    animations = load_framebuffer_animations(config, info)

    current_state = DEFAULT_STATE
    previous_state = None
    frame_index = 0
    last_state_check = 0

    with open(framebuffer_path, "r+b", buffering=0) as framebuffer:
        while True:
            now = time.time()

            if now - last_state_check >= STATE_CHECK_SECONDS:
                current_state, _detail = read_state(config)
                last_state_check = now

            if current_state != previous_state:
                frame_index = 0
                previous_state = current_state

            frames = animations.get(current_state) or animations[DEFAULT_STATE]
            framebuffer.seek(0)
            framebuffer.write(frames[frame_index % len(frames)])
            framebuffer.flush()

            frame_index += 1
            time.sleep(1 / STATE_FPS.get(current_state, FPS))


def run_pygame_renderer(config):
    import pygame

    pygame.init()
    pygame.display.set_caption("Pi Avatar")

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    hide_mouse()

    animations = load_all_animations(config, pygame)

    current_state = DEFAULT_STATE
    previous_state = None
    frame_index = 0
    last_state_check = 0
    detail = ""

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                raise SystemExit

        now = time.time()

        if now - last_state_check >= STATE_CHECK_SECONDS:
            current_state, detail = read_state(config)
            last_state_check = now

        if current_state != previous_state:
            frame_index = 0
            previous_state = current_state

        frames = animations.get(current_state) or animations[DEFAULT_STATE]
        frame = frames[frame_index % len(frames)]

        screen.blit(frame, (0, 0))

        if detail:
            text = font.render(detail[:80], True, (230, 230, 230))
            screen.blit(text, (16, SCREEN_HEIGHT - 30))

        pygame.display.flip()

        frame_index += 1
        clock.tick(STATE_FPS.get(current_state, FPS))


def main():
    config = load_config(os.environ)

    configure_sdl_environment(os.environ)

    try:
        run_pygame_renderer(config)
    except Exception as exc:
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            raise

        print(f"pygame display unavailable ({exc}); falling back to /dev/fb0", flush=True)
        run_framebuffer_renderer(config, os.environ.get("FRAMEBUFFER", "/dev/fb0"))


if __name__ == "__main__":
    main()
