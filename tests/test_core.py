import unittest
import uuid
from pathlib import Path
import shutil
from unittest.mock import call, patch

from pocketserver.aria2 import Aria2Client
from pocketserver.auth import SessionStore, new_password_record, verify_password
from pocketserver.config import load_config
from pocketserver.media import safe_media_path, scan_media
from pocketserver.metadata import MetadataService, title_from_filename
from pocketserver.requests import MediaRequestStore


class ConfigTests(unittest.TestCase):
    def test_config_is_created_with_secret(self):
        folder = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        try:
            config = load_config(folder)
            self.assertTrue(config["aria2"]["rpc_secret"])
            self.assertEqual("admin", config["auth"]["username"])
            self.assertTrue(verify_password("admin", config["auth"]))
            self.assertTrue(config["auth"]["must_change_password"])
            self.assertTrue((folder / "config.json").exists())
        finally:
            shutil.rmtree(folder)


class ScheduleTests(unittest.TestCase):
    def test_overnight_window(self):
        self.assertTrue(Aria2Client._time_in_window("23:30", "23:00", "06:00"))
        self.assertTrue(Aria2Client._time_in_window("05:59", "23:00", "06:00"))
        self.assertFalse(Aria2Client._time_in_window("12:00", "23:00", "06:00"))

    def test_daytime_and_full_day_windows(self):
        self.assertTrue(Aria2Client._time_in_window("12:00", "08:00", "17:00"))
        self.assertFalse(Aria2Client._time_in_window("19:00", "08:00", "17:00"))
        self.assertTrue(Aria2Client._time_in_window("19:00", "00:00", "00:00"))


class MediaTests(unittest.TestCase):
    def test_scans_video_and_rejects_path_outside_root(self):
        base = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        root = base / "root"
        other = base / "other"
        root.mkdir(parents=True)
        other.mkdir(parents=True)
        try:
            video = root / "movie.mp4"
            video.write_bytes(b"video")
            (root / "notes.txt").write_text("no", encoding="utf-8")
            items = scan_media(root)
            self.assertEqual(["movie.mp4"], [item["filename"] for item in items])
            self.assertEqual(video.resolve(), safe_media_path(str(video), [root]))
            outside = other / "private.mp4"
            outside.write_bytes(b"secret")
            self.assertIsNone(safe_media_path(str(outside), [root]))
        finally:
            shutil.rmtree(base)


class AuthenticationTests(unittest.TestCase):
    def test_passwords_are_salted_and_verified(self):
        first = new_password_record("correct horse battery staple")
        second = new_password_record("correct horse battery staple")
        self.assertNotEqual(first["password_hash"], second["password_hash"])
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong", first))

    def test_other_sessions_are_revoked_after_password_change(self):
        sessions = SessionStore()
        current = sessions.create()
        other = sessions.create()
        sessions.keep_only(current.token)
        self.assertIsNotNone(sessions.get(current.token))
        self.assertIsNone(sessions.get(other.token))


class MediaRequestTests(unittest.TestCase):
    def test_request_lifecycle_is_persisted_and_duplicates_are_blocked(self):
        folder = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        try:
            store = MediaRequestStore(folder)
            item = store.create(
                {
                    "title": "The Matrix",
                    "type": "movie",
                    "year": "1999",
                    "requested_by": "Viewer",
                    "notes": "4K if available",
                }
            )
            self.assertEqual("pending", item["status"])
            self.assertEqual(1, store.pending_count())
            with self.assertRaisesRegex(ValueError, "already been requested"):
                store.create({"title": "the matrix", "type": "movie", "year": "1999"})

            updated = store.set_status(item["id"], "available")
            self.assertEqual("available", updated["status"])
            self.assertEqual(0, store.pending_count())
            self.assertEqual("available", MediaRequestStore(folder).all()[0]["status"])
        finally:
            shutil.rmtree(folder)


class MetadataTests(unittest.TestCase):
    def test_release_filename_is_cleaned_for_lookup(self):
        title, year = title_from_filename("The.Matrix.1999.1080p.BluRay.x265.mkv")
        self.assertEqual("The Matrix", title)
        self.assertEqual("1999", year)

    def test_long_yts_release_name_is_reduced_to_title(self):
        title, year = title_from_filename("Masterplan.2026.720p.WEBRip.x264.AAC-[YTS.GG - YTS.BZ].mp4")
        self.assertEqual("Masterplan", title)
        self.assertEqual("2026", year)

    def test_omdb_response_is_normalized(self):
        value = MetadataService._normalize(
            {
                "Title": "Example",
                "Year": "2025",
                "Genre": "Drama, Mystery",
                "Actors": "Actor One, Actor Two",
                "Plot": "A test plot.",
                "imdbID": "tt1234567",
                "imdbRating": "8.1",
                "Poster": "https://example.com/poster.jpg",
                "Type": "movie",
            }
        )
        self.assertEqual(["Drama", "Mystery"], value["genres"])
        self.assertEqual(["Actor One", "Actor Two"], value["actors"])
        self.assertEqual("tt1234567", value["imdb_id"])

    def test_lookup_retries_without_year_when_omdb_does_not_find_title(self):
        folder = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        service = MetadataService(folder, {"metadata": {"enabled": True, "api_key": "test-key"}})
        try:
            with patch.object(
                service,
                "_request",
                side_effect=[
                    {"Response": "False", "Error": "Movie not found!"},
                    {"Response": "True", "Title": "Masterplan", "Year": "2026", "imdbID": "tt38672588"},
                ],
            ) as request:
                service._fetch_and_store("masterplan|2026", "Masterplan", "2026")
            self.assertEqual([call("Masterplan", "2026"), call("Masterplan", None)], request.call_args_list)
            self.assertEqual("Masterplan", service._cache["masterplan|2026"]["title"])
            self.assertIsNone(service.stats()["last_error"])
        finally:
            service.close()
            shutil.rmtree(folder)

    def test_invalid_api_key_is_reported_without_poisoning_cache(self):
        folder = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        service = MetadataService(folder, {"metadata": {"enabled": True, "api_key": "bad-key"}})
        try:
            with patch.object(service, "_request", return_value={"Response": "False", "Error": "Invalid API key!"}):
                service._fetch_and_store("example|2025", "Example", "2025")
            self.assertNotIn("example|2025", service._cache)
            self.assertEqual("Invalid API key!", service.stats()["last_error"])
        finally:
            service.close()
            shutil.rmtree(folder)


if __name__ == "__main__":
    unittest.main()
