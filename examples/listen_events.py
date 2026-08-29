"""Print local Satellite1 hardware events as they arrive."""

import asyncio

from satellite1 import AsyncSatellite1Client


async def main() -> None:
    async with AsyncSatellite1Client() as satellite:
        async for event in satellite.events.subscribe(include_current=True):
            print(event, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
