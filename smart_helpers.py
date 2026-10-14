import re
from typing import Any


class SmartHelpers:
    def __init__(self, api, dev):
        self.api = api
        self.dev = dev
        self._context: dict[str, Any] = {}
        self._project_cache: dict[str, Any] = {}
        self._employee_cache: dict[str, Any] = {}

    def set_context(self, about: Any):
        if about is None:
            return
        self._context = {
            "current_user_id": getattr(about, "current_user", None)
            or getattr(about, "id", None)
            or getattr(about, "user", None),
            "department": getattr(about, "department", None) or getattr(about, "dept", None),
            "location": getattr(about, "location", None),
            "is_public": getattr(about, "is_public", False),
        }

    def _get_all_pages(self, request_cls, list_attr: str, **kwargs) -> list[Any]:
        items = []
        offset = 0
        limit = 5

        while True:
            kwargs["offset"] = offset
            kwargs["limit"] = limit

            req = request_cls(**kwargs)
            try:
                res = self.api.dispatch(req)
            except Exception as e:
                error_msg = str(e).lower()
                if "page limit exceeded" in error_msg or "limit exceeded" in error_msg:
                    raise
                break

            batch = getattr(res, list_attr, []) or []
            items.extend(batch)

            next_off = getattr(res, "next_offset", None)
            if next_off is None or next_off < 0:
                break
            offset = next_off

            if len(items) > 500:
                break

        return items

    def _safe_lower(self, value: str) -> str:
        return (value or "").strip().lower()

    def _load_project_details(self, project_id: str):
        if not project_id:
            return None
        if project_id in self._project_cache:
            return self._project_cache[project_id]
        res = self.api.dispatch(self.dev.Req_GetProject(id=project_id))
        project = getattr(res, "project", None)
        if project:
            self._project_cache[project_id] = project
        return project

    def _load_employee_details(self, employee_id: str):
        if not employee_id:
            return None
        if employee_id in self._employee_cache:
            return self._employee_cache[employee_id]
        res = self.api.dispatch(self.dev.Req_GetEmployee(id=employee_id))
        employee = getattr(res, "employee", None)
        if employee:
            self._employee_cache[employee_id] = employee
        return employee

    def _score_project(self, query_words: set, project: Any) -> float:
        p_name = getattr(project, "name", "") or ""
        p_id = getattr(project, "id", "") or ""

        score = 0.0
        if not query_words:
            return score

        lower_name = p_name.lower()
        lower_id = p_id.lower()
        for w in query_words:
            if w in lower_name:
                score += 4
            if w in lower_id:
                score += 2
        if lower_name in query_words:
            score += 5
        if getattr(project, "status", "") == "active":
            score += 1
        return score

    def _filter_projects_by_access(
        self,
        projects: list[Any],
        require_current_user: bool = False,
        require_employee_id: str | None = None,
    ) -> list[Any]:
        if not (require_current_user or require_employee_id):
            return projects

        current_user = self._context.get("current_user_id")
        filtered = []
        for project in projects:
            details = self._load_project_details(getattr(project, "id", ""))
            if not details:
                continue
            team = getattr(details, "team", []) or []

            def _has_member(emp_id: str, team=team):
                if not emp_id:
                    return False
                for slot in team:
                    if getattr(slot, "employee", None) == emp_id:
                        return True
                return False

            if require_current_user and not _has_member(current_user):
                continue
            if require_employee_id and not _has_member(require_employee_id):
                continue
            filtered.append(details)
        return filtered

    def _search_projects(self, query: str, include_archived: bool) -> list[Any]:
        req = self.dev.Req_SearchProjects(
            query=query,
            customer_id="",
            status=[],
            team=None,
            include_archived=include_archived,
            limit=5,
            offset=0,
        )
        res = self.api.dispatch(req)
        return getattr(res, "projects", []) or []

    def find_project(
        self,
        query: str,
        *,
        require_current_user_member: bool = False,
        require_employee_id: str | None = None,
        customer_first: bool = True,
    ) -> Any | None:
        if not query:
            return None

        normalized_query = query.strip()
        query_words = {w.lower() for w in re.split(r"\W+", normalized_query) if len(w) > 1}
        tried_ids = set()
        candidates: list[Any] = []

        try:
            primary = self._search_projects(normalized_query, include_archived=False)
            candidates.extend(primary)
        except Exception as e:
            if "limit exceeded" in str(e).lower():
                raise

        if not candidates:
            try:
                candidates.extend(self._search_projects(normalized_query, include_archived=True))
            except Exception as e:
                if "limit exceeded" in str(e).lower():
                    raise

        if not candidates:
            for kw in sorted(query_words, key=len, reverse=True):
                try:
                    batch = self._search_projects(kw, include_archived=True)
                    candidates.extend(batch)
                except Exception as e:
                    if "limit exceeded" in str(e).lower():
                        raise

        if not candidates and customer_first:
            customer = self.find_customer(normalized_query)
            if customer:
                try:
                    req = self.dev.Req_SearchProjects(
                        query="",
                        customer_id=getattr(customer, "id", ""),
                        status=[],
                        team=None,
                        include_archived=True,
                        limit=5,
                        offset=0,
                    )
                    res = self.api.dispatch(req)
                    candidates.extend(getattr(res, "projects", []) or [])
                except Exception:
                    pass

        if not candidates:
            return None

        deduped = []
        for c in candidates:
            cid = getattr(c, "id", None)
            if not cid or cid in tried_ids:
                continue
            tried_ids.add(cid)
            deduped.append(c)

        accessible = self._filter_projects_by_access(
            deduped,
            require_current_user=require_current_user_member,
            require_employee_id=require_employee_id,
        )
        scored_list = accessible or deduped

        best = None
        best_score = -1.0
        for p in scored_list:
            score = self._score_project(query_words, p)
            if score > best_score:
                best = p
                best_score = score
        return best

    def _search_employees(self, query: str) -> list[Any]:
        req = self.dev.Req_SearchEmployees(
            query=query,
            limit=5,
            offset=0,
            skills=[],
            wills=[],
            location="",
            department="",
            manager="",
        )
        res = self.api.dispatch(req)
        return getattr(res, "employees", []) or []

    def find_employee(self, query: str) -> Any | None:
        if not query:
            return None

        normalized = query.strip()
        candidates: list[Any] = []
        try:
            candidates.extend(self._search_employees(normalized))
        except Exception as e:
            if "limit exceeded" in str(e).lower():
                raise

        if not candidates:
            tokens = [w for w in re.split(r"\W+", normalized) if w]
            for token in tokens:
                try:
                    candidates.extend(self._search_employees(token))
                except Exception as e:
                    if "limit exceeded" in str(e).lower():
                        raise

        if not candidates:
            return None

        lowered_query = normalized.lower()
        for e in candidates:
            if getattr(e, "name", "").lower() == lowered_query:
                return e
            if getattr(e, "email", "").lower() == lowered_query:
                return e

        return candidates[0]

    def find_customer(self, query: str) -> Any | None:
        if not query:
            return None

        try:
            req = self.dev.Req_SearchCustomers(
                query=query,
                locations=[],
                deal_phase=[],
                account_managers=[],
                limit=5,
                offset=0,
            )
            res = self.api.dispatch(req)
            companies = getattr(res, "companies", []) or []

            for c in companies:
                if c.name.lower() == query.lower():
                    return c

            if companies:
                return companies[0]
        except Exception as e:
            error_msg = str(e).lower()
            if (
                "page limit exceeded" in error_msg
                or "limit exceeded" in error_msg
                or "broken" in error_msg
            ):
                raise
            pass
        return None

    def list_employee_projects(self, employee_id: str, include_archived: bool = True) -> list[Any]:
        if not employee_id:
            return []
        team_filter = self.dev.ProjectTeamFilter(
            employee_id=employee_id, role=None, min_time_slice=0.0
        )
        return self._get_all_pages(
            self.dev.Req_SearchProjects,
            "projects",
            query="",
            customer_id="",
            status=[],
            team=team_filter,
            include_archived=include_archived,
        )
