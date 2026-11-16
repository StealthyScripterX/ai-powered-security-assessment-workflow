"""Dev-server entrypoint that ensures the process cwd is backend/
(needed because app/main.py mounts static files with a path relative
to cwd), regardless of where it was launched from.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
