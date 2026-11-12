from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from icalendar import Alarm, Calendar, Event

import main


def calendar_bytes(*uids, summary="Wm wyk sala 1", date="2026-11-12"):
    calendar = Calendar()
    calendar.add("VERSION", "2.0")
    for uid in uids:
        event = Event()
        event.add("UID", uid)
        event.add("SUMMARY", summary)
        event.add("DTSTART", datetime.fromisoformat(date + "T08:00:00+00:00"))
        event.add("DTEND", datetime.fromisoformat(date + "T09:00:00+00:00"))
        calendar.add_component(event)
    return calendar.to_ical()


class CalendarValidationTests(unittest.TestCase):
    def test_rejects_invalid_documents(self):
        valid = calendar_bytes("one")
        invalid = [
            b"",
            b"<html>Maintenance</html>",
            valid[:-20],
            valid + valid,
            valid.replace(b"END:VEVENT", b"END:VTODO"),
            valid.replace(b"VERSION:2.0", b"VERSION:1.0"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload[:50]), self.assertRaises(ValueError):
                main.parse_calendar_bytes(payload)

    def test_rejects_invalid_events(self):
        valid = calendar_bytes("one")
        invalid = [
            calendar_bytes("one", "one"),
            calendar_bytes("bad uid"),
            valid.replace(b"UID:one\r\n", b""),
            valid.replace(b"DTSTART:20261112T080000Z", b"DTSTART:garbage"),
            valid.replace(b"DTEND:20261112T090000Z", b"DTEND:20261112T070000Z"),
            valid.replace(b"SUMMARY:", b"RRULE:FREQ=DAILY\r\nSUMMARY:"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload[:80]), self.assertRaises(
                (ValueError, KeyError)
            ):
                main.parse_calendar_bytes(payload)

    def test_rejects_excessive_size_and_nesting(self):
        with patch.object(main, "MAX_CALENDAR_BYTES", 10), self.assertRaises(
            ValueError
        ):
            main.parse_calendar_bytes(calendar_bytes("one"))
        payload = (
            b"BEGIN:VCALENDAR\r\n"
            + b"BEGIN:VEVENT\r\n" * 10
            + b"END:VEVENT\r\n" * 10
            + b"END:VCALENDAR\r\n"
        )
        with self.assertRaises(ValueError):
            main.parse_calendar_bytes(payload)

    def test_valid_empty_calendar_is_not_a_download_failure(self):
        self.assertEqual(main.parse_calendar_bytes(calendar_bytes()).walk("VEVENT"), [])

    def test_nested_events_are_rejected(self):
        calendar = Calendar.from_ical(calendar_bytes("one"))
        nested = Calendar.from_ical(calendar_bytes("two")).subcomponents[0]
        calendar.subcomponents[0].add_component(nested)
        with self.assertRaises(ValueError):
            main.parse_calendar_bytes(calendar.to_ical())

    def test_bom_and_folded_polish_text(self):
        payload = b"\xef\xbb\xbf" + calendar_bytes(
            "one", summary="Wm wyk " + "ćwiczenia " * 30
        )
        parsed = main.parse_calendar_bytes(payload)
        self.assertIn("ćwiczenia", str(parsed.walk("VEVENT")[0]["SUMMARY"]))


class ProcessingTests(unittest.TestCase):
    def process(self, payload, **kwargs):
        options = dict(
            legend={"Wm": "Wyroby medyczne"},
            subject_groups={},
            optional_subjects_list=[],
            optional_selected=(),
        )
        options.update(kwargs)
        return Calendar.from_ical(
            main.process_calendar_bytes_for_group_and_optionals(payload, **options)
        )

    def test_source_instructions_are_not_republished(self):
        calendar = Calendar.from_ical(calendar_bytes("one"))
        source = calendar.subcomponents[0]
        source.add("URL", "https://example.invalid/untrusted")
        source.add("ATTACH", "https://example.invalid/attachment")
        source.add("ATTENDEE", "mailto:untrusted@example.invalid")
        source.add("ORGANIZER", "mailto:untrusted@example.invalid")
        alarm = Alarm()
        alarm.add("ACTION", "DISPLAY")
        alarm.add("DESCRIPTION", "untrusted")
        source.add_component(alarm)
        event = self.process(calendar.to_ical()).walk("VEVENT")[0]
        self.assertEqual(str(event["UID"]), "one")
        self.assertEqual(event.decoded("DTSTART"), source.decoded("DTSTART"))
        self.assertEqual(str(event["SUMMARY"]), "Wyroby medyczne")
        self.assertEqual(event.subcomponents, [])
        self.assertFalse({"URL", "ATTACH", "ATTENDEE", "ORGANIZER"} & set(event))

    def test_matching_and_nonmatching_groups(self):
        for selected, expected in [("A", 1), ("B", 0), (None, 0)]:
            with self.subTest(selected=selected):
                result = self.process(
                    calendar_bytes("one", summary="WmpA ćw sala 1"),
                    subject_groups={"Wm": selected},
                )
                self.assertEqual(len(result.walk("VEVENT")), expected)

    def test_optionals_are_filtered_after_suffix_removal(self):
        payload = calendar_bytes("one", summary="WmpB ćw sala 1")
        for selected, count in [((), 0), (("Wm",), 1)]:
            result = self.process(
                payload,
                subject_groups={"Wm": "B"},
                optional_subjects_list=["Wm"],
                optional_selected=selected,
            )
            self.assertEqual(len(result.walk("VEVENT")), count)

    def test_shared_awf_uid_is_resolved_by_subject_group_filtering(self):
        snapshot = Calendar.from_ical(
            calendar_bytes("shared", summary="WmpA ćw room A")
        )
        snapshot.add_component(
            Calendar.from_ical(
                calendar_bytes("shared", summary="WmpB ćw room B")
            ).subcomponents[0]
        )
        for group in ["A", "B"]:
            result = self.process(snapshot.to_ical(), subject_groups={"Wm": group})
            events = result.walk("VEVENT")
            self.assertEqual(len(events), 1)
            self.assertEqual(str(events[0]["UID"]), "shared")
            self.assertEqual(str(events[0]["DESCRIPTION"]), f"ćw room {group}")

    def test_optional_selection_formats(self):
        for config, expected in [
            (None, ("Wm",)),
            ([], ()),
            (["Wm"], ("Wm",)),
            ({"Wm": True, "Other": False}, ("Wm",)),
        ]:
            self.assertEqual(
                main.resolve_optional_selection_for_calendar(["Wm"], config), expected
            )

    def test_longest_prefix_and_original_remainder(self):
        self.assertEqual(
            main._split_summary("Umwzf  Gr 1 B   ćw sala 1", ["Umwzf", "Umwzf Gr 1 B"]),
            ("Umwzf Gr 1 B", "ćw sala 1"),
        )

    def test_utc_timestamps_on_both_sides_of_dst(self):
        for date in ["2026-10-24", "2026-10-26"]:
            source = calendar_bytes("one", date=date)
            event = self.process(source).walk("VEVENT")[0]
            self.assertEqual(event.decoded("DTSTART").utcoffset(), timedelta(0))
            self.assertIn(
                (date.replace("-", "") + "T080000Z").encode(), event.to_ical()
            )


class FetchAndPublicationTests(unittest.TestCase):
    def test_download_limits_and_redirects(self):
        for status, chunks, valid in [
            (200, [b"abc"], True),
            (302, [b"abc"], False),
            (200, [b"abc", b"def"], False),
        ]:
            response = MagicMock(status_code=status)
            response.iter_content.return_value = chunks
            request = MagicMock()
            request.return_value.__enter__.return_value = response
            with patch.object(main.requests, "get", request), patch.object(
                main, "MAX_CALENDAR_BYTES", 5
            ):
                if valid:
                    self.assertEqual(main.fetch_awf_calendar(), b"abc")
                else:
                    with self.assertRaises(ValueError):
                        main.fetch_awf_calendar()
                self.assertFalse(request.call_args.kwargs["allow_redirects"])
                self.assertTrue(request.call_args.kwargs["stream"])
                self.assertEqual(request.call_args.kwargs["timeout"], main.HTTP_TIMEOUT)

    def generate(self, snapshot):
        with patch.object(
            main, "fetch_awf_calendar", return_value=snapshot
        ), redirect_stdout(StringIO()):
            return main.get_full_semester_calendar_bytes(
                subject_groups={},
                legend={"Wm": "Test"},
                optional_subjects_list=[],
                optional_selected=(),
                start_of_semester=datetime(2026, 11, 9),
                end_of_semester=datetime(2026, 11, 22),
            )

    def test_invalid_snapshot_is_not_published_as_an_empty_calendar(self):
        with self.assertRaises(ValueError):
            self.generate(b"<html>No classes or no permission</html>")

    def test_empty_weeks_do_not_require_separate_downloads(self):
        self.assertEqual(
            len(
                Calendar.from_ical(self.generate(calendar_bytes("one"))).walk("VEVENT")
            ),
            1,
        )

    def test_duplicate_uids_after_filtering_block_publication(self):
        with self.assertRaises(ValueError):
            self.generate(calendar_bytes("one", "one"))

    def test_snapshot_is_filtered_to_complete_boundary_weeks(self):
        snapshot = Calendar.from_ical(calendar_bytes("before", date="2026-11-08"))
        for uid, date in [
            ("boundary", "2026-11-09"),
            ("last", "2026-11-22"),
            ("after", "2026-11-23"),
        ]:
            snapshot.add_component(
                Calendar.from_ical(calendar_bytes(uid, date=date)).subcomponents[0]
            )
        result = main.get_full_semester_calendar_bytes(
            subject_groups={},
            legend={"Wm": "Test"},
            optional_subjects_list=[],
            optional_selected=(),
            start_of_semester=datetime(2026, 11, 12),
            end_of_semester=datetime(2026, 11, 20),
            calendar_bytes=snapshot.to_ical(),
        )
        self.assertEqual(
            {str(event["UID"]) for event in Calendar.from_ical(result).walk("VEVENT")},
            {"boundary", "last"},
        )

    def test_snapshot_failure_leaves_existing_output_unchanged(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "example.ics"
            original = calendar_bytes("old")
            path.write_bytes(original)
            with patch.object(
                main, "ensure_output_dir", return_value=Path(directory)
            ), patch.object(
                main, "fetch_awf_calendar", side_effect=RuntimeError("network failure")
            ):
                with self.assertRaises(RuntimeError):
                    main.main()
            self.assertEqual(path.read_bytes(), original)

    def test_large_removals_are_blocked_but_small_removals_work(self):
        previous = calendar_bytes("a", "b", "c", "d")
        main.validate_calendar_removals(previous, calendar_bytes("a", "b", "c"))
        with self.assertRaisesRegex(ValueError, "large event removal"):
            main.validate_calendar_removals(previous, calendar_bytes("a", "b"))

    def test_failure_in_later_calendar_leaves_all_outputs_unchanged(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "first.ics"
            original = calendar_bytes("old")
            path.write_bytes(original)
            with patch.object(
                main, "ensure_output_dir", return_value=Path(directory)
            ), patch.object(
                main, "fetch_awf_calendar", return_value=calendar_bytes("source")
            ), patch.object(
                main,
                "load_yaml",
                return_value=({}, [], [{"name": "first"}, {"name": "second"}]),
            ), patch.object(
                main,
                "get_full_semester_calendar_bytes",
                side_effect=[calendar_bytes("new"), RuntimeError("invalid calendar")],
            ), redirect_stdout(
                StringIO()
            ):
                with self.assertRaises(RuntimeError):
                    main.main(allow_large_removals=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((Path(directory) / "second.ics").exists())

    def test_all_empty_output_retains_existing_feed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "example.ics"
            path.write_bytes(calendar_bytes("old"))
            with patch.object(
                main, "ensure_output_dir", return_value=Path(directory)
            ), patch.object(
                main, "load_yaml", return_value=({}, [], [{"name": "example"}])
            ), patch.object(
                main, "fetch_awf_calendar", return_value=calendar_bytes()
            ), patch.object(
                main, "get_full_semester_calendar_bytes", return_value=None
            ), redirect_stdout(
                StringIO()
            ):
                main.main()
            self.assertEqual(
                len(Calendar.from_ical(path.read_bytes()).walk("VEVENT")), 1
            )

    def test_main_fetches_one_snapshot_for_all_calendars(self):
        with TemporaryDirectory() as directory, patch.object(
            main, "ensure_output_dir", return_value=Path(directory)
        ), patch.object(
            main, "fetch_awf_calendar", return_value=calendar_bytes("shared")
        ) as fetch, redirect_stdout(
            StringIO()
        ):
            main.main()
            fetch.assert_called_once_with()
            _, _, configurations = main.load_yaml()
            self.assertEqual(
                len(list(Path(directory).glob("*.ics"))), len(configurations)
            )

    def test_filenames_cannot_escape_output_directory(self):
        for name in ["../outside", "/absolute", "a/b", "a\\b", "", ".hidden"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                main.make_filename_from_calendar_name(name)
        _, _, calendars = main.load_yaml()
        for calendar in calendars:
            self.assertEqual(
                main.make_filename_from_calendar_name(calendar["name"]),
                calendar["name"] + ".ics",
            )

    def test_both_yaml_calendar_formats(self):
        for calendars in ["  - name: example\n", "  example: {}\n"]:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "legend.yaml"
                path.write_text("calendars:\n" + calendars)
                self.assertEqual(main.load_yaml(str(path))[2], [{"name": "example"}])


if __name__ == "__main__":
    unittest.main()
