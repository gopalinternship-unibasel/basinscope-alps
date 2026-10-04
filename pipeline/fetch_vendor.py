"""Fonts and the one script library the self-hosted page uses, fetched once so that the site serves them itself.

  python fetch_vendor.py <pipeline folder>

Writes
  build/fonts/*.woff2, build/fonts/fonts.css    Barlow Semi Condensed, IBM Plex Mono, Source Sans 3 (SIL Open Font License), latin and latin-ext
  build/vendor/geotiff.js                       geotiff.js 2.1.3 (MIT licence), the browser bundle, for reading the satellite files

build.py copies both folders to the site's assets/ and points the self-hosted page at them. The page published on claude.ai keeps the
Google Fonts link, the only font source allowed there.
"""
import os, re, sys, urllib.request

SP = sys.argv[1]
B = SP + "/build/"
CSS = "https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;500;600;700&display=swap"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}  # a current browser gets woff2
get = lambda url: urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()

os.makedirs(B + "fonts", exist_ok=True)
os.makedirs(B + "vendor", exist_ok=True)
css, out, names = get(CSS).decode(), [], {}
for subset, body in re.findall(r"/\* ([a-z-]+) \*/\s*@font-face \{(.*?)\}", css, re.S):
    if subset not in ("latin", "latin-ext"):
        continue
    fam = re.search(r"font-family: '([^']+)'", body).group(1)
    url = re.search(r"url\((https://[^)]+\.woff2)\)", body).group(1)
    if url not in names:  # a variable font serves several weights from one file
        wt = re.search(r"font-weight: ([\d ]+);", body).group(1).replace(" ", "-")
        names[url] = f"{fam.lower().replace(' ', '-')}-{wt}-{subset}.woff2"
        if any(v == names[url] for k, v in names.items() if k != url):
            names[url] = names[url].replace(".woff2", f"-{len(names)}.woff2")
        open(B + "fonts/" + names[url], "wb").write(get(url))
    out.append("@font-face {" + body.replace(url, names[url]).rstrip() + "\n}")
open(B + "fonts/fonts.css", "w", encoding="utf-8").write("/* Barlow Semi Condensed, IBM Plex Mono, Source Sans 3: SIL Open Font License 1.1 */\n" + "\n".join(out) + "\n")
print("fonts:", len(names), "files,", sum(os.path.getsize(B + "fonts/" + f) for f in names.values()) // 1024, "kB,", len(out), "rules")

lib = get("https://cdn.jsdelivr.net/npm/geotiff@2.1.3/dist-browser/geotiff.js")
open(B + "vendor/geotiff.js", "wb").write(lib)
print("geotiff.js:", len(lib) // 1024, "kB")
