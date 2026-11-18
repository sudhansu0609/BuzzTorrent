"""Your video jockey. Learns from the titles you press ♥ on and lines up "For you" rows:

- *Because you liked X*: works Wikipedia considers similar to a liked title (its "morelike"
  search), kept to films / shows / albums.
- *More with <person>*: a director or star who keeps turning up in your likes.
- *New <genre> for you*: this year's and last year's releases in your favourite genres and
  languages (Wikipedia's "<year> <Language>-language films" categories).
- *Something different*: a popular genre you haven't liked yet, in your language.

Everything is keyless (Wikipedia + Wikidata, via SmartSearch / DetailsService) and cached; a
row is rebuilt in the background when the likes change, never while the TV waits.
"""
from __future__ import annotations

import random
import re
import threading
import time
import urllib.parse
from collections import Counter

from .details import DetailsService
from .models import Result
from .safehttp import FetchError
from .smart import SmartSearch
from .tvstate import TvState

TTL = 6 * 3600
PER_ROW = 10
MIN_ROW = 3
GENRES = ["action", "comedy", "drama", "thriller", "romance", "horror", "science fiction", "animation",
          "documentary", "crime", "adventure", "mystery", "fantasy", "musical", "war"]
# "action film" -> "action", "Hindi-language film" -> dropped (it is a language, not a genre)
NOT_GENRE = re.compile(r"language|film$|^film|television|series|cinema", re.I)
KIND_TEMPLATE = {"movies": "Infobox film", "tv": "Infobox television", "music": "Infobox album"}
KIND_WORD = {"movies": "film", "tv": "television series", "music": "album"}
KIND_LABEL = {"movies": "movies", "tv": "shows", "music": "albums"}
WIKI_URL = re.compile(r"^https://([a-z]{2,3})\.wikipedia\.org/wiki/(.+)$")
# Articles that mention films but aren't one: people, characters, genres, lists...
NOT_WORK = re.compile(r"\b(actor|actress|director|producer|writer|screenwriter|singer|composer|musician|comedian|"
                      r"character|characters|genre|archetype|franchise|film series|list of|award|awards|festival|"
                      r"studio|company|person|people|family|term|concept|trope|duo|trio|group|band|industry|"
                      r"filmography|discography|soundtrack|song|single)\b", re.I)


def _genre_words(genres: list[str]) -> list[str]:
    out = []
    for g in genres or []:
        g = re.sub(r"\s*\b(film|films|movie|television|tv|series|video game)\b\s*", " ", g, flags=re.I).strip().lower()
        if g and not NOT_GENRE.search(g) and g not in out:
            out.append(g)
    return out


class Taste:
    def __init__(self, state: TvState, smart: SmartSearch | None, details: DetailsService):
        self.state = state
        self.smart = smart
        self.details = details
        self._lock = threading.Lock()
        self._rows: list[dict] = []
        self._built = 0.0
        self._version = 0          # bumps whenever the likes change
        self._built_version = -1
        self._building = False

    # ---------------------------------------------------------------- likes
    def like(self, body: dict, result: Result | None = None) -> dict:
        like = self.state.like_add(body)
        self._invalidate()
        if self.smart is not None and not like.get("profile"):
            threading.Thread(target=self._enrich, args=(like, result), name="taste-enrich", daemon=True).start()
        return like

    def unlike(self, lid: str) -> bool:
        gone = self.state.like_remove(lid)
        if gone:
            self._invalidate()
        return gone

    def _invalidate(self) -> None:
        with self._lock:
            self._version += 1

    def _enrich(self, like: dict, result: Result | None) -> None:
        try:
            profile = self.profile_for(like, result)
        except Exception:
            profile = {}
        self.state.set_profile(like["id"], profile)
        self._invalidate()
        self.for_you()                       # kick off the rebuild now that more is known

    def profile_for(self, like: dict, result: Result | None = None) -> dict:
        """What Wikipedia/Wikidata know about a liked title: genres, people, language, article."""
        r = result or Result(title=like["title"], provider="likes", category=like["category"], year=like.get("year"),
                             id=f"like:{like['id']}")
        d = self.details.for_result(r, use_wiki=True)
        people = [v for f in d.get("facts", []) if f["label"] in ("Directed by", "Created by", "Performed by")
                  for v in f["values"][:2]]
        people += (d.get("cast") or [])[:4]
        wiki, wiki_title, qid = "en", None, None
        for link in d.get("links", []):
            m = WIKI_URL.match(link.get("url") or "")
            if m:
                wiki, wiki_title = m.group(1), urllib.parse.unquote(m.group(2)).replace("_", " ")
            elif "wikidata.org/wiki/" in (link.get("url") or ""):
                qid = link["url"].rsplit("/", 1)[-1]
        profile = {"matched": bool(d.get("matched")), "wiki": wiki, "wiki_title": wiki_title, "qid": qid,
                   "genres": _genre_words(d.get("genres") or []), "people": list(dict.fromkeys(people))[:6],
                   "language": (d.get("language") or "").split(",")[0].strip() or None,
                   "country": (d.get("country") or "").split(",")[0].strip() or None, "year": d.get("year")}
        if d.get("poster") and not like.get("thumb"):
            self.state.like_add({**like, "thumb": d["poster"]})
        return profile

    # ------------------------------------------------------------- for you
    def for_you(self) -> dict:
        """The rows, from the cache. Starts a background build when they are missing or stale."""
        likes = self.state.likes()
        if self.smart is None:
            return {"rows": [], "likes": len(likes), "building": False, "off": True}
        with self._lock:
            stale = self._built_version != self._version or time.time() - self._built > TTL
            if stale and not self._building and likes:
                self._building = True
                threading.Thread(target=self._build_safely, name="taste-build", daemon=True).start()
            return {"rows": [r for r in self._rows] if likes else [], "likes": len(likes),
                    "building": self._building, "built": self._built}

    def _build_safely(self) -> None:
        while True:
            with self._lock:
                version = self._version
            try:
                rows = self.build()
            except Exception:
                rows = []
            with self._lock:
                self._rows, self._built, self._built_version = rows, time.time(), version
                if self._version == version:
                    self._building = False
                    return                       # else the likes changed meanwhile: go again

    def build(self) -> list[dict]:
        likes = self.state.likes()
        profiled = [l for l in likes if l.get("profile")]
        seen = {l["title"].lower() for l in likes} | self.state.finished_titles()
        rows: list[dict] = []

        def add_row(label: str, reason: str, items: list[dict], kind: str = "movies") -> None:
            picked = []
            for it in items:
                t = it["title"].lower()
                if t in seen or any(t == p["title"].lower() for p in picked):
                    continue
                seen.add(t)
                picked.append({**it, "reason": reason, "category": kind})
                if len(picked) >= PER_ROW:
                    break
            if len(picked) >= MIN_ROW:
                rows.append({"label": label, "items": picked})

        # 1. because you liked …  (the three newest likes we know something about)
        for like in [l for l in profiled if l["profile"].get("wiki_title")][:3]:
            kind = like["category"] if like["category"] in KIND_TEMPLATE else "movies"
            add_row(f"Because you liked {like['title']}", f"Like {like['title']}", self._similar(like, kind), kind)

        # 2. the taste profile
        genres, people, langs, kinds = Counter(), Counter(), Counter(), Counter()
        for l in profiled:
            p = l["profile"]
            genres.update(p.get("genres") or [])
            people.update(p.get("people") or [])
            if p.get("language"):
                langs[p["language"]] += 1
            kinds[l["category"]] += 1
        for l in likes:
            kinds.setdefault(l["category"], 0)
        kind = max(kinds, key=kinds.get) if kinds else "movies"
        if kind == "music":
            kind = "movies"
        lang = langs.most_common(1)[0][0] if langs else None
        top = [g for g, _ in genres.most_common(3)]

        # 3. people who keep turning up (or, until someone does, the newest like's director / star)
        regulars = [p for p, n in people.most_common(4) if n >= 2 or len(profiled) <= 2]
        if not regulars and profiled and profiled[0]["profile"].get("people"):
            regulars = profiled[0]["profile"]["people"][:1]
        for person in regulars:
            add_row(f"More with {person}", f"You like {person}", self._by_person(person, kind, lang), kind)
            if sum(1 for r in rows if r["label"].startswith("More with")) >= 2:
                break

        # 4. new and fresh in the genres you like
        year = time.localtime().tm_year
        for g in top[:2] or [None]:
            label = f"New {g} {KIND_LABEL[kind]}" if g else f"New {KIND_LABEL[kind]}"
            add_row(label + (f" in {lang}" if lang else ""), "New this year", self._fresh(g, kind, lang, (year, year - 1)), kind)

        # 5. something different: a well-liked genre you haven't tried, in your language
        other = [g for g in GENRES if g not in genres]
        if other:
            g = random.Random(len(likes)).choice(other[:6])
            add_row(f"Something different: {g}", f"Try some {g}", self._by_genre(g, kind, lang), kind)
        return rows

    # ----------------------------------------------------------- lookups
    def _search(self, text: str, category: str, wiki: str = "en", limit: int = 16) -> list[dict]:
        try:
            titles, _ = self.smart._search(text, limit=limit, wiki=wiki)
            works = self.smart.describe(titles, wiki=wiki)
        except (FetchError, ValueError, KeyError):
            return []
        out = []
        for w in works:
            if not self.smart.is_kind(w["description"], category, wiki) or not self._is_work(w, wiki):
                continue
            out.append({"title": w["title"], "year": w.get("year"), "description": w.get("description") or "",
                        "thumb": self.details.register_image(w.get("thumb")), "qid": w.get("qid")})
        return out

    @staticmethod
    def _is_work(w: dict, wiki: str) -> bool:
        """A film / show / album, not an actor, character or genre article."""
        year = w.get("year")
        if not year or not 1890 <= year <= time.localtime().tm_year + 1:
            return False
        if wiki != "en":
            return True
        return not NOT_WORK.search(w.get("description") or "")

    def _first_enough(self, queries: list[str], category: str, wiki: str = "en") -> list[dict]:
        """The first query that finds a row's worth; else the best of them."""
        best: list[dict] = []
        for q in queries:
            got = self._search(q, category, wiki)
            if len(got) >= PER_ROW:
                return got
            if len(got) > len(best):
                best = got
        return best

    def _similar(self, like: dict, kind: str) -> list[dict]:
        """Wikipedia's "more like this" for the article, then the same genres + language + people."""
        p = like["profile"]
        items = self._search("morelike:" + p["wiki_title"].replace(" ", "_"), kind, p.get("wiki", "en"), limit=20)
        if len(items) < PER_ROW:
            lang, genres = p.get("language"), p.get("genres") or []
            filt = f'hastemplate:"{KIND_TEMPLATE[kind]}" -"{p["wiki_title"]}"'
            queries = []
            if genres and lang:
                queries.append(f'{filt} incategory:"{lang}-language {KIND_WORD[kind]}s" {" ".join(genres[:2])}')
            if p.get("people"):
                queries.append(f'{filt} "{p["people"][0]}" {" ".join(genres[:1])}')
            if genres:
                queries.append(f'{filt} {lang or ""} {" ".join(genres[:2])}')
            for q in queries:
                for it in self._search(q, kind):
                    if all(it["title"].lower() != x["title"].lower() for x in items):
                        items.append(it)
                if len(items) >= PER_ROW:
                    break
        return items

    def _by_person(self, person: str, kind: str, lang: str | None) -> list[dict]:
        return self._search(f'hastemplate:"{KIND_TEMPLATE[kind]}" "{person}"', kind)

    def _fresh(self, genre: str | None, kind: str, lang: str | None, years: tuple[int, ...]) -> list[dict]:
        items: list[dict] = []
        for y in years:
            cats = []
            if lang:
                cats.append(f'incategory:"{y} {lang}-language {"films" if kind == "movies" else "television series"}" {genre or ""}')
            generic = f'"{y} films"' if kind == "movies" else f'"{y} television series debuts"'
            cats.append(f'incategory:{generic} {lang or ""} {genre or ""}')
            cats.append(f'incategory:{generic} {genre or ""}')
            got = self._first_enough([c.strip() for c in cats], kind)
            items += [g for g in got if all(g["title"].lower() != x["title"].lower() for x in items)]
            if len(items) >= PER_ROW:
                break
        return items

    def _by_genre(self, genre: str, kind: str, lang: str | None) -> list[dict]:
        filt = f'hastemplate:"{KIND_TEMPLATE[kind]}"'
        queries = []
        if lang:
            queries.append(f'{filt} incategory:"{lang}-language {KIND_WORD[kind]}s" {genre}')
            queries.append(f'{filt} "{lang}-language" {genre} {KIND_WORD[kind]}')
        queries.append(f'{filt} {genre} {KIND_WORD[kind]}')
        return self._first_enough(queries, kind)
