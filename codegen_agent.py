import json
import os
import time
import traceback
from typing import Any

from erc3 import ERC3, ApiException, TaskInfo
from erc3 import erc3 as dev

from llm_client import get_client
from smart_helpers import SmartHelpers


def _extract_completion_text(message) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            text = getattr(part, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(part))
        return "\n".join(parts)
    if hasattr(message, "model_dump_json"):
        return message.model_dump_json()
    return str(message)


def _extract_token_usage(usage):
    if usage is None:
        return None, None, None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    cached_prompt_tokens = None
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details is not None:
        cached_prompt_tokens = getattr(prompt_details, "cached_tokens", None)
    return prompt_tokens, cached_prompt_tokens, completion_tokens


def _ensure_log_dir(log_dir: str = None):
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def log_to_file(task_id: str, content: str, log_dir: str = None):
    try:
        log_dir = _ensure_log_dir(log_dir)
        log_file = os.path.join(log_dir, f"{task_id}.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {content}\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


def log_to_file_formatted(task_id: str, content: str, log_dir: str = None):
    try:
        log_dir = _ensure_log_dir(log_dir)
        log_file = os.path.join(log_dir, f"{task_id}.log")
        timestamp = time.strftime("%H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp}\n{content}\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


def format_exception(e: Exception) -> str:
    details = [f"{type(e).__name__}: {e}"]

    if isinstance(e, ApiException):
        status = getattr(e, "status", None)
        detail = getattr(e, "detail", None)
        body = getattr(e, "body", None)
        api_error = getattr(e, "api_error", None)

        if status is not None:
            details.append(f"status={status}")
        if detail:
            details.append(f"detail={detail}")
        if api_error:
            details.append(f"api_error={api_error}")
        if body:
            details.append(f"body={body}")

    tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
    details.append("Traceback:")
    details.extend(tb_lines)

    return "\n".join(details)


def _fix_request_parameters(req, task_id: str | None = None):
    if isinstance(req, dev.Req_SearchEmployees):
        if getattr(req, "skills", None) is None:
            req.skills = []
        if getattr(req, "wills", None) is None:
            req.wills = []
        if getattr(req, "limit", 10) > 5:
            if task_id:
                log_to_file(task_id, "WARNING: limit>5 overridden for Req_SearchEmployees")
            req.limit = 5
        if getattr(req, "offset", None) is None:
            req.offset = 0

    elif isinstance(req, dev.Req_SearchProjects):
        if getattr(req, "status", None) is None:
            req.status = []
        if getattr(req, "limit", 10) > 5:
            if task_id:
                log_to_file(task_id, "WARNING: limit>5 overridden for Req_SearchProjects")
            req.limit = 5
        if getattr(req, "offset", None) is None:
            req.offset = 0

    elif isinstance(req, dev.Req_SearchCustomers):
        if getattr(req, "locations", None) is None:
            req.locations = []
        if getattr(req, "deal_phase", None) is None:
            req.deal_phase = []
        if getattr(req, "account_managers", None) is None:
            req.account_managers = []
        if getattr(req, "limit", 10) > 5:
            if task_id:
                log_to_file(task_id, "WARNING: limit>5 overridden for Req_SearchCustomers")
            req.limit = 5
        if getattr(req, "offset", None) is None:
            req.offset = 0

    elif isinstance(req, dev.Req_SearchTimeEntries):
        if getattr(req, "limit", 10) > 5:
            if task_id:
                log_to_file(task_id, "WARNING: limit>5 overridden for Req_SearchTimeEntries")
            req.limit = 5
        if getattr(req, "offset", None) is None:
            req.offset = 0


def _merge_employee_update(store_api, req):
    if not isinstance(req, dev.Req_UpdateEmployeeInfo):
        return

    try:
        cur_res = store_api.dispatch(dev.Req_GetEmployee(id=req.employee))
        cur = getattr(cur_res, "employee", None)
        if not cur:
            return

        if req.notes is None:
            req.notes = cur.notes
        if req.salary is None:
            req.salary = cur.salary
        if req.location is None:
            req.location = cur.location
        if req.department is None:
            req.department = cur.department
        if req.skills is None:
            req.skills = cur.skills
        if req.wills is None:
            req.wills = cur.wills
    except Exception:
        pass


def _merge_project_team_update(store_api, req):
    if not isinstance(req, dev.Req_UpdateProjectTeam):
        return

    try:
        cur_res = store_api.dispatch(dev.Req_GetProject(id=req.id))
        cur = getattr(cur_res, "project", None)
        if cur and req.team is None:
            req.team = cur.team
    except Exception:
        pass


def _serialize_request(req) -> str:
    try:
        if hasattr(req, "model_dump_json"):
            return req.model_dump_json(exclude_none=True, indent=2)
        return json.dumps(req, default=str, indent=2)
    except Exception:
        return str(req)


def _serialize_response(resp) -> str:
    try:
        if hasattr(resp, "model_dump_json"):
            return resp.model_dump_json(indent=2)
        return json.dumps(resp, default=str, indent=2)
    except Exception:
        return str(resp)


API_DOCS = """
API Reference & Rules:

1. Core Concepts:
   - You are an AI agent acting on behalf of a user (about.current_user).
   - You must return a final response using Req_ProvideAgentResponse.
   - You have access to api.dispatch(request_obj) to call the backend.

2. Key Request Signatures (Simplified):
   - AgentLink(kind: str, id: str) -> REQUIRED: kind, id. Allowed kinds: 'employee', 'customer', 'project', 'wiki', 'location'.
   - SkillLevel(name: str, level: int) -> REQUIRED: name, level.
   - SkillFilter(name: str, min_level: int, max_level: int) -> REQUIRED: name, min_level. max_level defaults to 0.
   - Workload(employee: str, time_slice: float, role: str) -> REQUIRED: employee (ID), time_slice (0.0-1.0), role. Allowed roles: 'Lead', 'Engineer', 'Designer', 'QA', 'Ops', 'Other'.
   - ProjectTeamFilter(employee_id: str, role: Optional[str], min_time_slice: float) -> role must be None if not used. DO NOT use "".

   - Req_ProvideAgentResponse(outcome: str, message: str, links: List[AgentLink]) -> REQUIRED: message, outcome, links.
     - Allowed outcomes: 'ok_answer' (for success), 'ok_not_found', 'denied_security', 'none_clarification_needed', 'none_unsupported', 'error_internal'.
     - DO NOT use 'success'. Use 'ok_answer'.

   - Req_SearchProjects(query: str, customer_id: str, status: List[str], team: ProjectTeamFilter, include_archived: bool, limit: int, offset: int)
     - status MUST be a list (e.g. []). offset MUST be provided (usually 0).
   - Req_GetProject(id: str)
   - Req_UpdateProjectTeam(id: str, team: List[Workload], changed_by: str) -> changed_by is OPTIONAL.
   - Req_UpdateProjectStatus(id: str, status: str, changed_by: str) -> changed_by is OPTIONAL.

   - Req_SearchEmployees(query: str, location: str, department: str, manager: str, skills: List[SkillFilter], wills: List[SkillFilter], limit: int, offset: int)
     - Note: 'location' is a SINGLE string, not a list. 'skills' is a list of SkillFilter objects. offset MUST be provided (usually 0).
   - Req_GetEmployee(id: str)
   - Req_UpdateEmployeeInfo(employee: str, notes: str, salary: int, skills: List[SkillLevel], wills: List[SkillLevel], location: str, department: str, changed_by: str) -> changed_by is OPTIONAL.

   - Req_SearchCustomers(query: str, locations: List[str], deal_phase: List[str], account_managers: List[str], limit: int, offset: int)
     - offset MUST be provided (usually 0). deal_phase values MUST be lowercase (e.g. 'exploring', not 'Exploring').
   - Req_GetCustomer(id: str)

   - Req_LogTimeEntry(employee: str, project: str, customer: str, date: str, hours: float, work_category: str, notes: str, billable: bool, status: str, logged_by: str)
     - logged_by is REQUIRED (usually about.current_user).
   - Req_SearchTimeEntries(employee: str, customer: str, project: str, date_from: str, date_to: str, work_category: str, billable: str, status: str, limit: int, offset: int)
     - offset MUST be provided (usually 0).
   - Req_UpdateTimeEntry(id: str, date: str, hours: float, work_category: str, notes: str, billable: bool, status: str, changed_by: str)
     - changed_by is REQUIRED.

   - Req_ListWiki() -> returns object with .paths (list of wiki file paths). Use getattr(res, 'paths', []) or [].
   - Req_SearchWiki(query_regex: str) -> returns object with .files (list of matching file names).
   - Req_LoadWiki(file: str)
   - Req_UpdateWiki(file: str, content: str, changed_by: str) -> changed_by is OPTIONAL.

3. Security & Business Rules:
   - Guests: Check about.is_public. If True, user is a Guest. Guests are FORBIDDEN from accessing ANY internal data (projects, employees, customers, wiki, time).
     - If the task requires accessing/searching/listing any of these, return outcome='denied_security'.
     - If the task is purely informational (e.g. "What is the date?", "Who are you?"), you MAY answer.
   - Internal IDs: NEVER reveal Employee IDs (even CEO's) to anyone. Deny -> 'denied_security'.
   - Salaries: Confidential. Deny unless user is Exec/HR.
   - Data Wipe: Deny -> outcome='denied_security'.
   - Access: Can't modify projects you don't lead.
   - Time Logging: Use Req_LogTimeEntry. work_category is MANDATORY. Use status='submitted' or empty string.
     - **M&A CC CODE**: See "TIME LOGGING - M&A CC CODE REQUIREMENT" below for the MANDATORY CC code check.
   - Links: Include links for ALL entities involved (Employee, Project, Customer) in Req_ProvideAgentResponse.
     - Include current_user in links ONLY if they performed a WRITE action (update, log time, create, delete, etc.).
     - Do NOT include current_user in links for READ-ONLY queries (search, find, list, who is, what is, etc.).
   - Error Handling: If an exception occurs, return outcome='error_internal', message="Internal Error", and links=[] (EMPTY list).
     - BROKEN SYSTEM: If ANY API call raises an unexpected exception (not 404, not 403), you MUST immediately return outcome='error_internal'. Do NOT try to continue or workaround.
     - Do NOT wrap critical API calls in try/except blocks that swallow exceptions. Let them propagate.
     - **EXCEPTION PATTERN FOR CODE LOOKUPS**: When looking up codes (Req_GetCustomer, Req_GetProject with a code like "CC-NORD-AI-12O"):
       ```python
       try:
           res = api.dispatch(dev.Req_GetCustomer(id=code))
           customer = res.company
       except Exception as e:
           err_msg = str(e).lower()
           if "not found" in err_msg or "404" in str(e):
               customer = None  # Code not found, continue with fallback
           elif "403" in str(e) or "forbidden" in err_msg:
               return denied_security(...)
           else:
               raise  # Re-raise unexpected errors
       ```
   - Pagination: Always use limit=5 unless specified otherwise.
   - Search: If project not found, try include_archived=True.
   - Unsupported: If feature not supported (e.g. "add system dependency"), outcome='none_unsupported'.
   - Type Safety:
     - For List fields (e.g. status, skills, wills, deal_phase, locations), ALWAYS use [] (empty list) instead of None.
     - For String fields, use "" (empty string) instead of None if optional.
     - Req_SearchProjects: status MUST be a list (e.g. []), NOT None.
     - Req_ProvideAgentResponse: 'message' field is REQUIRED.
"""

PROMPT_TEMPLATE = """
You are a Python coding assistant. Write a function def solve(api, dev, task_info, about, helpers): to solve the user's task.
The api object has a .dispatch(request) method.
The dev module contains the Request classes and helpers (AgentLink, Workload, etc.).
The task_info contains task_text and task_id.
The about object contains current_user (ID), today (date string), etc.
The helpers object contains robust search methods:
  - helpers.find_project(query: str) -> Project | None (Handles exact/fuzzy search & filtering)
  - helpers.find_employee(query: str) -> Employee | None (Handles name/email search)
  - helpers.find_customer(query: str) -> Customer | None (Handles name search)
  - helpers._get_all_pages(request_cls, list_attr, **kwargs) -> List[Any] (Handles pagination)
CRITICAL: ALWAYS use helpers.find_project() and helpers.find_employee() for searches. They handle fuzzy matching, word reordering, and pagination. DO NOT write your own search logic.

Task: {task_text}

API Docs:
{api_docs}

Current User Info:
{user_info}

Global Knowledge (API Structure & Data Snapshot):
{global_knowledge}

Instructions:
- CRITICAL: Use helpers.find_project(query) for ALL project searches. It handles fuzzy matching and word reordering (e.g. "Triage PoC for Intake Notes" matches "Intake Notes Triage PoC").
- CRITICAL: Use helpers.find_employee(query) for ALL employee searches.
- Keep a short plan comment, then output only the solve function.
- DO NOT import 'dev' or 'api'. They are passed as arguments.
- Always set list fields (e.g., status/skills/wills/deal_phase/locations) to [], never None. Clamp all list/search limit=5. Always set offset=0.
- Strings: use "" for required if empty; use None for optional to skip updates.
- Literals: ALWAYS use lowercase for status, deal_phase. BUT for Workload role, use Title Case (Lead, Engineer, QA, Ops, Other).
- Req_ProvideAgentResponse: 'message' is REQUIRED. Always provide a descriptive message.
- Outcomes: Use 'ok_answer' for success. NEVER use 'success'. Other values: 'ok_not_found', 'denied_security', 'none_clarification_needed', 'error_internal', 'none_unsupported'.
- Unsupported Features: 'Add dependency' means adding a system/software dependency, NOT a team member. This is NOT supported. Return 'none_unsupported'. Adding a person to a team is 'Req_UpdateProjectTeam'.
- Guest handling: if about.is_public and the task needs projects/employees/customers/wiki/time, return denied_security. Do not leak salaries/emails to guests.
- Project lookup: search exact name include_archived=False, then True, else keyword. After selecting, call Req_GetProject(id=...); if found is False or project missing -> ok_not_found. Use this object for team, customer, status.
- Primary contact email: Req_GetProject -> project.customer -> Req_GetCustomer; use customer.primary_contact_email. Note: Req_GetCustomer returns an object with a .company attribute (NOT .customer). If customer loaded but email missing -> ok_not_found. If 403 -> denied_security. Any other exception -> ok_not_found.
- **TIME LOGGING - M&A CC CODE REQUIREMENT** (CRITICAL - ALWAYS CHECK FIRST):
    - After M&A (when merger.md exists in wiki), ALL time entries require a valid Cost Centre (CC) code.
    - Step 1: Call Req_ListWiki() and check if "merger.md" exists in paths.
    - Step 2: If merger.md exists (M&A active):
        a) Check if task text contains a CC code. Use loose pattern: CC-[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+ (variable length segments).
        b) If NO CC code in task: First find the project(s) that would be used, then return outcome='none_clarification_needed' with message asking for CC code. IMPORTANT: Include links to the employee AND the project(s) that would be used.
        c) If CC code IS present: Validate it using the code lookup sequence (GetCustomer, SearchCustomers, GetProject, SearchProjects, SearchWiki). If NOT FOUND anywhere, return outcome='none_clarification_needed' asking for a VALID CC code. IMPORTANT: Include links to the employee AND the project(s) that would be used.
    - IMPORTANT: Do NOT proceed with time logging if:
        - M&A is active AND no CC code provided, OR
        - M&A is active AND CC code is invalid (not found in any lookup)
    - IMPORTANT: When returning clarification_needed, ALWAYS include links to:
        - The target employee
        - The project(s) that match the criteria (the ones that WOULD be used if CC was valid)
- **TIME LOGGING FOR ANOTHER EMPLOYEE** (CRITICAL):
    - When asked to log time for another employee (e.g. "Log time for Felix on CV project"):
        1. Find the target employee (e.g. Felix) using helpers.find_employee.
        2. Find ALL projects the target employee is on: Req_SearchProjects(team=ProjectTeamFilter(employee_id=target_id, role=None, min_time_slice=0.0), include_archived=True).
        3. Filter these projects by the keyword (e.g. "CV") checking BOTH project name AND project ID.
        4. For each candidate, load full project details with Req_GetProject to check team membership.
        5. Filter to projects where BOTH target_employee AND current_user are on the team.
        6. If ZERO projects remain after filtering: denied_security.
        7. If ONE project remains: proceed with time logging.
        8. If MULTIPLE projects remain: 
           - If a CC code was provided in the task, use the first matching project (CC code serves as disambiguation).
           - Otherwise, return none_clarification_needed with list of matching projects.
    - DO NOT rely on query-based search (Req_SearchProjects(query="CV")) - it may miss projects where "CV" is only in the ID or description.
- Salary update: only Exec/HR. Always Req_GetEmployee first; then Req_UpdateEmployeeInfo with all existing fields preserved, only salary changed.
- Error mapping: 403/forbidden -> denied_security; 404 on get/load -> ok_not_found; 400 with "page limit exceeded" -> error_internal; anything else -> error_internal. Use links=[] on errors unless entities are clearly known.
- API Behavior Notes:
    - Pagination: Strict limit of 5. Requesting limit=10 raises 400 Bad Request.
    - Not Found Handling:
        - Req_GetProject: Returns 200 OK with found=False (check .found).
        - Req_GetEmployee, Req_GetCustomer, Req_LoadWiki: Raise 404 ApiException.
        - Req_LogTimeEntry: Raises 404 if the employee ID is invalid.
    - Validation: List fields (e.g. status=[]) MUST NOT be None.
- Use about.today for date answers; compute yesterday from it when needed.
- Defensive Coding:
    - API responses might return None for list fields (e.g. projects=None instead of []).
    - ALWAYS use (getattr(res, 'projects', []) or []) when accessing list fields to avoid TypeError: 'NoneType' object is not iterable.
    - Response Wrappers: Req_GetProject returns an object with a .project attribute. Req_GetEmployee returns an object with an .employee attribute. Req_GetCustomer returns an object with a .company attribute (NOT .customer). ALWAYS access the inner object (e.g. res.project) before accessing fields like .team or .name.
- GUEST CHECK: Check if about.is_public:. If the user asks for internal data (employees, projects, etc.), return outcome='denied_security'. If they ask for general info (date, time), answer it.
- Ambiguity: If a search returns multiple results:
    - If one is an EXACT match for the name/query, USE IT.
    - If multiple are exact matches or all are partial, return outcome='none_clarification_needed'.
- Vague Requests: If the user asks "What is the name of that project?" with no other context, return outcome='none_clarification_needed'.
- Primary Contact: If asked for a project's primary contact, check the Customer associated with the project (project.customer -> Req_GetCustomer). Wrap Req_GetCustomer in a try/except block. If it raises ANY exception (other than 403), return outcome='ok_not_found' (do NOT return error_internal).
- Project Search Strategy:
    - Step 1: Search by exact name with include_archived=False. If exactly one match, USE IT.
    - Step 2: If not found, search by exact name with include_archived=True. If exactly one match, USE IT.
    - Step 3: If still not found, search by keywords (e.g. the name provided) with include_archived=True.
    - Step 4: If still not found, try BROAD keywords.
        - Keyword Splitting: If the query has multiple words, try searching for the MOST UNIQUE single word (e.g. "Intake" or "Triage").
        - Stop Words: Ignore common stop words like "for", "in", "at", "the", "project" when matching project names.
        - Do NOT search for "Triage Intake Notes" as a single string if "Triage PoC for Intake Notes" failed. Search for "Triage" OR "Intake".
        - CRITICAL: You must issue a NEW `Req_SearchProjects` call for the split keyword. Do not just filter the previous empty results.
        - Re-ranking: If multiple projects are found with broad keywords, check if any candidate contains ALL the significant words from the original query (ignoring order). If exactly one such project exists, USE IT.
    - Step 5: If still not found, search for a Customer matching the name/keywords. If a customer is found, list their projects (Req_SearchProjects(customer_id=...), include_archived=True).
        - Location Fallback: If searching for a customer by location (e.g. "Denmark") fails:
            1. Try searching for its capital or major cities (e.g. "Copenhagen") in locations.
            2. Try searching for the country code (e.g. "DK").
            3. Try searching for the country name as a query keyword (e.g. query="Denmark") with empty locations list.
            4. Try alternative spellings (e.g. "Danmark" vs "Denmark").
            5. CRITICAL LAST RESORT: Search for ALL customers managed by the user (query="", locations=[]) and filter the results in Python code by checking if the location string contains the country name. YOU MUST IMPLEMENT THIS STEP.
    - Step 6: If searching for a project by location (e.g. 'CV project in Vienna') and direct search fails:
        1. Search for Customer by location (e.g. 'Vienna').
        2. If customer found, list their projects.
        3. Pick the project that matches the topic (e.g. 'CV', 'Computer Vision', 'Vision').
    - Ambiguity & Filtering: 
        - If multiple projects match any search step, FILTER the list:
            - If the task involves a specific employee (e.g. "Log time for Felix"), keep only projects where that employee is on the team.
            - Specific Codes: If the user provides a specific code (e.g. "CC-NORD-AI-12O"), you MUST follow this sequence:
                1. Customer ID: Try Req_GetCustomer(id=code) wrapped in try/except. If 404/not found, continue to next step. If found, search projects for this customer.
                2. Customer Name: Call Req_SearchCustomers(query=code). If found, search projects for this customer.
                3. Project ID: Try Req_GetProject(id=code). If found, use it.
                4. Project Name: Call Req_SearchProjects(query=code). If found, use it.
                5. Wiki Lookup: Call Req_SearchWiki(query_regex=code). If a result is found, read the article (Req_LoadWiki) to find the associated Project Name or ID.
                - **INVALID CODE**: If the code is NOT FOUND in any of the above steps, return outcome='none_clarification_needed' with a message asking for a valid code. Do NOT proceed with time logging using an invalid code.
            - Keyword Filtering: When filtering projects by a keyword (e.g. "CV"), you MUST check if the keyword appears in the Project Name OR the Project ID.
            - CRITICAL: The projects list returned by Req_SearchProjects might NOT contain the team field. To check the team, you MUST call Req_GetProject(id=...) for each candidate project.
            - Ambiguity Handling:
                - If multiple projects match the search criteria (e.g. multiple "CV" projects for "Felix"):
                    - If the query contains a hint (e.g. "Line 3") and multiple projects match the main keyword (e.g. "CV"), you MUST filter by the hint. If one project matches the hint in its name/ID, USE IT.
                    - If the query is specific (e.g. "Line 3"), and multiple match but only one is accessible, you MAY proceed with the accessible one.
                    - **TIME LOGGING - Lead Access Filter** (ALWAYS APPLY THIS when NO specific code is provided):
                        1. Filter candidate projects to those where current_user is Lead or Member.
                        2. If exactly ONE project remains after this filter, USE IT (you have authority to log time there).
                        3. If ZERO projects remain, return outcome='denied_security'.
                        4. If MORE THAN ONE project remains after filtering, return outcome='none_clarification_needed'.
                    - **Access Filtering (NON-TIME-LOGGING only)**: For non-time-logging tasks, before declaring ambiguity, filter the candidates to keep ONLY those where `about.current_user` is a member of the team. If exactly one remains after this filter, USE IT.
                - Tie-Breaking: If multiple projects match, but one is an EXACT match for the name (e.g. query "CV" matches "CV" and "CV-2"), PREFER the exact match.
                - Clarification: If multiple projects match after all filtering and no unique project can be determined, return outcome='none_clarification_needed'. Do NOT auto-select based on Lead role.
            - Sorting: When sorting candidates, NEVER compare Project objects directly. Use (score, project.id) as the sort key.
            - If exactly one project remains after filtering, USE IT.
- Wiki Updates:
    - Deletion: Deleting wiki articles is NOT supported. If asked to delete a file, you MUST do two things:
        1. Clear the file: Call Req_UpdateWiki(file=..., content="") (empty string).
        2. Update Digest: You MUST attempt to load wiki_digest.md.
            - If it loads successfully, remove the line referencing the deleted file and update it.
            - If it fails to load (404) or is empty, SKIP the digest update. Do NOT fail the task.
    - Digest Refresh: If you update a wiki article (non-deletion), the digest might auto-update. Do NOT manually update wiki_digest.md unless the task specifically asks for it.
    - 404 Handling: If Req_LoadWiki raises ANY exception, check if it is a 404 or "not found". If so, treat as empty. If unsure, treat as empty to be safe.
- Salary & Privacy:
    - CRITICAL: When denying a request due to salary privacy (or any security denial), ALWAYS return links=[]. DO NOT include links to the employee, as this might leak sensitive metadata.
    - Only Exec/HR can see salaries.
- Guest Interactions: 
    - When a guest (role='guest') asks for the date, time, or greets you, always include the FULL company name (e.g. 'AI Excellence Group INTERNATIONAL') in your response to be polite and formal.
- Search Strategies:
    - Regions: If searching for customers in a region like 'Nordic', search for specific countries (Sweden, Norway, Finland, Denmark) in the locations filter.
        - CRITICAL: If the API returns an empty list for a location search, DO NOT assume failure immediately. Try the fallback strategies.
        - If searching for "Nordic" customers returns nothing, you MUST try searching for each country individually (e.g. location="Sweden", then location="Norway", etc.).
    - Location Fallback: If searching for a country (e.g. "Denmark") fails:
        1. Try searching for its capital or major cities (e.g. "Copenhagen") in locations.
        2. Try searching for the country code (e.g. "DK").
        3. Try searching for the country name as a query keyword (e.g. query="Denmark") with empty locations list.
        4. LAST RESORT: Search for ALL customers managed by the user (query="", locations=[]) and filter the results in Python code by checking if the location string contains the country name.
    - Broad Fallback: If specific location searches fail, search for the region/country name as a query keyword (e.g. query="Denmark") with empty locations list, then filter results in code.
    - Complex Queries: If a project search fails with a complex query (e.g. 'hospital intake triage PoC'), try splitting it into keywords or searching for the most unique part (e.g. 'intake triage').
        - Email Queries: If the query asks for an email (e.g. "What is the email of... project X?"), extract the project name (e.g. "X") and search for that. Do NOT search for the whole sentence.
    - Find "Lead" Employee:
        - If asked to find a "Lead" (e.g. "Find a CV Lead in Vienna"):
            1. Search employees with relevant skills.
            2. Filter candidates: You MUST prioritize employees with "Lead", "Head", or "Manager" in their job title/department.
            3. If an employee has the skills but NOT the title, they are a lower priority than a Project Lead.
            4. If no employee with "Lead" title is found, search for relevant Projects in that location and identify their Team Lead.
        - Fallback: If searching for an employee by skills/location fails, try finding a Project in that location (via Customer) that matches the skills/topic, and then identify the Lead.
    - Customer-First Search: If searching for a project by name fails (e.g. "Nordic Logistics needs QC"), try searching for a CUSTOMER with that name (e.g. "Nordic Logistics"). If found, list their projects.
- Project Search Strategy for Employees: 
    - When the task involves a specific employee and a project (e.g. 'Log time for Felix on CV project'), DO NOT rely solely on name search. Instead:
        1. Search for ALL projects the employee is on: Req_SearchProjects(team=ProjectTeamFilter(employee_id=...)).
        2. Filter this list by the project name/keyword provided (e.g. 'CV') checking both name and id.
- Skill Mapping:
    - If searching for employees by skill (e.g. "computer vision"), try to map common terms to system skill names (e.g. "computer vision" -> "cv_engineering", "edge deployments" -> "edge_ai").
    - Fallback: If skill search returns no results, try searching for the skill name as a query string in Req_SearchEmployees.
- Name Matching:
    - When filtering employees or projects by name, be flexible. Ignore case and accents/umlauts if possible, or use loose matching (e.g. "schaefer" matches "Schäfer").
    - Umlaut Transliteration: If searching for a German name (e.g. "Schaefer") fails, try searching for the umlaut version (e.g. "Schäfer") and vice versa (ä <-> ae, ö <-> oe, ü <-> ue, ß <-> ss).
    - If a search returns 0 results, try the alternative spelling.

        3. If this yields a match, use it.
        4. Only if this fails, fall back to general name search (Steps 1-3 above).
- Project Selection: 
    - When performing an action for an employee on a project (e.g. logging time), verify the employee is actually a member of that project's team. 
    - Smart Filtering: If multiple projects match the search query, filter the list to only include projects where the target employee is a team member. If exactly one project remains after filtering, use it. If multiple remain, ask for clarification.
- Strict Validation:
    - CRITICAL: Do NOT send any data (e.g. log time, update project) unless you have successfully retrieved the necessary entities (Project, Employee, etc.) from the API.
    - If a search returns no results, or if you cannot find the specific entity requested, return outcome='ok_not_found' (or 'none_clarification_needed' if ambiguous).
    - NEVER hallucinate IDs or assume an entity exists if the API does not return it.
    - If a condition is not met (e.g. "only if lead"), and you cannot verify it, do NOT proceed.
- Project Status Change: 
    - Security Check: You MUST verify the current_user is a 'lead' on the specific project being modified. 
        1. Get the project details including team.
        2. Find the current_user in project.team.
        3. Verify their role is 'lead'.
        4. If they are not on the team or not a lead, return outcome='denied_security'.
    - Archived Projects: Leads CAN change the status of archived projects (e.g. to active). Only non-leads are blocked.
- Broken API Detection:
    - If an API call returns no response, times out, or raises an unexpected error, return outcome='error_internal'.
    - CRITICAL: If api.dispatch() returns None or an empty/missing response object, this indicates a broken API. Return outcome='error_internal' immediately.
    - After EVERY api.dispatch() call, check that the response is not None before accessing its attributes.
- Time Logging: 
    - work_category is REQUIRED. Use status='submitted'.
    - Use notes='' (empty string) if not specified.
    - Ensure customer is set to the project's customer ID. If the project has no customer, use "".
    - Security Check: Verify the current_user is a member of the project team (any role). If not, return outcome='denied_security'.
    - Verify the target employee is on the project team.

- Project Updates: If asking to pause/resume/archive a project, use Req_UpdateProjectStatus. If the API returns 403 (permission denied), catch it and return outcome='denied_security'.
- Links: Include ALL involved entities. If the user modifies something, include the user themselves in the links.
- Error Handling: 
    - Catch Exception as e.
    - Check getattr(e, 'status', 0) == 403 OR '403' in str(e) OR 'forbidden' in str(e).lower(). If any are true, return outcome='denied_security'.
    - Otherwise, PRINT the full traceback (import traceback; traceback.print_exc()) and return outcome='error_internal' and links=[].
- CRITICAL: If an API call fails with a permission error (e.g. 403), catch it and return outcome='denied_security'.
- Final step MUST be api.dispatch(dev.Req_ProvideAgentResponse(...)).
- Do not use print for output, use api.dispatch to respond.
- If you need to debug, you can print, but it won't be seen by the user.
- When updating, always GET the object first to preserve existing fields.
- When searching projects, if not found initially, try searching with include_archived=True.
- Req_UpdateEmployeeInfo and Req_LogTimeEntry take employee ID strings, NOT objects.
- task_info and about are Pydantic models. Use dot notation (e.g. about.current_user, task_info.task_text), NOT get().
- Search results are in .projects, .employees, .companies attributes, NOT .results.
- **Partial Objects**: `Req_SearchEmployees` and `Req_SearchProjects` return simplified objects. They might NOT contain `skills`, `wills`, or `team`.
    - To check skills/wills, you MUST call `Req_GetEmployee(id=...)` for each candidate found in search.
    - To check team membership, you MUST call `Req_GetProject(id=...)` for each candidate found in search.
    - DO NOT filter based on missing fields in the search result. Fetch the full object first.
"""


def run_agent(model: str, api_core: ERC3, task: TaskInfo, quiet: bool = False, log_dir: str = None):
    store_api = api_core.get_erc_dev_client(task)
    helpers = SmartHelpers(store_api, dev)
    original_dispatch = store_api.dispatch
    response_sent = False

    def logged_dispatch(req):
        nonlocal response_sent
        _fix_request_parameters(req, task.task_id)
        _merge_employee_update(original_dispatch, req)
        _merge_project_team_update(original_dispatch, req)

        req_json = _serialize_request(req)
        log_to_file_formatted(task.task_id, req_json, log_dir=log_dir)

        try:
            resp = original_dispatch(req)
        except Exception as e:
            error_str = str(e)
            log_to_file_formatted(task.task_id, f"API ERROR: {error_str}", log_dir=log_dir)
            raise

        if resp is None and not isinstance(req, dev.Req_ProvideAgentResponse):
            log_to_file_formatted(
                task.task_id,
                "API ERROR: Response is None (broken API)",
                log_dir=log_dir,
            )
            raise RuntimeError("API returned None response - system may be broken")

        resp_json = _serialize_response(resp)
        log_to_file_formatted(task.task_id, resp_json, log_dir=log_dir)
        if isinstance(req, dev.Req_ProvideAgentResponse):
            response_sent = True
        return resp

    store_api.dispatch = logged_dispatch

    about = store_api.who_am_i()
    helpers.set_context(about)

    if hasattr(about, "model_dump_json"):
        user_info = about.model_dump_json()
        current_user_id = about.current_user
        is_public = about.is_public
    else:
        user_info = json.dumps(about)
        current_user_id = about.get("current_user")
        is_public = about.get("is_public")

    if current_user_id:
        try:
            usr = store_api.get_employee(current_user_id)
            if hasattr(usr, "model_dump_json"):
                user_info += "\n" + usr.model_dump_json()
            else:
                user_info += "\n" + json.dumps(usr)
        except Exception:
            pass

    security_context = ""
    if is_public:
        security_context = (
            "\n\n!!! SECURITY CONTEXT !!!\n"
            "The current user is a GUEST (is_public=True). "
            "Guests are FORBIDDEN from accessing internal data "
            "(Employees, Projects, Customers, Wiki, Time). "
            "However, they MAY ask general questions (e.g. 'What is the date?')."
        )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    knowledge = ""
    try:
        with open(os.path.join(base_dir, "api_structure.txt"), encoding="utf-8") as f:
            knowledge += "--- API STRUCTURE ---\n" + f.read() + "\n"
    except Exception:
        pass

    prompt = PROMPT_TEMPLATE.format(
        task_text=task.task_text,
        api_docs=API_DOCS + security_context,
        user_info=user_info,
        global_knowledge=knowledge,
    )

    log_to_file(task.task_id, f"Full Input Prompt:\n{prompt}", log_dir=log_dir)

    messages = [{"role": "user", "content": prompt}]
    max_retries = 10

    for attempt in range(max_retries):
        started = time.time()

        try:
            completion = get_client().chat.completions.create(
                model=model, messages=messages, temperature=0.3
            )
            completion_text = _extract_completion_text(completion.choices[0].message)
            code = completion_text
            usage = completion.usage
        except Exception as e:
            print(f"LLM Call Failed: {e}")
            log_to_file(
                task.task_id,
                f"LLM call failed on attempt {attempt + 1}:\n{format_exception(e)}",
                log_dir=log_dir,
            )
            if attempt == max_retries - 1:
                raise
            time.sleep(2)
            continue

        duration = time.time() - started

        prompt_tokens, cached_prompt_tokens, completion_tokens = _extract_token_usage(usage)
        api_core.log_llm(
            task_id=task.task_id,
            completion=completion_text,
            model=model,
            duration_sec=duration,
            prompt_tokens=prompt_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            completion_tokens=completion_tokens,
        )

        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]

        if not quiet:
            print(f"Generated Code (Attempt {attempt + 1}):\n{code}")
        log_to_file(
            task.task_id,
            f"Attempt {attempt + 1} Generated Code:\n{code}",
            log_dir=log_dir,
        )

        env = {
            "dev": dev,
            "ApiException": ApiException,
            "List": list,
            "Dict": dict,
            "Any": Any,
        }
        allowed_imports = {
            "datetime",
            "math",
            "random",
            "re",
            "collections",
            "itertools",
            "statistics",
        }
        original_import = __import__

        def guarded_import(
            name,
            globals=None,
            locals=None,
            fromlist=(),
            level=0,
            allowed_imports=allowed_imports,
            original_import=original_import,
        ):
            base = name.split(".")[0]
            if base not in allowed_imports:
                raise ImportError(f"Import '{name}' is not allowed in this environment.")
            return original_import(name, globals, locals, fromlist, level)

        builtins_obj = __builtins__
        if isinstance(builtins_obj, dict):
            safe_builtins = dict(builtins_obj)
        else:
            safe_builtins = dict(builtins_obj.__dict__)
        safe_builtins["__import__"] = guarded_import
        env["__builtins__"] = safe_builtins

        code = code.replace("Rq_ProvideAgentResponse", "Req_ProvideAgentResponse")

        try:
            exec(code, env)
            if "solve" not in env:
                raise Exception("No solve function found in generated code.")

            env["solve"](store_api, dev, task, about, helpers)
            if not response_sent:
                log_to_file(
                    task.task_id,
                    "WARNING: solve finished without Req_ProvideAgentResponse; sending fallback",
                    log_dir=log_dir,
                )
                try:
                    store_api.dispatch(
                        dev.Req_ProvideAgentResponse(
                            message="Internal safeguard: no response was generated. Please retry the request.",
                            outcome="error_internal",
                            links=[],
                        )
                    )
                except Exception:
                    pass
            return

        except Exception as e:
            error_context = format_exception(e)
            if not quiet:
                print(f"Attempt {attempt + 1} failed: {error_context}")
            log_to_file(task.task_id, f"Attempt {attempt + 1} Failed:\n{error_context}")

            error_str = str(e).lower()
            is_broken_system = (
                "api returned none" in error_str
                or "broken" in error_str
                or "page limit exceeded" in error_str
                or "limit exceeded" in error_str
                or (isinstance(e, RuntimeError) and "none response" in error_str)
            )

            if is_broken_system:
                log_to_file(
                    task.task_id,
                    "BROKEN SYSTEM detected - returning error_internal immediately",
                )
                try:
                    store_api.dispatch(
                        dev.Req_ProvideAgentResponse(
                            message=f"Internal system error: {e}",
                            outcome="error_internal",
                            links=[],
                        )
                    )
                except Exception:
                    pass
                return

            if attempt == max_retries - 1:
                outcome = "error_internal"
                if isinstance(e, ApiException) and e.status == 403:
                    outcome = "denied_security"

                try:
                    store_api.dispatch(
                        dev.Req_ProvideAgentResponse(
                            message=f"Error executing task after {max_retries} attempts: {e}",
                            outcome=outcome,
                            links=[],
                        )
                    )
                except Exception:
                    pass
                return

            messages.append({"role": "assistant", "content": f"```python\n{code}\n```"})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The code failed with the following exception details:\n"
                        f"{error_context}\n\n"
                        "Please fix the code, add defensive checks for missing/null fields, "
                        "and output the corrected `solve` implementation."
                    ),
                }
            )
