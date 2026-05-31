"""GitHub code search source — find mp3 files in public repositories."""
from typing import Optional, List
import requests
from sources.base import MusicSource, SearchResult

API = "https://api.github.com"


class GithubSource(MusicSource):
    name = "github"

    def search(self, title: str, artist: str = "") -> List[SearchResult]:
        """Search GitHub for mp3 files matching the query."""
        query = f"{title} {artist}".strip()
        # Search for mp3 files with the song name
        queries = [
            f"{query} extension:mp3",
            f"{query} extension:m4a",
            f"{query} extension:flac",
        ]
        all_results = []
        for q in queries[:2]:  # Limit to avoid rate limits
            results = self._search_code(q)
            all_results.extend(results)
            if len(all_results) >= 3:
                break
        return all_results[:10]

    def _search_code(self, query: str) -> List[SearchResult]:
        """Search GitHub code for audio files. Rate limit: 10 req/min unauthenticated."""
        try:
            resp = requests.get(
                f"{API}/search/code",
                params={"q": query, "per_page": 5},
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "music-dl",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception:
            return []

        results = []
        for item in data.get("items", []):
            raw_url = (
                item["html_url"]
                .replace("github.com", "raw.githubusercontent.com")
                .replace("/blob/", "/")
            )
            repo_name = item["repository"]["full_name"]
            path = item["path"]
            title = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

            results.append(SearchResult(
                title=title,
                artist=repo_name.split("/")[0],
                download_url=raw_url,
                free=True,
                match_score=0.3,  # GitHub results are low confidence
            ))
        return results

    def get_download_url(self, song_id: str) -> Optional[str]:
        """Return the raw download URL directly."""
        return song_id if song_id.startswith("http") else None
