"""Run the Help Desk web application."""

import os
import socket
import sys

import uvicorn

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


if __name__ == "__main__":
    if port_in_use(HOST, PORT):
        print(
            f"Port {PORT} is already in use (Windows error 10048).\n"
            f"Another server is probably still running.\n\n"
            f"Fix options:\n"
            f"  1. Close the other terminal where you ran 'python run.py', or\n"
            f"  2. Kill the process:  netstat -ano | findstr :{PORT}\n"
            f"     then:  taskkill /PID <pid> /F\n"
            f"  3. Use a different port:  $env:PORT=8001; python run.py\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting Help Desk at http://{HOST}:{PORT}")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
