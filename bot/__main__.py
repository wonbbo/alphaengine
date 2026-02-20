"""
Bot 진입점

실행 방법:
    python -m bot
"""

import asyncio

from bot.bootstrap import main

if __name__ == "__main__":
    asyncio.run(main())
