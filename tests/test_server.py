"""Credential- and network-free adapter regression tests."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from garmin_mcp import server


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")).start()
        patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")).start()
        patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")).start()


class ClientInitializationTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        patch.object(server, "_garmin_client", None).start()
        patch.object(server, "logger").start()
        self.session = SimpleNamespace(profile={"displayName": "synthetic-user"})
        self.garth = SimpleNamespace(client=self.session, resume=Mock(), login=Mock(), save=Mock())
        patch.object(server, "garth", self.garth).start()
        patch.dict(server.os.environ, {}, clear=True).start()

    def test_resumed_client_initializes_display_name_and_is_cached(self):
        client = server.get_garmin_client()
        self.assertEqual(client.display_name, "synthetic-user")
        self.assertIs(client.garth, self.session)
        self.assertIs(server.get_garmin_client(), client)
        self.garth.resume.assert_called_once()
        self.garth.login.assert_not_called()
        self.garth.save.assert_not_called()

    def test_credential_login_initializes_display_name_and_saves_session(self):
        self.garth.resume.side_effect = OSError("Synthetic missing session")
        patch.dict(server.os.environ, {"GARMIN_EMAIL": "synthetic@example.invalid", "GARMIN_PASSWORD": "fake"}).start()
        client = server.get_garmin_client()
        self.assertEqual(client.display_name, "synthetic-user")
        self.assertIs(client.garth, self.session)
        self.garth.login.assert_called_once()
        self.garth.save.assert_called_once()

    def test_cached_client_missing_display_name_is_initialized(self):
        client = SimpleNamespace(garth=self.session, display_name=None)
        server._garmin_client = client
        self.assertIs(server.get_garmin_client(), client)
        self.assertEqual(client.display_name, "synthetic-user")
        self.garth.resume.assert_not_called()

    def test_initialized_real_sdk_methods_use_profile_display_name_in_urls(self):
        client = server.get_garmin_client()
        with patch.object(client, "connectapi", return_value={"totalSteps": 0}) as transport:
            client.get_user_summary("2026-10-10")
            client.get_rhr_day("2026-10-10")
        self.assertEqual(len(transport.call_args_list), 2)
        for call in transport.call_args_list:
            self.assertTrue(call.args[0].endswith("/synthetic-user"))
            self.assertNotIn("/None", call.args[0])

    def test_failed_resume_without_credentials_preserves_auth_error(self):
        self.garth.resume.side_effect = OSError("Synthetic missing session")
        with self.assertRaisesRegex(ValueError, "No saved session found"):
            server.get_garmin_client()
        self.assertIsNone(server._garmin_client)
        self.garth.login.assert_not_called()
        self.garth.save.assert_not_called()

    def test_cached_initialized_client_does_not_fetch_profile_again(self):
        client = SimpleNamespace(display_name="synthetic-user")
        server._garmin_client = client
        self.assertIs(server.get_garmin_client(), client)
        self.garth.resume.assert_not_called()


class SyntheticClient:
    """Only local payloads; no SDK transport or saved sessions."""
    def __init__(self, **payloads):
        self.payloads = payloads
        self.garth = SimpleNamespace(profile={"displayName": "synthetic-user"})

    def get_user_summary(self, day):
        return self.payloads.get("user_summary", {})

    def get_sleep_data(self, day):
        return self.payloads.get("sleep")

    def get_hrv_data(self, day):
        return self.payloads.get("hrv")

    def get_body_battery(self, day):
        return self.payloads.get("body_battery")

    def get_training_readiness(self, day):
        return self.payloads.get("readiness")

    def get_rhr_day(self, day):
        return self.payloads.get("rhr")

    def get_activities_by_date(self, start, end):
        return self.payloads.get("activities")


class DailySummaryTests(OfflineTestCase):
    day = "2026-10-06"

    def summary(self, **payloads):
        return asyncio.run(server.get_daily_summary(SyntheticClient(**payloads), self.day))

    def readiness(self, score, context="AFTER_WAKEUP_RESET", primary=True,
                  timestamp: str | None = "2026-10-06T07:00:00.000", day=None):
        return {"calendarDate": day or self.day, "score": score,
                "inputContext": context, "primaryActivityTracker": primary,
                "timestamp": timestamp}

    def test_readiness_prefers_primary_tracker_morning_in_shuffled_list(self):
        morning = self.readiness(94)
        later_morning = self.readiness(95, timestamp="2026-10-06T08:00:00.000")
        exercise = self.readiness(86, "AFTER_EXERCISE", timestamp="2026-10-06T18:00:00.000")
        secondary = self.readiness(22, primary=False, timestamp="2026-10-06T09:00:00.000")
        wrong_day = self.readiness(99, day="2026-10-10")
        records = [exercise, morning, secondary, wrong_day, later_morning]
        for items in (records, records[::-1], records[2:] + records[:2]):
            with self.subTest(items=items):
                result = self.summary(readiness=items)
                self.assertEqual(result["training_readiness"], 95)
                self.assertEqual(result.get("training_readiness_context"), "AFTER_WAKEUP_RESET")
                self.assertEqual(result.get("training_readiness_timestamp"), later_morning["timestamp"])
                self.assertEqual(result.get("training_readiness_selection"), "primary_tracker_morning")

    def test_readiness_latest_fallback_exposes_post_exercise_provenance(self):
        records = [self.readiness(40, "OTHER", timestamp="2026-10-06T10:00:00.000"),
                   self.readiness(86, "AFTER_EXERCISE", timestamp="2026-10-06T18:00:00.000")]
        result = self.summary(readiness=records[::-1])
        self.assertEqual(result["training_readiness"], 86)
        self.assertEqual(result.get("training_readiness_context"), "AFTER_EXERCISE")
        self.assertEqual(result.get("training_readiness_timestamp"), records[1]["timestamp"])
        self.assertEqual(result.get("training_readiness_selection"), "latest")

    def test_readiness_legacy_dict_retains_zero(self):
        result = self.summary(readiness={"score": 0})
        self.assertEqual(result["training_readiness"], 0)
        self.assertEqual(result.get("training_readiness_selection"), "legacy")

    def test_readiness_absent_invalid_or_wrong_day_remains_null(self):
        cases = [None, [], {}, {"score": 94, "calendarDate": "2026-10-05"},
                 {"score": True}, {"score": -1}, {"score": 101}, {"score": "94"},
                 [None, "bad", {}, self.readiness(None), self.readiness(float("nan")),
                  self.readiness(99, day="2026-10-05")],
                 [self.readiness(86, "AFTER_EXERCISE", timestamp="invalid")]]
        for payload in cases:
            with self.subTest(payload=payload):
                result = self.summary(readiness=payload)
                self.assertIsNone(result["training_readiness"])
                self.assertNotIn("training_readiness_selection", result)

    def test_readiness_malformed_morning_timestamp_does_not_override_valid_fallback(self):
        records = [self.readiness(99, timestamp="invalid"),
                   self.readiness(86, "AFTER_EXERCISE", timestamp="2026-10-06T18:00:00Z")]
        result = self.summary(readiness=records)
        self.assertEqual(result["training_readiness"], 86)
        self.assertEqual(result.get("training_readiness_selection"), "latest")

    def test_readiness_morning_without_timestamp_retains_zero(self):
        result = self.summary(readiness=[self.readiness(0, timestamp=None)])
        self.assertEqual(result["training_readiness"], 0)
        self.assertEqual(result.get("training_readiness_selection"), "primary_tracker_morning")
        self.assertIsNone(result.get("training_readiness_timestamp"))

    def test_readiness_latest_compares_instants_not_iso_string_order(self):
        records = [self.readiness(50, "OTHER", timestamp="2026-10-06T18:00:00+05:00"),
                   self.readiness(86, "AFTER_EXERCISE", timestamp="2026-10-06T14:00:00Z")]
        result = self.summary(readiness=records)
        self.assertEqual(result["training_readiness"], 86)

    def battery(self, values, day=None, descriptors=None):
        return {"date": day or self.day,
                "bodyBatteryValueDescriptorDTOList": descriptors if descriptors is not None else [
                    {"bodyBatteryValueDescriptorKey": "timestamp", "bodyBatteryValueDescriptorIndex": 0},
                    {"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": 1}],
                "bodyBatteryValuesArray": values}

    def test_body_battery_uses_matching_day_series_including_zero(self):
        payload = [None, "bad", self.battery([[1000, 99]], day="2026-10-05"),
                   self.battery([[1000, 75], [2000, 30]]),
                   self.battery([[3000, 0], [4000, 50]])]
        for items in (payload, payload[::-1]):
            with self.subTest(items=items):
                result = self.summary(body_battery=items)
                self.assertEqual(result["body_battery_high"], 75)
                self.assertEqual(result["body_battery_low"], 0)

    def test_body_battery_uses_descriptor_indices_not_row_position(self):
        descriptors = [{"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": 0},
                       {"bodyBatteryValueDescriptorKey": "timestamp", "bodyBatteryValueDescriptorIndex": 2}]
        result = self.summary(body_battery=[self.battery([[93, 999, 1000], [19, 888, 2000]],
                                                       descriptors=descriptors)])
        self.assertEqual(result["body_battery_high"], 93)
        self.assertEqual(result["body_battery_low"], 19)

    def test_body_battery_skips_malformed_samples_without_losing_valid_ones(self):
        rows = [None, {}, [], [1000], [None, 100], ["time", 100], [1000, "99"],
                [1000, True], [1000, -1], [1000, 101], [1000, float("nan")],
                [float("inf"), 100], [1000, None], [1000, 75], [2000, 30]]
        result = self.summary(body_battery=[self.battery(rows)])
        self.assertEqual(result["body_battery_high"], 75)
        self.assertEqual(result["body_battery_low"], 30)

    def test_body_battery_absent_invalid_descriptors_or_wrong_day_remains_null(self):
        invalid_descriptors = [[], [None], [{"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": -1}],
                               [{"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": True}],
                               [{"bodyBatteryValueDescriptorKey": "timestamp", "bodyBatteryValueDescriptorIndex": 0},
                                {"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": 0}],
                               [{"bodyBatteryValueDescriptorKey": "timestamp", "bodyBatteryValueDescriptorIndex": 0},
                                {"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": 1},
                                {"bodyBatteryValueDescriptorKey": "bodyBatteryLevel", "bodyBatteryValueDescriptorIndex": 2}]]
        cases = [None, [], {}, [self.battery([], day=self.day)],
                 [self.battery([[1000, 100]], day="2026-10-05")],
                 [{"date": self.day, "bodyBatteryValuesArray": [[1000, 100]]}],
                 [self.battery([[1000, None]])]]
        cases.extend([[self.battery([[1000, 100]], descriptors=d)] for d in invalid_descriptors])
        for payload in cases:
            with self.subTest(payload=payload):
                result = self.summary(body_battery=payload)
                self.assertIsNone(result["body_battery_high"])
                self.assertIsNone(result["body_battery_low"])

    def rhr(self, records):
        return {"allMetrics": {"metricsMap": {"WELLNESS_RESTING_HEART_RATE": records}}}

    def test_rhr_extracts_matching_day_numeric_scalar_from_metrics_map(self):
        records = [None, "bad", {}, {"calendarDate": "2026-10-05", "value": 90},
                   {"calendarDate": self.day, "value": "90"},
                   {"calendarDate": self.day, "value": 63.0}]
        for items in (records, records[::-1]):
            with self.subTest(items=items):
                result = self.summary(rhr=self.rhr(items), user_summary={"restingHeartRate": 64})
                self.assertEqual(result["resting_heart_rate"], 63.0)
                self.assertIsInstance(result["resting_heart_rate"], (int, float))

    def test_rhr_falls_back_to_user_summary_when_endpoint_is_absent_or_invalid(self):
        cases = [None, {}, {"allMetrics": None}, {"allMetrics": []},
                 self.rhr(None), self.rhr([]), self.rhr([{"calendarDate": "2026-10-05", "value": 90}]),
                 self.rhr([{"calendarDate": self.day, "value": True}])]
        for payload in cases:
            with self.subTest(payload=payload):
                result = self.summary(rhr=payload, user_summary={"restingHeartRate": 63, "totalSteps": 0,
                                                              "averageStressLevel": 0})
                self.assertEqual(result["resting_heart_rate"], 63)
                self.assertEqual(result["steps"], 0)
                self.assertEqual(result["avg_stress"], 0)

    def test_rhr_fallback_survives_endpoint_exception(self):
        client = SyntheticClient(user_summary={"restingHeartRate": 63})
        client.get_rhr_day = Mock(side_effect=RuntimeError("Synthetic unavailable endpoint"))
        with self.assertLogs(server.logger, level="WARNING"):
            result = asyncio.run(server.get_daily_summary(client, self.day))
        self.assertEqual(result["resting_heart_rate"], 63)

    def test_rhr_absent_malformed_or_wrong_day_remains_null(self):
        for value in (None, 0, -1, True, "63", float("nan"), float("inf"), {}):
            with self.subTest(value=value):
                result = self.summary(rhr=self.rhr([{"calendarDate": self.day, "value": value}]),
                                      user_summary={"restingHeartRate": value})
                self.assertIsNone(result["resting_heart_rate"])
        result = self.summary(rhr=self.rhr([{"calendarDate": "2026-10-05", "value": 63}]),
                              user_summary={"calendarDate": "2026-10-05", "restingHeartRate": 65})
        self.assertIsNone(result["resting_heart_rate"])

    def test_sleep_hrv_steps_stress_and_fixed_metrics_survive_combined_payload(self):
        result = self.summary(
            sleep={"dailySleepDTO": {"sleepScores": {"overall": {"value": 88}}}},
            hrv={"hrvSummary": {"lastNightAvg": 48, "status": "BALANCED"}},
            user_summary={"totalSteps": 1234, "averageStressLevel": 20, "restingHeartRate": 63},
            readiness=[self.readiness(86, "AFTER_EXERCISE", timestamp="2026-10-06T18:00:00.000"),
                       self.readiness(94)], body_battery=[self.battery([[1000, 93], [2000, 19]])])
        expected = {"date": self.day, "sleep_score": 88, "hrv_value": 48, "hrv_status": "BALANCED",
                    "steps": 1234, "avg_stress": 20, "resting_heart_rate": 63,
                    "training_readiness": 94, "body_battery_high": 93, "body_battery_low": 19}
        for key, value in expected.items():
            self.assertEqual(result[key], value)

    def test_empty_payload_retains_all_core_fields_as_null(self):
        result = self.summary(user_summary=None)
        self.assertEqual(result, {"date": self.day, "sleep_score": None, "training_readiness": None,
                                  "body_battery_high": None, "body_battery_low": None,
                                  "hrv_status": None, "hrv_value": None, "resting_heart_rate": None,
                                  "avg_stress": None, "steps": None})

    def test_range_reuses_date_safe_daily_summary(self):
        client = SyntheticClient(readiness=[self.readiness(94)],
                                 body_battery=[self.battery([[1000, 93], [2000, 19]])])
        result = asyncio.run(server.get_summary_range(client, self.day, "2026-10-07"))
        self.assertEqual(result["days"], 2)
        self.assertEqual(result["summaries"][0]["training_readiness"], 94)
        self.assertIsNone(result["summaries"][1]["training_readiness"])
        self.assertIsNone(result["summaries"][1]["body_battery_high"])

    def test_mcp_names_and_daily_json_contract_remain_compatible(self):
        tools = asyncio.run(server.list_tools())
        self.assertEqual([t.name for t in tools], ["get_daily_summary", "get_summary_range",
                                                  "get_activities", "get_sleep_details"])
        client = SyntheticClient(readiness=[self.readiness(94)])
        with patch.object(server, "get_garmin_client", return_value=client):
            contents = asyncio.run(server.call_tool("get_daily_summary", {"date": self.day}))
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0].type, "text")
        result = json.loads(contents[0].text)
        self.assertEqual(result["training_readiness"], 94)
        self.assertEqual(result["training_readiness_selection"], "primary_tracker_morning")

    def test_sleep_details_remain_unchanged(self):
        scores = {"overall": {"value": 88}, "quality": {"value": 80}}
        client = SyntheticClient(sleep={"dailySleepDTO": {
            "sleepStartTimestampLocal": datetime(2026, 10, 5, 23, 0).timestamp() * 1000,
            "sleepEndTimestampLocal": datetime(2026, 10, 6, 7, 0).timestamp() * 1000,
            "sleepTimeSeconds": 28800, "deepSleepSeconds": 3600, "lightSleepSeconds": 18000,
            "remSleepSeconds": 7200, "awakeSleepSeconds": 1800, "sleepScores": scores}})
        result = asyncio.run(server.get_sleep_details(client, self.day))
        self.assertEqual(result, {"date": self.day, "sleep_start": "23:00", "sleep_end": "07:00",
                                  "total_sleep_minutes": 480, "deep_sleep_minutes": 60,
                                  "light_sleep_minutes": 300, "rem_sleep_minutes": 120,
                                  "awake_minutes": 30, "sleep_scores": scores})

    def test_activity_formatting_remains_unchanged(self):
        client = SyntheticClient(activities=[{"activityName": "Synthetic walk",
            "activityType": {"typeKey": "walking"}, "startTimeLocal": "2026-10-06T12:00:00",
            "duration": 3600, "distance": 1000, "calories": 100, "averageHR": 90, "maxHR": 110,
            "aerobicTrainingEffect": 1.0, "anaerobicTrainingEffect": 0.0}])
        result = asyncio.run(server.get_activities(client, self.day))
        self.assertEqual(result, {"date": self.day, "count": 1, "activities": [{
            "name": "Synthetic walk", "type": "walking", "start_time": "2026-10-06T12:00:00",
            "duration_minutes": 60.0, "distance_km": 1.0, "calories": 100, "avg_hr": 90,
            "max_hr": 110, "training_effect_aerobic": 1.0, "training_effect_anaerobic": 0.0}]})


if __name__ == "__main__":
    unittest.main()
