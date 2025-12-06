from typing import Any, Dict

import aiohttp

from .config import settings


class NcbiError(Exception):
    pass


class SnpNotFoundError(NcbiError):
    pass


class NcbiUnavailableError(NcbiError):
    pass


async def fetch_snp(rsid: str) -> Dict[str, Any]:
    if not rsid.startswith("rs"):
        raise ValueError("rsid must start with 'rs'")
    numeric_id = rsid[2:]
    url = f"https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/{numeric_id}"

    timeout = aiohttp.ClientTimeout(total=settings.ncbi_timeout)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 404:
                    raise SnpNotFoundError(f"SNP {rsid} not found")
                if resp.status >= 500:
                    raise NcbiUnavailableError(f"NCBI API error {resp.status}")
                if resp.status != 200:
                    raise NcbiError(f"Unexpected status code {resp.status}")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise NcbiUnavailableError(f"Network error: {e}") from e
