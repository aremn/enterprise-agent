import argparse
import json
import os
import textwrap
import time

from erc3 import ERC3

from codegen_agent import run_agent


def main():
    parser = argparse.ArgumentParser(
        description="Run codegen agent on ERC3 benchmark with logging."
    )
    parser.add_argument("--model", default="gpt-5.1", help="Model ID to use.")
    parser.add_argument("--benchmark", default="erc3-prod", help="Benchmark name.")
    parser.add_argument("--workspace", default="my", help="Workspace name.")
    parser.add_argument(
        "--specs",
        default="",
        help="Comma-separated list of spec_ids to run; empty means run all tasks in session.",
    )
    parser.add_argument(
        "--flags",
        default="compete_accuracy",
        help="Comma-separated session flags (e.g. compete_accuracy,compete_speed). Use empty to skip flags.",
    )
    args = parser.parse_args()

    core = ERC3()
    MODEL_ID = args.model

    flags = [f.strip() for f in args.flags.split(",") if f.strip()]

    res = core.start_session(
        benchmark=args.benchmark,
        workspace=args.workspace,
        name=f"Enterprise agent ({MODEL_ID})",
        architecture="Python code generation with OpenAI",
        flags=flags,
    )

    status = core.session_status(res.session_id)
    print(f"Session has {len(status.tasks)} tasks")

    include_specs = {s.strip() for s in args.specs.split(",") if s.strip()}
    if include_specs:
        tasks = [t for t in status.tasks if t.spec_id in include_specs]
        print(f"Filtering to {len(tasks)} tasks by spec_id: {', '.join(include_specs)}")
    else:
        tasks = status.tasks

    log_root = os.path.join(os.path.dirname(__file__), "logs", "runs")
    os.makedirs(log_root, exist_ok=True)
    run_dir = os.path.join(log_root, f"session-{res.session_id}")
    os.makedirs(run_dir, exist_ok=True)

    def log_line(msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(run_dir, "run.log"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")

    def log_task_json(payload: dict):
        with open(os.path.join(run_dir, "tasks.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    log_line(
        f"Session start: {res.session_id}, tasks_total={len(status.tasks)}, tasks_run={len(tasks)}, model={MODEL_ID}"
    )

    for task in tasks:
        print("=" * 40)
        print(f"Starting Task: {task.task_id} ({task.spec_id}): {task.task_text}")
        start_ts = time.time()
        core.start_task(task)
        try:
            run_agent(MODEL_ID, core, task, quiet=True, log_dir=run_dir)
        except Exception as e:
            log_line(f"Task {task.task_id} error: {e}")
        result = core.complete_task(task)
        duration = time.time() - start_ts
        if result.eval:
            explain = textwrap.indent(result.eval.logs, "  ")
            print(f"\nSCORE: {result.eval.score}\n{explain}\n")
            log_line(
                f"Task {task.task_id} ({task.spec_id}) score={result.eval.score} duration={duration:.2f}s"
            )
            log_line(f"Eval logs:\n{explain}")
            log_task_json(
                {
                    "session_id": res.session_id,
                    "task_id": task.task_id,
                    "task_spec": task.spec_id,
                    "task_text": task.task_text,
                    "score": result.eval.score,
                    "duration_sec": duration,
                    "eval_logs": result.eval.logs,
                }
            )
        else:
            log_line(
                f"Task {task.task_id} ({task.spec_id}) completed without eval, duration={duration:.2f}s"
            )

    core.submit_session(res.session_id)
    log_line(f"Session end: {res.session_id}")


if __name__ == "__main__":
    main()
