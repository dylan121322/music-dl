"""Test favorite songs API with saved cookies."""
import json, requests, sys
from pathlib import Path

sys.path.insert(0, '/Users/boqing/Desktop/code/qqmusic-dl')
from utils import load_config, cookie_to_auth

CONFIG_PATH = Path.home() / '.config' / 'qqmusic-dl' / 'config.json'
config = load_config(CONFIG_PATH)
cookie_str = config.get('cookie', '')

auth = cookie_to_auth(cookie_str)
uin = auth['uin']
g_tk = auth['g_tk']
print(f'Using saved cookie. uin={uin}, g_tk={g_tk}')

# Now test fav APIs
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://y.qq.com',
    'Cookie': cookie_str,
})

base = 'https://u.y.qq.com/cgi-bin/musicu.fcg'

tests = [
    ('music.musichallSong.SongListInter / GetMyFavSongList', {
        'module': 'music.musichallSong.SongListInter',
        'method': 'GetMyFavSongList',
        'param': {'page': 0, 'size': 10},
    }),
    ('music.musichallSong.SongListInter / GetFavSongList', {
        'module': 'music.musichallSong.SongListInter',
        'method': 'GetFavSongList',
        'param': {'page': 0, 'size': 10},
    }),
    ('music.musichallSong.SongListInter / getMyFav', {
        'module': 'music.musichallSong.SongListInter',
        'method': 'getMyFav',
        'param': {},
    }),
    ('music.personal.PersonalCenter / GetMyFav', {
        'module': 'music.personal.PersonalCenter',
        'method': 'GetMyFav',
        'param': {},
    }),
    ('music.fav.FavList / GetAllFavList', {
        'module': 'music.fav.FavList',
        'method': 'GetAllFavList',
        'param': {'uin': uin},
    }),
    ('music.srfDissInfo.DissInfo / getFavDiss', {
        'module': 'music.srfDissInfo.DissInfo',
        'method': 'getFavDiss',
        'param': {},
    }),
]

for label, mod in tests:
    req = {
        'req_0': mod,
        'comm': {'uin': uin, 'format': 'json', 'ct': '20', 'cv': 0},
    }
    url = base + '?g_tk=' + str(g_tk)
    resp = s.post(url, json=req, timeout=15)
    data = resp.json()
    code = data.get('req_0', {}).get('code', data.get('code'))
    rd = data.get('req_0', {}).get('data', {})

    sl = rd.get('songList') or rd.get('songlist') or rd.get('list')
    has_songs = bool(sl and len(sl) > 0)

    print(f'{label}: code={code}, songs={"YES("+str(len(sl))+")" if has_songs else "NO"}')
    if has_songs:
        for item in sl[:3]:
            info = item.get('songInfo', item)
            name = info.get('name', info.get('songname', info.get('title', '?')))
            singer_list = info.get('singer', [])
            singer = singer_list[0].get('name', '?') if singer_list else '?'
            print(f'  {name} - {singer}')

print()
print('--- REST fav API ---')
resp2 = s.get('https://c.y.qq.com/fav/fcgi-bin/fcg_get_profile_order_asset.fcg', params={
    'loginUin': uin, 'hostUin': uin,
    'format': 'json', 'inCharset': 'utf8', 'outCharset': 'utf-8',
    'notice': '0', 'platform': 'yqq', 'needNewCode': '0',
}, timeout=15)
print(resp2.text[:500])
