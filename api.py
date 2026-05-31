"""Music API client — search, play URLs, playlists."""
import sys
import time
import uuid
import re
import logging
import requests
from typing import List, Optional
from models import Song

# Ensure /tmp/pylib is available for websocket-client
sys.path.insert(0, "/tmp/pylib")

logger = logging.getLogger(__name__)

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
        if cookie_str:
            self.set_cookie(cookie_str)

    def set_cookie(self, cookie_str: str) -> bool:
        """Set the cookie string for VIP auth. Returns True if valid."""
        from utils import cookie_to_auth
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
                ))
            return songs
        except Exception as e:
            logger.warning("QQ Music search v2 failed: %s", e)
            return []

    def get_song_url(self, song_mid: str, quality: str = "320kbps") -> Optional[str]:
        """Get the playable download URL for a song. Returns None if unavailable.

        Quality levels: 128kbps (songtype=0), 320kbps (songtype=1), flac (songtype=2).
        Higher qualities require login. When not logged in, falls back to 128kbps.
        """
        st_map = {"128kbps": 0, "320kbps": 1, "flac": 2}
        songtype = st_map.get(quality, 1)

        def _build_url(p, data):
            # Use alternative CDN since aqqmusic.tc.qq.com is blocked on mobile networks
            servers = ["http://sjy6.stream.qqmusic.qq.com/",
                       "http://aqqmusic.tc.qq.com/",
                       "http://stream.qqmusic.tc.qq.com/"]
            srv = data.get("server", servers[0])
            if not srv or "aqqmusic.tc.qq.com" in srv:
                srv = servers[0]
            if not srv.endswith("/"):
                srv += "/"
            if ".m4a" in p.lower():
                p = p.rsplit(".", 1)[0] + ".mp3"
            return srv + p
            if ".m4a" in p.lower():
                p = p.rsplit(".", 1)[0] + ".mp3"
            return srv + p

        # Try requested quality first
        data = self._get_vkey(song_mid, songtype)
        if data and data.get("purl"):
            return _build_url(data["purl"], data)

        # If logged in but higher quality failed, try 128kbps
        if songtype > 0:
            data = self._get_vkey(song_mid, 0)
            if data and data.get("purl"):
                return _build_url(data["purl"], data)

        return None

    def _get_vkey(self, song_mid: str, songtype: int = 0) -> Optional[dict]:
        """Request the vkey needed to construct the play URL. songtype: 0=lq 1=hq 2=flac."""
        time.sleep(0.8)  # rate limit
        req_data = {
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "guid": self.guid,
                    "songmid": [song_mid],
                    "songtype": [songtype],
                    "uin": self.uin,
                    "loginflag": 1,
                    "platform": "20",
                },
            }
        }
        # If authenticated, add the comm block with uin and g_tk
        if self.g_tk:
            req_data["comm"] = {
                "uin": self.uin,
                "format": "json",
                "ct": "20",
                "cv": 0,
                "g_tk": self.g_tk,
            }

        try:
            url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
            if self.g_tk:
                url += f"?g_tk={self.g_tk}"
            resp = self.session.post(url, json=req_data, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            inner = result.get("req_0", {}).get("data", {})
            midurlinfo = inner.get("midurlinfo", [])
            sip_list = inner.get("sip", ["http://aqqmusic.tc.qq.com/"])
            if midurlinfo:
                item = midurlinfo[0]
                purl = item.get("purl", "")
                if not purl:
                    return None  # song is paywalled
                return {
                    "purl": purl,
                    "server": sip_list[0],
                }
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug("Vkey request failed for %s: %s", song_mid, e)
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


def _is_gray(item: dict) -> bool:
    """Check if a song is 'gray' (unavailable/paywalled).

    Note: This only checks the raw API response. Callers that have auth (VIP login)
    should pass authenticated=True to NOT mark paywalled songs as gray.
    """
    pay = item.get("pay", {})
    if isinstance(pay, dict):
        if int(pay.get("payplay", 0)) == 1:
            return True
    if item.get("disabled") == 1:
        return True
    return False
