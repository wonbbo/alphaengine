"""
Web 진입점

실행 방법:
    python -m web
"""

import uvicorn

from core.constants import Defaults

if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host=Defaults.WEB_HOST,
        port=Defaults.WEB_PORT,
        reload=False,
    )
