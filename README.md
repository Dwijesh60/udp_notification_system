# UDP Notification System

A small Python project for sending and receiving UDP notifications on a local network.

## Project structure

- `src/`
  - `udp_core.py` — core UDP networking logic.
  - `udp_gui.py` — graphical user interface layer.
  - `test_lan_logic.py` — LAN test and notification logic.

## Getting started

1. Make sure Python is installed.
2. Open a terminal in this repository.
3. Run the GUI application:

```bash
python src/udp_gui.py
```

If you want to run the networking core directly instead, use:

```bash
python src/udp_core.py
```

## Notes

- The source files now live in `src/` instead of `files(2)/`.
- Adjust the entrypoint if your project uses a different startup script.
