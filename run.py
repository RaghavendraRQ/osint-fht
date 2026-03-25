#!/usr/bin/env python3
"""Application entrypoint – launches the FastAPI server via uvicorn."""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="OSINT Framework for Human Trafficker Identification"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Port")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    uvicorn.run(
        "src.web.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
