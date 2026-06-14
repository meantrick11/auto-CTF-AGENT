"""Main orchestrator — wires all components and drives the agent loop."""

import json
import os

from blackboard.blackboard import Blackboard
from commander.agent import Commander
from config import create_client
from workers.base_worker import TaskResult
from workers.registry import get_worker_registry
from workers.web.agent import WebWorker
from hooks import fire

# Register Supervisor hooks (side-effect on import)
# Replaces: guardrail/ + filter/ + evaluator/ — all converged into supervisor/
import supervisor  # noqa: F401
from supervisor import init_supervisor, should_compact as supervisor_should_compact
from supervisor import get_observer_notes as supervisor_get_observer_notes


class Engine:
    """Central orchestrator managing the Commander-Worker-Blackboard loop.

    Hook points (7 total):
      before_plan, after_plan, before_task_create,
      before_execute, after_execute, on_finding, on_complete
    """

    def __init__(self, model: str | None = None,
                 max_rounds: int = 10, data_dir: str = "data"):
        self.model = model
        self.max_rounds = max_rounds
        self._data_dir = data_dir
        self.blackboard = Blackboard(data_dir=data_dir)
        self.commander = Commander(model=model)

        # Register domain workers in global registry
        reg = get_worker_registry()#注册workers到全局workers registry中，指定任务前缀为web_，这样当commander创建任务时，如果任务类型以web_开头，就会被路由到这个worker执行
        reg.register(WebWorker(model=model), name="web_worker",
                     domain="web", task_prefixes=["web_"])
        self._round = 0

    def run(self, goal: str) -> dict:
        """Execute the full agent loop for a given goal."""
        self._log(f"=== Mission Start ===")
        self._log(f"Goal: {goal}")

        # Phase 0: Clear old state
        filepath = os.path.join(self._data_dir, "blackboard.json")##黑板的存储路径
        if os.path.exists(filepath):
            os.remove(filepath)#如果路径存在，则删除旧黑板
        self.blackboard = Blackboard(data_dir=self._data_dir)#create new blackboard instance to reset state
        init_supervisor()#reset supervisor state for new mission

        # Phase 1: Initialize
        self.blackboard.create_goal(goal)#初始化向黑板添加目标

        # Phase 2: Main loop
        for self._round in range(1, self.max_rounds + 1):#外层大循环，设定了默认为12轮
            self._log(f"\n--- Round {self._round}/{self.max_rounds} ---")

            # ── Hook: before_plan ──
            snapshot = self.blackboard.snapshot()#获取当前黑板的现状
            ## hook1：before_plan，在Commander做下一次决策前触发，提供当前黑板快照，
            ## 然后交给Guarddrail判断目标是否合法？
            ev = fire("before_plan", snapshot=snapshot, round=self._round)
            if ev.blocked:#如果被过滤器阻止了计划生成，则直接结束任务，返回失败报告
                self._log(f"[BLOCKED] before_plan: {ev.block_reason}")
                return self._build_report("failed", ev.block_reason)
            ## hook1没有生效，则，进行commander的计划生成，得到决策结果
            commander_view = self.blackboard.get_commander_view()
            commander_view["observer_notes"] = supervisor_get_observer_notes()
            decision = self.commander.plan(commander_view)

            # ── Hook: after_plan ──
            ## hook2：after_plan，logging hook,在Commander做出决策后触发，提供决策结果和当前黑板快照，logging记录commander的决策
            fire("after_plan", snapshot=snapshot, decision=decision, round=self._round)
            #记录commander的决策descision+reasoning的前120字符
            self._log(f"Commander decision: {decision.decision}")
            self._log(f"Reasoning: {decision.reasoning[:120]}")
            #检查是否有completed/failed的决策，如果有，则结束任务，返回报告
            if decision.decision in ("completed", "failed"):
                self.blackboard.update_goal_status(decision.decision)#跟新黑板状态
                final_summary = decision.final_summary#最后总结
                self._log(f"\n=== Mission {decision.decision.upper()} ===")
                self._log(final_summary)
                report = self._build_report(decision.decision, final_summary)
                # ── Hook: on_complete ──
                ## hook7,on_complete,在任务完成之后触发，记录最后决策和最终报告
                fire("on_complete", outcome=decision.decision, report=report)
                return report#返回report报告

            # Publish new tasks
            #获取commander传递的decision{}字典任务并根据Guardrail的判断，决定是否在黑板上创建任务   
            for task_def in decision.new_tasks:
                # ── Hook: before_task_create ──
                ## hook3：before_task_create，task_check_hook,在Commander创建任务后写入黑板前触发,交给Guardrail，检查分发的任务是否合法？
                ev = fire("before_task_create", task_def=task_def)
                if ev.blocked:#如果当前任务被Guardrail判定为非法，则记录并跳过执行
                    self._log(f"[BLOCKED] before_task_create: {ev.block_reason}")
                    continue
                #如果创建任务合法，在黑板上创建任务，等待后续执行
                self.blackboard.create_task(
                    type=task_def["type"],
                    instruction=task_def["instruction"],
                    input_data=task_def.get("input_data", {}),
                )

            # Execute pending tasks
            pending = self.blackboard.get_pending_tasks()#检查是否有待执行的任务？
            if not pending:
                self._log("No pending tasks — Commander did not create any.")
                continue

            for task in pending:#如果有没有完成的任务，则交给_execute_task()方法执行任务
                self._execute_task(task)

            self._maybe_compact()

        # Max rounds reached
        ##如果上述循环达到最大轮数限制，仍未完成任务，则记录并返回失败报告
        self._log(f"\n=== Max rounds ({self.max_rounds}) reached ===")
        self.blackboard.update_goal_status("failed")#更新黑板状态
        report = self._build_report("failed", "Max rounds reached without finding flag")
        ## hook7,on_complete，在任务失败时候触发，提供最终报告，记录任务失败的结果
        fire("on_complete", outcome="failed", report=report)
        return report

    def _execute_task(self, task: dict):
        '''Execute a single task by routing to the appropriate worker.'''
        task_id = task["id"]#获取·任务id和任务类型
        task_type = task["type"]

        worker = self._route_task(task_type)#根据任务类型路由到对应的worker执行
        #如果没有worker能处理这个任务，则记录并标记任务失败
        if worker is None:
            self._log(f"No worker for task type: {task_type}, skipping task {task_id}")
            self.blackboard.complete_task(task_id, {"error": "No suitable worker"}, "failed")#记录没有合适的worker到黑板上
            return
        #根据任务id+worker name 使用assign_task分配任务
        self.blackboard.assign_task(task_id, worker.name)
        self.blackboard.start_task(task_id)#标记任务开始执行

        # ── Hook: before_execute ──
        ## hook4 before_execute,task_safety_check_again,任务已经分发，具体的worker执行之前触发，Guardrail最后一次检查任务是否合法？
        ev = fire("before_execute", task=task, worker_name=worker.name)
        #如果被Guardrail判定为非法，则记录并退出任务执行，标记任务失败
        if ev.blocked:
            self._log(f"[BLOCKED] before_execute: {ev.block_reason}")
            self.blackboard.complete_task(task_id, {"error": ev.block_reason}, "failed")
            return
        #如果合法，则记录任务类型+worker name+任务指令的前100字符，并调用worker的execute方法执行任务，传入任务和当前黑板快照
        self._log(f"Executing [{task_type}] → {worker.name}: {task['instruction'][:100]}")
        #交给对应的worker执行（传入黑板快照，？
        result = worker.execute(task, self.blackboard.snapshot())

        # ── Hook: after_execute (Filter can modify result) ──
        ## hook5 after_execute,task_result_filter,执行之后触发，提供任务、执行结果和当前黑板快照，交给Filter过滤器检查结果是否合法？如果不合法，则可以修改结果或者标记任务失败
        ev = fire("after_execute", task=task, result=result)
        result = ev.data.get("result", result)

        # Normalize: TaskResult → dict access for uniform handling
        if isinstance(result, TaskResult):#返回如果是TaskResult对象，则提取findings、status、summary和output_data属性；如果是dict，则直接从字典中获取这些字段
            findings = result.findings
            status = result.status
            summary = result.summary
            output_data = result.output_data
        else:#如果直接是dict
            findings = result.get("findings", [])
            status = result.get("status", "completed")
            summary = result.get("summary", "")
            output_data = result.get("output_data", {})

        for finding in findings:
            if isinstance(finding, dict):
                finding["source_task_id"] = task_id
            else:
                finding.source_task_id = task_id

            # ── Hook: on_finding 
            ## hook6 on_finding事件，
            ev = fire("on_finding", finding=finding, task_id=task_id)
            if ev.blocked:
                continue

            # Convert to dict for blackboard (WorkerFinding → dict)
            #将发现都转为dict形式，以便存储到黑板上，如果发现已经是dict了，则直接使用；如果是WorkerFinding对象，则提取type、title、data、confidence和source_task_id属性构建成dict
            if not isinstance(finding, dict):
                finding = {
                    "type": finding.type,
                    "title": finding.title,
                    "data": finding.data,
                    "confidence": finding.confidence,
                    "source_task_id": finding.source_task_id,
                }
            
            added = self.blackboard.add_finding(finding)#添加，并返回True/False表示是否是新发现
            if added is not None:
                self._log(f"  Finding: [{finding['type']}] {finding['title']}")
            else:
                self._log(f"  (dup) [{finding['type']}] {finding['title']}")

        # Complete task — include error_detail for Commander visibility
        task_output = {
            "summary": summary,
            "raw_output": output_data,
        }
        if isinstance(result, TaskResult) and result.error_detail:
            task_output["error_detail"] = result.error_detail

        self.blackboard.complete_task(
            task_id,
            task_output,
            status,
        )
        if status == "failed" and task_output.get("error_detail"):
            ed = task_output["error_detail"]
            self._log(f"  Task {task_id}: failed ({ed.get('error_type')}: {ed.get('detail', '')[:80]})")
        else:
            self._log(f"  Task {task_id}: {status}")

    def _route_task(self, task_type: str):
        '''Route a task type to the appropriate worker using the registry. First try exact match, then fallback to any worker willing to try.'''
        reg = get_worker_registry()
        worker = reg.route(task_type)#根据注册表和任务类型，找到合适的worker执行任务，首先尝试完全匹配任务类型，如果没有找到，则尝试任何愿意尝试的worker（例如web_worker），如果仍然没有找到，则返回None
        if worker is not None:
            return worker
        # Fallback: any worker willing to try
        #兜底至少返回一个worker，例如web_worker，允许它尝试执行任何没有明确worker的任务
        return reg.get("web_worker")

    def _maybe_compact(self):
        """Trigger LLM compaction when findings accumulate past threshold."""
        if not supervisor_should_compact(self.blackboard.get_findings()):
            return
        self._log("[Compact] Findings threshold exceeded, generating summary...")
        client = create_client(self.model)
        self.blackboard.compact(client, model=self.model)
        summary = self.blackboard._situation_summary
        if summary:
            self._log(
                f"[Compact] Summary generated: "
                f"{summary.get('summary', '')[:100]}"
            )

    def _build_report(self, outcome: str, summary: str) -> dict:
        '''Construct&return the final report with outcome, summary, findings, flag, and task history.'''
        return {
            "outcome": outcome,
            "summary": summary,
            "total_rounds": self._round,
            "findings": self.blackboard.get_findings(),
            "flag": self._extract_flag(),
            "task_history": self.blackboard.get_all_tasks(),
            "event_log": self.blackboard.get_recent_events(100),
        }

    def _extract_flag(self) -> str:
        '''Heuristic to extract flag from findings. '''
        import re
        #获取黑板中所有类型位flag的finding，对于每个finding，都检查它的data字段
        for f in self.blackboard.get_findings_by_type("flag"):
            data = f.get("data", {})
            #第一层，如果直接匹配到flag字段、decoded字段、value字段或者result字段，并且这些字段有值，则直接返回这个值作为flag
            for key in ("flag", "decoded", "value", "result"):
                if key in data and data[key]:
                    return str(data[key])
            #第二层，直接匹配都没有匹配到上述字段，那么对data中所有值进行正则匹配
            for v in data.values():
                if isinstance(v, str):#判断是否是字符串，如果是字符串，则使用正则表达式匹配CTF或者flag格式的字符串，如果匹配到，则返回这个字符串作为flag    
                    m = re.search(r"(?:CTF|flag)\{[^\}]+\}", v, re.IGNORECASE)
                    if m:
                        return m.group(0)#group(0)表示返回整个匹配到的字符串,group(1)表示返回第一个括号匹配到的字符串，以此类推，如果正则表达式中没有括号，那么group(0)就是整个匹配到的字符串
        #如果没有finding，或者finding中没有匹配到flag字段，也没有在data的值中匹配到flag格式的字符串，则返回空字符串
        return ""

    def _log(self, msg: str):
        '''print the log message'''
        print(msg)
