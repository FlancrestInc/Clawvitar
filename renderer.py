#!/usr/bin/env python3

import json
import os
import time

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


def main():
    config = load_config(os.environ)

    configure_sdl_environment(os.environ)

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


if __name__ == "__main__":
    main()
