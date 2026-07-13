"""执行痕迹追踪。每一步都留痕,出问题能查。"""
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from schemas import StepTrace


class Tracer:
    """简单的步骤追踪器。

    用法:
        tracer = Tracer(verbose=True, log_dir="./logs")
        with tracer.step("anchor_facts") as t:
            t.set_input("原文长度: 500字")
            result = do_something()
            t.set_output(f"抽到 {len(result.tools)} 个工具")
    """

    def __init__(self, verbose: bool = False, log_dir: Optional[str] = None,
                 run_id: str = ""):
        self.verbose = verbose
        self.run_id = run_id
        self.traces: list[StepTrace] = []

        # 日志配置
        self.logger = logging.getLogger(f"agent.{run_id}")
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        # 避免重复 handler
        if not self.logger.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S",
            ))
            self.logger.addHandler(h)

            if log_dir:
                Path(log_dir).mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(
                    Path(log_dir) / f"{run_id or 'run'}.log",
                    encoding="utf-8",
                )
                fh.setFormatter(logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(message)s"
                ))
                self.logger.addHandler(fh)

    @contextmanager
    def step(self, name: str):
        """上下文管理器,自动记录开始/结束/耗时/异常。"""
        from datetime import datetime
        trace = StepTrace(
            step_name=name,
            started_at=datetime.now().isoformat(),
            duration_ms=0,
            success=False,
        )
        start = time.time()
        self.logger.info(f"→ {name} START")
        try:
            yield trace
            trace.success = True
            self.logger.info(f"← {name} OK ({int((time.time()-start)*1000)}ms)")
        except Exception as e:
            trace.success = False
            trace.error = f"{type(e).__name__}: {e}"
            self.logger.error(f"× {name} FAIL: {trace.error}")
            raise
        finally:
            trace.duration_ms = int((time.time() - start) * 1000)
            if self.verbose:
                self.logger.debug(f"  input: {trace.input_summary[:200]}")
                self.logger.debug(f"  output: {trace.output_summary[:200]}")
            self.traces.append(trace)

    def info(self, msg: str):
        self.logger.info(msg)

    def warn(self, msg: str):
        self.logger.warning(msg)


# 给 StepTrace 加方便方法
def _set_input(self: StepTrace, s: str):
    self.input_summary = s
    return self


def _set_output(self: StepTrace, s: str):
    self.output_summary = s
    return self


def _add_issue(self: StepTrace, s: str):
    self.issues.append(s)
    return self


StepTrace.set_input = _set_input
StepTrace.set_output = _set_output
StepTrace.add_issue = _add_issue