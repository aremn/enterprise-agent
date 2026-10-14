import json
import os
import time
from typing import Annotated

from annotated_types import MaxLen, MinLen
from erc3 import ERC3, ApiException, TaskInfo
from erc3 import erc3 as dev
from pydantic import BaseModel, Field

from llm_client import get_client


def log_to_file(task_id: str, content: str, log_dir: str = None):
    try:
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{task_id}.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {content}\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


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


class NextStep(BaseModel):
    current_state: str

    plan_remaining_steps_brief: Annotated[list[str], MinLen(1), MaxLen(5)] = Field(
        ...,
        description="explain your thoughts on how to accomplish - what steps to execute",
    )

    task_completed: bool

    function: (
        dev.Req_ProvideAgentResponse
        | dev.Req_ListProjects
        | dev.Req_ListEmployees
        | dev.Req_ListCustomers
        | dev.Req_GetCustomer
        | dev.Req_GetEmployee
        | dev.Req_GetProject
        | dev.Req_GetTimeEntry
        | dev.Req_SearchProjects
        | dev.Req_SearchEmployees
        | dev.Req_LogTimeEntry
        | dev.Req_SearchTimeEntries
        | dev.Req_SearchCustomers
        | dev.Req_UpdateTimeEntry
        | dev.Req_UpdateProjectTeam
        | dev.Req_UpdateProjectStatus
        | dev.Req_UpdateEmployeeInfo
        | dev.Req_TimeSummaryByProject
        | dev.Req_TimeSummaryByEmployee
    ) = Field(..., description="execute first remaining step")


CLI_RED = "\x1b[31m"
CLI_GREEN = "\x1b[32m"
CLI_BLUE = "\x1b[34m"
CLI_CLR = "\x1b[0m"


def run_agent(model: str, api: ERC3, task: TaskInfo):
    store_api = api.get_erc_dev_client(task)
    about = store_api.who_am_i()

    system_prompt = f"""
You are a business assistant helping customers of Aetherion.

# Security & Privacy Rules
1. **Guests (no account)**: Respond ONLY with public-safe data. REFUSE requests for internal IDs (project/employee IDs), internal structure, or specific employee details with `outcome='denied_security'`.
2. **Internal IDs**: Employee IDs are internal system data. REFUSE requests for Employee IDs (even for the CEO) with `outcome='denied_security'`.
3. **Salaries**: Salary data is CONFIDENTIAL. REFUSE requests for salary (individual or total) with `outcome='denied_security'`, unless the user is explicitly in 'Executive Leadership' or 'HR'. Project leads do NOT have access to salaries.
4. **Data Deletion**: Requests to wipe data/delete accounts must be DENIED (`outcome='denied_security'`) as they require compliance review.
5. **Access Control**: Operate strictly within the user's access level.
   - Executives: Broad access.
   - Project Leads: Can write/update ONLY projects they lead.
   - Team Members: Read access to their projects.
   - If a user asks to modify a project they do not lead (or you cannot find), DENY with `outcome='denied_security'`.

# Tool Usage Guidelines
- **Logging Time**: CRITICAL! Use `Req_LogTimeEntry` to log time. NEVER use `Req_TimeSummary...` for logging (those are for reading).
- **Unsupported Features**: If the user asks for a feature not supported by the API (e.g., "add system dependency"), respond with `outcome='none_unsupported'`.
- **Project Search**: If a project is not found, try searching again with `include_archived=True`.
- **Links**: Include `links` to ALL entities involved (Employee, Project, Customer). If an action was performed (update, log time), include the acting user in the links as well.
- **Updating Employees**: ALWAYS use `Req_GetEmployee` (by ID) first to get the FULL profile. Then use `Req_UpdateEmployeeInfo` passing ALL existing values back.
- **Pagination**: Always use `limit=5` for lists and searches.

# Current user info:
{about.model_dump_json()}
"""
    if about.current_user:
        usr = store_api.get_employee(about.current_user)
        system_prompt += f"\n{usr.model_dump_json()}"

    log = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task.task_text},
    ]

    for i in range(20):
        step = f"step_{i + 1}"
        print(f"Next {step}... ", end="")

        started = time.time()

        log_to_file(task.task_id, f"Input Messages for {step}:\n{json.dumps(log, indent=2)}")

        completion = get_client().beta.chat.completions.parse(
            model=model,
            response_format=NextStep,
            messages=log,
            max_completion_tokens=4096,
        )

        completion_text = _extract_completion_text(completion.choices[0].message)
        prompt_tokens, cached_prompt_tokens, completion_tokens = _extract_token_usage(
            completion.usage
        )

        api.log_llm(
            task_id=task.task_id,
            completion=completion_text,
            model=model,
            duration_sec=time.time() - started,
            prompt_tokens=prompt_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            completion_tokens=completion_tokens,
        )

        job = completion.choices[0].message.parsed

        print(job.plan_remaining_steps_brief[0], f"\n  {job.function}")

        log.append(
            {
                "role": "assistant",
                "content": job.plan_remaining_steps_brief[0],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": step,
                        "function": {
                            "name": job.function.__class__.__name__,
                            "arguments": job.function.model_dump_json(),
                        },
                    }
                ],
            }
        )

        try:
            result = store_api.dispatch(job.function)
            txt = result.model_dump_json(exclude_none=True, exclude_unset=True)
            print(f"{CLI_GREEN}OUT{CLI_CLR}: {txt}")
        except ApiException as e:
            txt = e.detail

            print(f"{CLI_RED}ERR: {e.api_error.error}{CLI_CLR}")

        if isinstance(job.function, dev.Req_ProvideAgentResponse):
            print(
                f"{CLI_BLUE}agent {job.function.outcome}{CLI_CLR}. Summary:\n{job.function.message}"
            )

            for link in job.function.links:
                print(f"  - link {link.kind}: {link.id}")

            break

        log.append({"role": "tool", "content": txt, "tool_call_id": step})
