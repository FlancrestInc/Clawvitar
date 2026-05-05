#!/usr/bin/env python3

import os

from pi_avatar.config import load_config
from pi_avatar.http_monitor import run_monitor


def main():
    run_monitor(load_config(os.environ))


if __name__ == "__main__":
    main()
