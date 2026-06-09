import threading
import uuid
import logging
from enum import Enum, auto
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass

from .protocol import unwrap_rtvi_envelope

logger = logging.getLogger("EvaSharedFSM")

# --- Pure FSM Events ---

@dataclass
class ConfigUpdateEvent:
    valid_tasks: List[str]

@dataclass
class SwitchApprovedEvent:
    command_id: str

@dataclass
class SwitchDeniedEvent:
    reason: str

@dataclass
class SwitchAdviceEvent:
    advice_id: str
    suggested_task: str
    confidence: float

# --- Pure FSM ---

class TaskFSMState(Enum):
    IDLE = auto()
    ACTIVE = auto()
    PENDING_SWITCH = auto()

class TaskFSM:
    """
    Pure Finite State Machine for task state management.
    Does not know about JSON or RTVI protocols.
    """
    def __init__(self, on_task_change: Optional[Callable[[str, str], None]] = None):
        self.state = TaskFSMState.IDLE
        self.current_task: Optional[str] = None
        self.pending_task: Optional[str] = None
        self.revision = 0
        self.allowed_tasks: List[str] = []
        self._on_task_change = on_task_change
        self._lock = threading.Lock()

    def initialize(self, initial_task: str):
        with self._lock:
            self.current_task = initial_task
            self.state = TaskFSMState.ACTIVE
            logger.info(f"[TaskFSM] Initialized with task: {initial_task}")

    def on_config_update(self, event: ConfigUpdateEvent):
        with self._lock:
            self.allowed_tasks = event.valid_tasks
            logger.info(f"[TaskFSM] Config updated. Allowed tasks: {self.allowed_tasks}")

    def request_switch(self, target_task: str) -> bool:
        """Returns True if the switch request is valid and state transitioned to PENDING_SWITCH."""
        with self._lock:
            if self.allowed_tasks and target_task not in self.allowed_tasks:
                logger.warning(f"[TaskFSM] Switch to {target_task} denied: not in allowed tasks")
                return False

            self.pending_task = target_task
            self.state = TaskFSMState.PENDING_SWITCH
            logger.info(f"[TaskFSM] Requested switch to {target_task}, state: PENDING_SWITCH")
            return True

    def on_switch_approved(self, event: SwitchApprovedEvent) -> bool:
        """Returns True if the switch was successfully applied."""
        with self._lock:
            if self.state != TaskFSMState.PENDING_SWITCH:
                logger.warning(f"[TaskFSM] Received switch approval but not in PENDING_SWITCH state.")
                return False
                
            old_task = self.current_task
            self.current_task = self.pending_task
            self.state = TaskFSMState.ACTIVE
            self.revision += 1
            self.pending_task = None
            
            logger.info(f"[TaskFSM] Switch approved: {old_task} -> {self.current_task} (revision {self.revision})")
            
        if self._on_task_change and old_task != self.current_task:
            try:
                self._on_task_change(old_task or "", self.current_task or "")
            except Exception as e:
                logger.error(f"[TaskFSM] Error in task change callback: {e}")
                
        return True

    def on_switch_denied(self, event: SwitchDeniedEvent):
        with self._lock:
            self.state = TaskFSMState.ACTIVE if self.current_task else TaskFSMState.IDLE
            self.pending_task = None
            logger.info(f"[TaskFSM] Switch denied: {event.reason}")

    def on_switch_advice(self, event: SwitchAdviceEvent, threshold: float) -> bool:
        """Returns True if the advice triggered an auto-switch."""
        if event.confidence <= threshold:
            return False
            
        with self._lock:
            old_task = self.current_task
            self.current_task = event.suggested_task
            self.state = TaskFSMState.ACTIVE
            self.revision += 1
            self.pending_task = None

            logger.info(f"[TaskFSM] Auto-switch triggered: {old_task} -> {self.current_task} (revision {self.revision})")

        if self._on_task_change and old_task != self.current_task:
            try:
                self._on_task_change(old_task or "", self.current_task or "")
            except Exception as e:
                logger.error(f"[TaskFSM] Error in task change callback: {e}")
                
        return True


# --- Protocol Adapter ---

class RTVITaskNegotiator:
    """
    Adapter that translates RTVI JSON messages into FSM Events,
    and FSM State changes into RTVI JSON Commands/Commits.
    """
    def __init__(self, on_task_change: Optional[Callable[[str, str], None]] = None, auto_switch_confidence_threshold: float = 0.8):
        self.fsm = TaskFSM(on_task_change=on_task_change)
        self.auto_switch_confidence_threshold = auto_switch_confidence_threshold

    def initialize(self, initial_task: str):
        self.fsm.initialize(initial_task)

    def handle_message(self, raw_message: dict) -> Optional[dict]:
        """Parses RTVI message, updates FSM, and optionally returns a payload to send."""
        message = unwrap_rtvi_envelope(raw_message)
        msg_type = message.get("type", "unknown")

        if msg_type == "system_config":
            event = ConfigUpdateEvent(valid_tasks=message.get("valid_tasks", []))
            self.fsm.on_config_update(event)
            return None

        if msg_type == "task.switch.result" or "approved" in message:
            approved = message.get("approved", False)
            if approved:
                event = SwitchApprovedEvent(command_id=message.get("id", ""))
                if self.fsm.on_switch_approved(event):
                    return self._build_commit_payload("edge_command", event.command_id)
            else:
                event = SwitchDeniedEvent(reason=message.get("reason", ""))
                self.fsm.on_switch_denied(event)
            return None

        if msg_type == "task.switch.advice" or "suggested_task" in message:
            event = SwitchAdviceEvent(
                advice_id=message.get("id", ""),
                suggested_task=message.get("suggested_task", ""),
                confidence=message.get("confidence", 0.0)
            )
            if self.fsm.on_switch_advice(event, self.auto_switch_confidence_threshold):
                return self._build_commit_payload("advice", event.advice_id)
            return None

        return None

    def request_switch(self, target_task: str, reason: str = "User Request") -> Optional[dict]:
        """Translates a switch request intent into an FSM state transition and an RTVI command payload."""
        if self.fsm.request_switch(target_task):
            return {
                "type": "task.switch.command",
                "id": f"cmd_{uuid.uuid4().hex[:8]}",
                "from_task": self.fsm.current_task or "",
                "to_task": target_task,
                "reason": reason,
                "revision": self.fsm.revision
            }
        return None

    def _build_commit_payload(self, ref_source: str, ref_id: str) -> dict:
        return {
            "type": "task.switch.commit",
            "id": f"commit_{uuid.uuid4().hex[:8]}",
            "final_task": self.fsm.current_task,
            "revision": self.fsm.revision,
            "ref_source": ref_source,
            "ref_id": ref_id
        }
