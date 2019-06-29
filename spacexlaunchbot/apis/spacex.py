"""Handles interactions with the SpaceX API
As of 13/01/19, API rate limit is 50 req/sec per IP
"""

import aiohttp
import logging
from typing import Dict


async def get_launch_dict(launch_number: int = 0) -> Dict:
    """Get a launch dict for the given launch
    If launch_number <= 0 (the default), get the "next" launch
    Returns {} on failure
    """

    route = str(launch_number) if launch_number > 0 else "next"
    spacex_api_url = f"https://api.spacexdata.com/v3/launches/{route}"

    async with aiohttp.ClientSession() as session:
        async with session.get(spacex_api_url) as response:

            if response.status != 200:
                logging.error(f"Response status: {response.status}")
                return {}

            try:
                launch_dict = await response.json()

            except aiohttp.ContentTypeError:
                logging.error("JSON decode failed")
                return {}

            return launch_dict