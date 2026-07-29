"""Agent状态管理"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime


class AgentStatus(Enum):
    """Agent会话状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class AgentPhase(Enum):
    """Agent执行阶段"""
    THINKING = "thinking"
    RETRIEVING = "retrieving"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    CONCLUDING = "concluding"


@dataclass
class AgentStep:
    """Agent执行步骤"""
    step_number: int
    phase: AgentPhase
    thought: str = ""
    action: Optional[Dict] = None
    observation: str = ""
    knowledge_refs: List[Dict] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return {
            "step_number": self.step_number,
            "phase": self.phase.value,
            "thought": self.thought,
            "action": self.action,
            "observation": self.observation,
            "knowledge_refs": self.knowledge_refs,
            "timestamp": self.timestamp
        }


class AgentState:
    """Agent状态管理器"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.status = AgentStatus.IDLE
        self.current_step = 0
        self.max_steps = 10
        self.steps: List[AgentStep] = []
        self.conversation_history: List[Dict] = []
        self.error_message = ""

    def add_step(self, phase: AgentPhase, thought: str = "",
                 action: Optional[Dict] = None, observation: str = "",
                 knowledge_refs: Optional[List[Dict]] = None):
        """添加执行步骤"""
        step = AgentStep(
            step_number=self.current_step,
            phase=phase,
            thought=thought,
            action=action,
            observation=observation,
            knowledge_refs=knowledge_refs or [],
            timestamp=datetime.now().isoformat()
        )
        self.steps.append(step)
        return step

    def next_step(self):
        """进入下一步"""
        self.current_step += 1

    def set_status(self, status: AgentStatus):
        """设置状态"""
        self.status = status

    def set_error(self, error: str):
        """设置错误"""
        self.status = AgentStatus.ERROR
        self.error_message = error

    def add_message(self, role: str, content: str):
        """添加对话历史"""
        self.conversation_history.append({
            "role": role,
            "content": content
        })

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "steps": [s.to_dict() for s in self.steps],
            "error_message": self.error_message
        }

    def get_summary(self) -> str:
        """获取执行摘要"""
        phases = [s.phase.value for s in self.steps]
        return f"Agent执行: {len(self.steps)}步, 阶段: {' -> '.join(phases)}"
