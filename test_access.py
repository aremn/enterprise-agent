import unittest
from types import SimpleNamespace

from smart_helpers import SmartHelpers


class ProjectAccessTests(unittest.TestCase):
    def setUp(self):
        self.helpers = SmartHelpers(None, None)
        self.helpers.set_context(SimpleNamespace(current_user="member", is_public=False))
        self.projects = [SimpleNamespace(id="allowed"), SimpleNamespace(id="unrelated")]
        self.details = {
            "allowed": SimpleNamespace(id="allowed", team=[SimpleNamespace(employee="member")]),
            "unrelated": SimpleNamespace(id="unrelated", team=[SimpleNamespace(employee="other")]),
        }
        self.helpers._load_project_details = self.details.get

    def test_current_user_sees_only_own_projects(self):
        result = self.helpers._filter_projects_by_access(self.projects, require_current_user=True)
        self.assertEqual([project.id for project in result], ["allowed"])

    def test_unknown_user_receives_no_projects(self):
        self.helpers.set_context(SimpleNamespace(current_user=None, is_public=True))
        self.assertEqual(
            self.helpers._filter_projects_by_access(self.projects, require_current_user=True), []
        )

    def test_combined_filters_require_both_members(self):
        self.assertEqual(
            self.helpers._filter_projects_by_access(
                self.projects, require_current_user=True, require_employee_id="other"
            ),
            [],
        )

    def test_unavailable_project_is_excluded(self):
        self.details.clear()
        self.assertEqual(
            self.helpers._filter_projects_by_access(self.projects, require_current_user=True), []
        )


if __name__ == "__main__":
    unittest.main()
