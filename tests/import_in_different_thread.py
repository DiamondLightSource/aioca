import asyncio
import sys
import threading

from aioca import caget

if __name__ == "__main__":

    async def get_value():
        print(await caget(sys.argv[1], timeout=0.5))

    # Run event loop in a different thread
    t = threading.Thread(
        target=asyncio.new_event_loop().run_until_complete, args=[get_value()]
    )
    t.start()
    t.join()
