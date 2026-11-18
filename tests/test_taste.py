"""Likes and the "For you" rows (buzz/taste.py), with Wikipedia stubbed out."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import app
from buzz import tv
from buzz.engine import Engine
from buzz.taste import Taste, _genre_words
from buzz.tvstate import TvState
from tests.test_tv import StubProvider


class FakeSmart:
    """Answers like SmartSearch: fixed 'articles' per kind of query, unique ones for the rest."""
    MORELIKE = ["Deewaar", "Zanjeer", "Amjad Khan", "Masala film", "Don", "Trishul"]
    FRESH = ["Sikandar", "Jaat", "War 2", "Fateh", "Deva"]
    DESC = {"Amjad Khan": "Indian actor (1940–1992)", "Masala film": "film genre", "Amitabh Bachchan": "Indian actor"}

    def __init__(self):
        self.queries = []

    def _search(self, text, limit=8, wiki="en"):
        self.queries.append(text)
        if text.startswith("morelike:"):
            return list(self.MORELIKE), None
        if 'incategory:"20' in text:
            return list(self.FRESH), None
        if "Amitabh Bachchan" in text:
            return ["Pink", "Paa", "Badla", "Amitabh Bachchan", "Laawaris"], None
        return [f"{text.split()[-1].strip(chr(34))} pick {i}" for i in range(6)], None

    def describe(self, titles, thumb=320, wiki="en"):
        year = 2025 if 'incategory:"20' in self.queries[-1] else 1975
        return [{"title": t, "wiki_title": t, "wiki": wiki, "year": year, "qid": "Q1",
                 "description": self.DESC.get(t, "Indian film"), "thumb": None} for t in titles]

    @staticmethod
    def is_kind(description, category, wiki="en"):
        return "film" in description


class FakeDetails:
    def __init__(self):
        self.asked = []

    def register_image(self, url):
        return None

    def for_result(self, r, use_wiki=True):
        self.asked.append(r.title)
        return {"title": r.title, "year": 1975, "matched": True, "genres": ["action film", "drama", "Hindi-language film"],
                "cast": ["Amitabh Bachchan", "Dharmendra"], "facts": [{"label": "Directed by", "values": ["Ramesh Sippy"]}],
                "language": "Hindi, English", "country": "India", "poster": None,
                "links": [{"label": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Sholay"},
                          {"label": "Wikidata", "url": "https://www.wikidata.org/wiki/Q949228"}]}


class TasteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = TvState(Path(self.tmp.name) / "tv_state.json")
        self.smart, self.details = FakeSmart(), FakeDetails()
        self.taste = Taste(self.st, self.smart, self.details)

    def tearDown(self):
        self.tmp.cleanup()

    def test_genre_words(self):
        self.assertEqual(_genre_words(["action film", "Hindi-language film", "crime thriller", "television drama"]),
                         ["action", "crime thriller", "drama"])

    def test_profile_from_details(self):
        like = self.st.like_add({"title": "Sholay", "category": "movies", "year": 1975})
        p = self.taste.profile_for(like)
        self.assertEqual(p["wiki_title"], "Sholay")
        self.assertEqual(p["qid"], "Q949228")
        self.assertEqual(p["genres"], ["action", "drama"])
        self.assertEqual(p["people"][:2], ["Ramesh Sippy", "Amitabh Bachchan"])
        self.assertEqual(p["language"], "Hindi")

    def test_rows_skip_people_genres_and_what_you_saw(self):
        like = self.st.like_add({"title": "Sholay", "category": "movies", "year": 1975})
        self.st.set_profile(like["id"], self.taste.profile_for(like))
        self.st.report({"key": "ia:x:Don", "pos": 5900, "dur": 6000, "title": "Don"})   # watched to the end
        rows = self.taste.build()
        labels = [r["label"] for r in rows]
        self.assertEqual(labels[0], "Because you liked Sholay")
        similar = [i["title"] for i in rows[0]["items"]]
        self.assertIn("Deewaar", similar)
        self.assertNotIn("Amjad Khan", similar)         # an actor, not a film
        self.assertNotIn("Masala film", similar)        # a genre article
        self.assertNotIn("Don", similar)                # already watched
        self.assertNotIn("Sholay", similar)             # the like itself
        self.assertTrue(any(l.startswith("More with ") for l in labels))
        self.assertTrue(any(l.startswith("New action movies in Hindi") for l in labels), labels)
        self.assertTrue(any(l.startswith("Something different") for l in labels))
        fresh = next(r for r in rows if r["label"].startswith("New action"))
        self.assertTrue(all(i["year"] == 2025 for i in fresh["items"]))
        self.assertTrue(all(i["reason"] for r in rows for i in r["items"]))
        titles = [i["title"] for r in rows for i in r["items"]]
        self.assertEqual(len(titles), len(set(titles)))  # no title in two rows

    def test_for_you_builds_in_the_background_and_likes_change_it(self):
        self.assertEqual(self.taste.for_you(), {"rows": [], "likes": 0, "building": False, "built": 0.0})
        self.taste.like({"title": "Sholay", "category": "movies"})
        for _ in range(100):
            d = self.taste.for_you()
            if d["rows"] and not d["building"]:
                break
            time.sleep(0.05)
        self.assertTrue(d["rows"])
        self.assertEqual(d["likes"], 1)
        self.assertEqual(self.details.asked, ["Sholay"])             # the like was profiled once
        lid = self.st.likes()[0]["id"]
        self.assertTrue(self.taste.unlike(lid))
        self.assertEqual(self.taste.for_you()["rows"], [])              # nothing liked: nothing to show
        self.assertFalse(self.taste.unlike(lid))

    def test_smart_search_off(self):
        t = Taste(self.st, None, self.details)
        t.like({"title": "Sholay", "category": "movies"})
        self.assertTrue(t.for_you()["off"])
        self.assertEqual(self.st.likes()[0]["profile"], None)


class TestHandler(app.Handler):
    @property
    def remote(self):
        return self.headers.get("X-Test-Remote") == "1"

    def log_message(self, *a):
        pass


class LikeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = app.Server(("127.0.0.1", 0), TestHandler)
        cls.port = cls.server.server_address[1]
        cfg = {**app.DEFAULTS, "tv": {"enabled": True, "pin": "654321", "tokens": [], "autostart": False}}
        TestHandler.engine = Engine([StubProvider()])
        TestHandler.cfg = cfg
        TestHandler.port = cls.port
        TestHandler.lan_bound = True
        TestHandler.allowed_hosts = {f"127.0.0.1:{cls.port}", f"localhost:{cls.port}"}
        TestHandler.pairing = tv.Pairing(cfg["tv"], lambda: None)
        TestHandler.tvstate = TvState(Path(cls.tmp.name) / "state.json")
        TestHandler.taste = Taste(TestHandler.tvstate, FakeSmart(), FakeDetails())
        TestHandler.signer = tv.Signer("secret")
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": f"192.168.1.20:{self.port}", "X-Test-Remote": "1"}
        if cookie:
            headers["Cookie"] = cookie
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers.update({"Content-Type": "application/json", "X-BuzzTorrent": "1"})
        c.request(method, path, body=data, headers=headers)
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, json.loads(raw), r.getheader("Set-Cookie")

    def test_like_toggle_and_for_you_from_a_paired_tv(self):
        self.assertEqual(self.req("GET", "/api/tv/likes")[0], 401)                  # pairing first
        status, _, cookie = self.req("POST", "/api/tv/pair", {"pin": "654321"})
        self.assertEqual(status, 200)
        cookie = cookie.split(";")[0]
        status, d, _ = self.req("POST", "/api/tv/like", {"title": "Sholay.1975.1080p.BluRay.x264", "category": "movies"}, cookie)
        self.assertEqual((status, d["liked"], d["item"]["title"], d["item"]["year"]), (200, True, "Sholay", 1975))
        status, d, _ = self.req("GET", "/api/tv/likes", cookie=cookie)
        self.assertEqual([l["title"] for l in d["items"]], ["Sholay"])
        # a native player toggles without knowing the state
        status, d, _ = self.req("POST", "/api/tv/like", {"action": "toggle", "title": "Sholay", "category": "movies"}, cookie)
        self.assertEqual((status, d["liked"]), (200, False))
        status, d, _ = self.req("POST", "/api/tv/like", {"action": "toggle", "title": "Sholay", "category": "movies"}, cookie)
        self.assertEqual((status, d["liked"]), (200, True))
        # private titles are never remembered
        status, d, _ = self.req("POST", "/api/tv/like", {"title": "Something", "category": "adult"}, cookie)
        self.assertEqual(status, 400)
        for _ in range(100):
            status, d, _ = self.req("GET", "/api/tv/foryou", cookie=cookie)
            if d["rows"] and not d["building"]:
                break
            time.sleep(0.05)
        self.assertEqual((status, d["likes"]), (200, 1))
        self.assertEqual(d["rows"][0]["label"], "Because you liked Sholay")
        # the signed link handed to native players works without the pairing cookie
        signed = TestHandler.signer.sign("/api/tv/like")
        status, d, _ = self.req("POST", signed, {"action": "toggle", "title": "Sholay", "category": "movies"})
        self.assertEqual((status, d["liked"]), (200, False))
        lid = self.req("GET", "/api/tv/likes", cookie=cookie)[1]
        self.assertEqual(lid["items"], [])


if __name__ == "__main__":
    unittest.main()
