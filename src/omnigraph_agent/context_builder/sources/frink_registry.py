"""
Fetch knowledge graph metadata from the FRINK OKN registry.

The registry at https://frink.renci.org/registry/ provides title and description
for each KG. Used to enrich text_blurb so omnigraph context files are comparable
to mcp-proto-okn's metadata/descriptions (and the get_description() output).
"""

import re
from html import unescape
from typing import Dict, Optional
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


FRINK_REGISTRY_KG_URL = "https://frink.renci.org/registry/kgs/{kg_id}/"


class FrinkRegistryClient:
    """Fetches KG title and description from the FRINK OKN registry."""

    def get_kg_metadata(self, kg_id: str) -> Optional[Dict[str, str]]:
        """
        Fetch title and description for a knowledge graph from the FRINK registry.

        Args:
            kg_id: Graph shortname (e.g. 'nde', 'biobricks-aopwiki').

        Returns:
            Dict with 'title' and 'description' (one or both may be empty string),
            or None if the page is unavailable or cannot be parsed.
        """
        url = FRINK_REGISTRY_KG_URL.format(kg_id=kg_id)
        try:
            with urlopen(url, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, OSError, TypeError):
            return None

        title: Optional[str] = None
        description: Optional[str] = None

        # Prefer <h1> for title (MkDocs style)
        m = re.search(r"<h1[^>]*>([^<]+)</h1>", raw, re.IGNORECASE | re.DOTALL)
        if m:
            title = unescape(m.group(1).strip())

        # Prefer first substantial <p> for description
        m = re.search(r"<p[^>]*>([^<]{50,})</p>", raw, re.IGNORECASE | re.DOTALL)
        if m:
            description = unescape(m.group(1).strip())
        if not description:
            # Fallback: first <h3> (some pages use ### for the lead paragraph)
            m = re.search(r"<h3[^>]*>([^<]+)</h3>", raw, re.IGNORECASE)
            if m:
                description = unescape(m.group(1).strip())

        if not title and not description:
            return None

        return {"title": title or "", "description": description or ""}
