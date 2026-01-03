"""
Unified entrypoint for PyInstaller.

Default: launch the Terminal UI which embeds the backend API server.
"""

import argparse


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="netmon")
    p.add_argument(
        "--mode",
        choices=["tui", "api", "web"],
        default="tui",
        help="tui = terminal app (default), api = backend only, web = original web UI",
    )
    p.add_argument("--host", default="127.0.0.1", help="API host for --mode api")
    p.add_argument("--port", type=int, default=8765, help="API port for --mode api")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if args.mode == "tui":
        from terminal_app import NetMonTUI

        NetMonTUI().run()
        return

    if args.mode == "api":
        from server import run_server

        run_server(host=args.host, port=args.port)
        return

    # args.mode == "web"
    # The original web UI uses eventlet monkey-patching; keep it isolated.
    import app as web_app

    web_app.socketio.run(web_app.app, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()

