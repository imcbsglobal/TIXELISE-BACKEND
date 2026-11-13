from .base import APITestBase


class EventProgramDurationTests(APITestBase):
    """The daily program window is optional and applies to both event types."""

    def test_regular_event_accepts_program_window(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV801",
                "name": "Walk-in counter",
                "event_type": "regular",
                "program_start_time": "09:00",
                "program_end_time": "17:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["program_start_time"], "09:00:00")
        self.assertEqual(response.data["program_end_time"], "17:00:00")
        self.assertEqual(response.data["program_duration_minutes"], 480)

    def test_periodical_event_accepts_program_window(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV802",
                "name": "Evening show",
                "event_type": "periodical",
                "start_at": "2026-12-01T18:00:00Z",
                "end_at": "2026-12-02T00:00:00Z",
                "program_start_time": "18:30",
                "program_end_time": "21:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["program_start_time"], "18:30:00")
        self.assertEqual(response.data["program_end_time"], "21:00:00")
        self.assertEqual(response.data["program_duration_minutes"], 150)

    def test_program_window_is_optional(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {"code": "EV803", "name": "No programme", "event_type": "regular"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.data["program_start_time"])
        self.assertIsNone(response.data["program_end_time"])
        self.assertIsNone(response.data["program_duration_minutes"])

    def test_supplying_only_one_program_time_is_rejected(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV804",
                "name": "Half a window",
                "event_type": "regular",
                "program_start_time": "09:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_program_end_must_be_after_start(self):
        self.login_admin_a()
        response = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV805",
                "name": "Backwards programme",
                "event_type": "regular",
                "program_start_time": "17:00",
                "program_end_time": "09:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_program_window_can_be_updated_and_cleared(self):
        self.login_admin_a()
        created = self.client.post(
            "/api/v1/admin/events/",
            {
                "code": "EV806",
                "name": "Editable programme",
                "event_type": "regular",
                "program_start_time": "09:00",
                "program_end_time": "17:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        url = f"/api/v1/admin/events/{created.data['id']}/"

        updated = self.client.patch(
            url,
            {"program_end_time": "19:30"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data["program_end_time"], "19:30:00")
        self.assertEqual(updated.data["program_duration_minutes"], 630)

        cleared = self.client.patch(
            url,
            {"program_start_time": None, "program_end_time": None},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(cleared.data["program_start_time"])
        self.assertIsNone(cleared.data["program_end_time"])
