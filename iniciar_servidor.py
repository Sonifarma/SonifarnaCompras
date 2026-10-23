"""Stable process entry point used by the Windows controller."""
from pathlib import Path
import uvicorn

if __name__ == '__main__':
    uvicorn.run('app:app', app_dir=str(Path(__file__).resolve().parent),
                host='127.0.0.1', port=8766, reload=False)
