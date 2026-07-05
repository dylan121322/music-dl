"""Music API client — search, play URLs, playlists."""
import sys
import time
import uuid
import re
import requests
from logger import get_logger
from typing import List, Optional
from models import Song

# Ensure /tmp/pylib is available for websocket-client
sys.path.insert(0, "/tmp/pylib")

logger = get_logger("api")

BASE_URL = "https://c.y.qq.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class MusicAPI:
    """Thin wrapper around QQ Music web API endpoints."""

    def __init__(self, cookie_str: str = ""):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": "https://y.qq.com",
            "Origin": "https://y.qq.com",
        })
        self.guid = str(uuid.uuid4()).replace("-", "")[:32].upper()
        self.uin = "0"
        self.g_tk = ""
        self.music_key = ""  # authst for GetVkey (unlocks higher quality)
        if cookie_str:
            self.set_cookie(cookie_str)

    def set_cookie(self, cookie_str: str) -> bool:
        """Set the cookie string for VIP auth. Returns True if valid."""
        from utils import cookie_to_auth, extract_music_key
        auth = cookie_to_auth(cookie_str)
        if not auth:
            return False
        # Set cookies on session's cookie jar for proper domain handling
        for part in auth["cookie_str"].split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip(), domain=".qq.com")
                self.session.cookies.set(k.strip(), v.strip(), domain=".y.qq.com")
        self.session.headers["Cookie"] = auth["cookie_str"]
        self.uin = auth["uin"]
        self.g_tk = auth["g_tk"]
        self.music_key = extract_music_key(cookie_str)
        return True

    def _get(self, path: str, params: dict, timeout: int = 15) -> dict:
        """GET request with rate-limit and error handling."""
        time.sleep(0.8)  # rate limit
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def search(self, keyword: str, page: int = 1, limit: int = 20) -> List[Song]:
        """Search songs by keyword. Returns list of Song objects."""
        # Try primary search endpoint
        songs = self._search_v1(keyword, page, limit)
        if songs:
            return songs
        # Fallback to musicu.fcg search endpoint
        logger.info("Primary search failed, trying fallback endpoint...")
        return self._search_v2(keyword, page, limit)

    def _search_v1(self, keyword: str, page: int, limit: int) -> List[Song]:
        """Primary: client_search_cp endpoint."""
        params = {
            "w": keyword,
            "p": page,
            "n": limit,
            "format": "json",
            "ct": "24",
            "cv": "0",
        }
        try:
            data = self._get("/soso/fcgi-bin/client_search_cp", params)
        except Exception as e:
            logger.warning("QQ Music search v1 failed: %s", e)
            return []
        songs = []
        song_list = data.get("data", {}).get("song", {}).get("list", [])
        for item in song_list:
            song = Song(
                mid=item.get("songmid", ""),
                title=item.get("songname", ""),
                singer=_extract_singer(item.get("singer", [])),
                album=item.get("albumname", ""),
                duration=int(item.get("interval", 0)),
                is_gray=False if self.g_tk else _is_gray(item),
                media_mid=_extract_media_mid(item),
            )
            songs.append(song)
        return songs

    def _search_v2(self, keyword: str, page: int, limit: int) -> List[Song]:
        """Fallback: music.search.SearchCgiService via musicu.fcg."""
        try:
            time.sleep(0.8)
            req = {
                "search": {
                    "module": "music.search.SearchCgiService",
                    "method": "DoSearchForQQMusicDesktop",
                    "param": {
                        "searchid": "1",
                        "remoteplace": "txt.qqmusic.top",
                        "search_type": 0,
                        "query": keyword,
                        "page_num": page,
                        "num_per_page": limit,
                        "grp": 1,
                    },
                }
            }
            url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
            resp = self.session.post(url, json=req, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            song_list = (
                data.get("search", {})
                .get("data", {})
                .get("body", {})
                .get("song", {})
                .get("list", [])
            )
            songs = []
            for item in song_list:
                songs.append(Song(
                    mid=item.get("mid", ""),
                    title=item.get("name", item.get("title", "")),
                    singer=_extract_singer(item.get("singer", [])),
                    album=item.get("album", {}).get("name", ""),
                    duration=int(item.get("interval", 0)),
                    is_gray=False if self.g_tk else _is_gray(item),
                    media_mid=_extract_media_mid(item),
                ))
            return songs
        except Exception as e:
            logger.warning("QQ Music search v2 failed: %s", e)
            return []

    # Quality filename templates (Mineradio strategy — batch probe all in one request).
    _FNAME_TEMPLATES = [
        ("RS01", ".flac", "hires"),
        ("F000", ".flac", "lossless"),
        ("M800", ".mp3", "exhigh"),
        ("M500", ".mp3", "standard"),
        ("C400", ".m4a", "aac"),
    ]

    def get_song_url(self, song_mid: str, quality: str = "320kbps",
                     media_mid: str = "") -> Optional[str]:
        """Get the playable/download URL for a song. Returns None if unavailable.

        Uses Mineradio's batch filename probing: one request covers all
        quality tiers and both song_mid + media_mid.
        """
        data = self._get_vkey_batch(song_mid, quality, media_mid)
        if not data:
            return None
        srv = data.get("server", "http://aqqmusic.tc.qq.com/")
        if not srv.endswith("/"):
            srv += "/"
        return srv + data["purl"]

    def _get_vkey_batch(self, song_mid: str, target_quality: str = "hires",
                        media_mid: str = "") -> Optional[dict]:
        """One-request batch GetVkey: probes all filename patterns × all media IDs.

        Ported from Mineradio's handleQQSongUrl.  Key improvements over songtype:
        - Multiple file format prefixes (RS01/F000/M800/M500/C400)
        - Dual ID probing (media_mid + song_mid)
        - authst (musicKey) for authenticated quality tiers
        - Falls back to single-file probe if batch returns empty
        """
        time.sleep(0.8)

        # Resolve quality starting point
        quality_rank = {"128kbps": "standard", "320kbps": "exhigh",
                        "flac": "lossless", "hires": "hires"}
        start_level = quality_rank.get(target_quality)
        if start_level is None:
            logger.warning("Unknown quality '%s', falling back to exhigh", target_quality)
            start_level = "exhigh"
        try:
            start_idx = next(i for i, t in enumerate(self._FNAME_TEMPLATES)
                             if t[2] == start_level)
        except StopIteration:
            logger.warning("Quality level '%s' not in templates, probing all", start_level)
            start_idx = 0
        templates = self._FNAME_TEMPLATES[start_idx:]

        # Build candidate media IDs: media_mid first, song_mid as fallback
        media_ids = [media_mid] if media_mid and media_mid != song_mid else []
        media_ids.append(song_mid)

        # Build filename list
        filenames = []
        for mid in media_ids:
            for prefix, ext, level in templates:
                filenames.append(f"{prefix}{mid}{ext}")

        # Build request
        param = {
            "guid": self.guid,
            "songmid": [song_mid] * len(filenames),
            "songtype": [0] * len(filenames),
            "uin": self.uin,
            "loginflag": 1,
            "platform": "20",
            "filename": filenames,
        }

        req_data = {
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": param,
            },
        }

        # Auth block — include musicKey as authst when available
        if self.g_tk:
            comm = {
                "uin": self.uin,
                "format": "json",
                "ct": 19 if self.music_key else 24,
                "cv": 0,
            }
            if self.music_key:
                comm["authst"] = self.music_key
            req_data["comm"] = comm

        try:
            url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
            if self.g_tk:
                url += f"?g_tk={self.g_tk}"
            resp = self.session.post(url, json=req_data, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            inner = result.get("req_0", {}).get("data", {})
            midurlinfo = inner.get("midurlinfo", [])
            sip_list = inner.get("sip", [])
            sip = sip_list[0] if sip_list else "http://aqqmusic.tc.qq.com/"

            if midurlinfo:
                # Return the first entry with a valid purl
                for item in midurlinfo:
                    purl = item.get("purl", "")
                    if purl:
                        return {"purl": purl, "server": sip}

            # Batch returned no playable URL — log and fall back to single probe
            logger.warning(
                "Batch GetVkey empty for %s (tried %d candidates, quality=%s)",
                song_mid, len(filenames), target_quality,
            )
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            logger.debug("Vkey batch request failed for %s: %s", song_mid, e)

        # Fallback: single-file probe with lowest quality (songtype=0, standard M500)
        return self._get_vkey_fallback(song_mid)

    def _get_vkey_fallback(self, song_mid: str) -> Optional[dict]:
        """Single-file fallback probe when batch GetVkey returns nothing.

        Uses the simplest file pattern (M500 MP3) with no auth requirements.
        Kept as emergency fallback in case the batch approach fails for any reason.
        """
        try:
            req_data = {
                "req_0": {
                    "module": "vkey.GetVkeyServer",
                    "method": "CgiGetVkey",
                    "param": {
                        "guid": self.guid,
                        "songmid": [song_mid],
                        "songtype": [0],
                        "uin": self.uin,
                        "loginflag": 1,
                        "platform": "20",
                        "filename": [f"M500{song_mid}.mp3"],
                    },
                }
            }
            url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
            resp = self.session.post(url, json=req_data, timeout=10)
            resp.raise_for_status()
            inner = resp.json().get("req_0", {}).get("data", {})
            midurlinfo = inner.get("midurlinfo", [])
            sip_list = inner.get("sip", [])
            sip = sip_list[0] if sip_list else "http://aqqmusic.tc.qq.com/"
            if midurlinfo:
                for item in midurlinfo:
                    purl = item.get("purl", "")
                    if purl:
                        logger.info("Fallback GetVkey succeeded for %s", song_mid)
                        return {"purl": purl, "server": sip}
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            logger.debug("Fallback GetVkey also failed for %s: %s", song_mid, e)
        return None

    def get_fav_songs(self, page: int = 0, size: int = 50) -> List[Song]:
        """Get user's favorite (hearted) songs. Requires login cookie."""
        req_data = {
            "req_0": {
                "module": "music.musichallSong.SongListInter",
                "method": "GetMyFavSongList",
                "param": {"page": page, "size": size},
            },
            "comm": {"uin": self.uin, "format": "json", "ct": "20", "cv": 0},
        }
        try:
            resp = self.session.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                json=req_data,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            song_list = (
                result.get("req_0", {}).get("data", {}).get("songList", []) or []
            )
            songs = []
            for item in song_list:
                info = item.get("songInfo", {})
                singer_list = info.get("singer", [])
                singer = " / ".join(s.get("name", "") for s in singer_list)
                songs.append(Song(
                    mid=info.get("mid", ""),
                    title=info.get("name", ""),
                    singer=singer,
                    album=info.get("album", {}).get("name", ""),
                    duration=int(info.get("interval", 0)),
                    is_gray=False,  # musicu path only runs when authenticated
                    media_mid=_extract_media_mid(info),
                ))
            return songs
        except Exception:
            return []

    def get_playlist_songs(self, playlist_id: str) -> List[Song]:
        """Fetch all songs from a QQ Music playlist by its ID."""
        # Method 1: CDP HTML extraction (most reliable)
        songs = MusicAPI.extract_playlist_from_html(playlist_id)
        if songs:
            return songs

        # Method 2: musicu.fcg API (requires auth)
        if self.g_tk:
            try:
                req_data = {
                    "req_0": {
                        "module": "music.musicasset.PlaylistDetailInter",
                        "method": "GetAll",
                        "param": {"tId": int(playlist_id), "offset": 0, "limit": 500},
                    },
                    "comm": {"uin": self.uin, "format": "json", "ct": "23"},
                }
                resp = self.session.post(
                    "https://u.y.qq.com/cgi-bin/musicu.fcg",
                    json=req_data, timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
                song_list = result.get("req_0", {}).get("data", {}).get("songList", [])
                if song_list:
                    songs = []
                    for item in song_list:
                        info = item.get("songInfo", {})
                        singer_list = info.get("singer", [])
                        singer = " / ".join(s.get("name", "") for s in singer_list)
                        songs.append(Song(
                            mid=info.get("mid", ""),
                            title=info.get("name", ""),
                            singer=singer,
                            album=info.get("album", {}).get("name", ""),
                            duration=int(info.get("interval", 0)),
                            is_gray=False,  # CDP HTML extraction: user is logged in
                            media_mid=_extract_media_mid(info),
                        ))
                    return songs
            except Exception:
                pass

        # Fallback: old REST API
        params = {
            "id": playlist_id,
            "format": "json",
            "type": "1",
        }
        data = self._get("/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg", params)
        songs = []
        cdlist = data.get("cdlist", [])
        for cd in cdlist:
            for item in cd.get("songlist", []):
                song = Song(
                    mid=item.get("songmid", ""),
                    title=item.get("songname", ""),
                    singer=_extract_singer(item.get("singer", [])),
                    album=item.get("albumname", ""),
                    duration=int(item.get("interval", 0)),
                    is_gray=False if self.g_tk else _is_gray(item),
                    media_mid=_extract_media_mid(item),
                )
                songs.append(song)
        return songs

    @staticmethod
    def extract_playlist_from_html(playlist_id: str) -> List[Song]:
        """Extract song list from playlist page HTML via CDP Chrome."""
        import json as j
        import re
        try:
            import requests as req
            from websocket import create_connection as cc

            resp = req.get("http://localhost:9233/json/list", timeout=5)
            pages = resp.json()
            if not pages:
                return []
            target = pages[0]
            url = target.get("url", "")
            ws = cc(target["webSocketDebuggerUrl"], timeout=10)

            # Navigate if not already on playlist page
            if playlist_id not in url:
                ws.send(j.dumps({"id": 1, "method": "Page.navigate",
                    "params": {"url": f"https://y.qq.com/n/ryqq_v2/playlist/{playlist_id}"}}))
                ws.recv()
                time.sleep(3)

            # Get page HTML
            ws.send(j.dumps({"id": 2, "method": "Runtime.evaluate",
                "params": {"expression": "document.documentElement.outerHTML",
                           "returnByValue": True}}))
            time.sleep(2)
            ws.settimeout(5)
            html = ""
            try:
                result = j.loads(ws.recv())
                html = result.get("result", {}).get("result", {}).get("value", "")
            except Exception:
                pass
            ws.close()

            if not html:
                return []

            # Find and extract the songList JSON
            pos = html.find('"songList":[')
            if pos < 0:
                return []

            start = pos + len('"songList":')
            depth = 0
            end = start
            in_string = False
            for i, ch in enumerate(html[start:], start):
                if ch == '"' and (i == start or html[i - 1] != '\\'):
                    in_string = not in_string
                elif not in_string:
                    if ch == '[':
                        depth += 1
                    elif ch == ']':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break

            json_str = html[start:end].replace("undefined", "null")
            song_data = j.loads(json_str)

            songs = []
            for item in song_data:
                album_info = item.get("album", {})
                singer_list = item.get("singer", [])
                singer = " / ".join(s.get("name", "") for s in singer_list)
                songs.append(Song(
                    mid=item.get("mid", ""),
                    title=item.get("name", item.get("title", "")),
                    singer=singer,
                    album=album_info.get("name", ""),
                    duration=int(item.get("interval", 0)),
                    is_gray=False,  # CDP = user is logged in
                    media_mid=_extract_media_mid(item),
                ))
            return songs
        except Exception as e:
            logger.debug("extract_playlist_from_html: %s", e)
            return []

    @staticmethod
    def extract_playlist_id(url_or_id: str) -> str:
        """Extract playlist ID from a QQ Music URL or return the raw string.

        Supports:
          - https://y.qq.com/n/ryqq/playlist/123456.html
          - https://y.qq.com/n/ryqq_v2/playlist/123456?ADTAG=...
          - https://i.y.qq.com/n2/m/share/details/taoge.html?id=123456
          - https://c6.y.qq.com/base/fcgi-bin/u?__=TOKEN  (short link)
        """
        if url_or_id.isdigit():
            return url_or_id

        # Pattern 1: /playlist/123456 (in path)
        match = re.search(r"/playlist/(\d+)", url_or_id)
        if match:
            return match.group(1)

        # Pattern 2: ?id=123456 (in query string for share links)
        match = re.search(r"[?&]id=(\d+)", url_or_id)
        if match:
            return match.group(1)

        # Pattern 3: short URL -> follow redirect
        if "/base/fcgi-bin/u" in url_or_id or "c6.y.qq.com" in url_or_id:
            try:
                resp = requests.get(url_or_id, allow_redirects=True, timeout=15,
                    headers={"User-Agent": USER_AGENT})
                return MusicAPI.extract_playlist_id(resp.url)
            except requests.RequestException:
                pass

        # Pattern 4: /taoge.html?id=123456 (share detail page)
        match = re.search(r"/taoge\.html\?[^#]*[?&]id=(\d+)", url_or_id)
        if match:
            return match.group(1)

        raise ValueError(f"Cannot extract playlist ID from: {url_or_id}")


def _extract_singer(singers: List[dict]) -> str:
    """Join singer names from the singer list."""
    return " / ".join(s.get("name", "") for s in singers)


def _extract_media_mid(item: dict) -> str:
    """Extract media_mid from a song item (alternative file ID for GetVkey).

    Some songs register their audio files under file.media_mid instead of
    the song's main mid.  Probing both IDs increases the chance of finding
    a playable URL.
    """
    file_info = item.get("file", {})
    if isinstance(file_info, dict):
        return file_info.get("media_mid", "")
    return ""


def _is_gray(item: dict) -> bool:
    """Check if a song is 'gray' (unavailable/paywalled) in the raw API response.

    Note: Callers with auth (VIP login) pass is_gray=False on the Song object
    directly rather than relying on this function's output.
    """
    pay = item.get("pay", {})
    if isinstance(pay, dict):
        if int(pay.get("payplay", 0)) == 1:
            return True
    if item.get("disabled") == 1:
        return True
    return False
