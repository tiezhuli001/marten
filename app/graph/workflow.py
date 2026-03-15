import re
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.graph.router import classify_intent
from app.graph.state import WorkflowState
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GatewayMessageRequest,
    GatewayMessageResponse,
    SleepCodingTaskRequest,
    TokenUsage,
)
from app.services.observability import LangSmithService
from app.services.sleep_coding import SleepCodingService


class WorkflowRunner:
    def __init__(self) -> None:
        settings = get_settings()
        self.langsmith = LangSmithService(settings)
        self.ledger = TokenLedgerService(settings)
        self.sleep_coding = SleepCodingService(settings=settings, ledger=self.ledger)
        self.graph = self._build_graph().compile()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(WorkflowState)
        graph.add_node("intent_classifier", self._intent_classifier)
        graph.add_node("general_handler", self._general_handler)
        graph.add_node("stats_query_handler", self._stats_query_handler)
        graph.add_node("sleep_coding_handler", self._sleep_coding_handler)
        graph.add_node("token_ledger", self._token_ledger)
        graph.add_node("response_formatter", self._response_formatter)

        graph.add_edge(START, "intent_classifier")
        graph.add_conditional_edges(
            "intent_classifier",
            self._route_from_intent,
            {
                "general_handler": "general_handler",
                "stats_query_handler": "stats_query_handler",
                "sleep_coding_handler": "sleep_coding_handler",
            },
        )
        graph.add_edge("general_handler", "token_ledger")
        graph.add_edge("stats_query_handler", "token_ledger")
        graph.add_edge("sleep_coding_handler", "token_ledger")
        graph.add_edge("token_ledger", "response_formatter")
        graph.add_edge("response_formatter", END)
        return graph

    def run(self, payload: GatewayMessageRequest) -> GatewayMessageResponse:
        request_id = str(uuid4())
        run_id = str(uuid4())
        initial_state: WorkflowState = {
            "request_id": request_id,
            "run_id": run_id,
            "user_id": payload.user_id,
            "source": payload.source,
            "content": payload.content,
            "intent": "general",
            "message": "",
            "token_usage": TokenUsage(),
            "task_id": None,
        }
        with self.langsmith.request_trace(
            request_id=request_id,
            run_id=run_id,
            user_id=payload.user_id,
        ):
            result = self.graph.invoke(initial_state)
        return GatewayMessageResponse(
            request_id=result["request_id"],
            intent=result["intent"],
            message=result["message"],
            token_usage=result["token_usage"],
        )

    def _intent_classifier(self, state: WorkflowState) -> WorkflowState:
        state["intent"] = classify_intent(state["content"])
        return state

    def _route_from_intent(self, state: WorkflowState) -> str:
        mapping = {
            "general": "general_handler",
            "stats_query": "stats_query_handler",
            "sleep_coding": "sleep_coding_handler",
        }
        return mapping[state["intent"]]

    def _general_handler(self, state: WorkflowState) -> WorkflowState:
        state["message"] = "General intent received. Workflow skeleton is ready."
        return state

    def _stats_query_handler(self, state: WorkflowState) -> WorkflowState:
        summary = self.ledger.get_usage_summary(query=state["content"])
        state["message"] = summary
        return state

    def _sleep_coding_handler(self, state: WorkflowState) -> WorkflowState:
        match = re.search(r"\b(\d+)\b", state["content"])
        if match is None:
            state["message"] = (
                "Sleep coding intent recognized. Provide an issue number or call POST /tasks/sleep-coding directly."
            )
            return state

        task = self.sleep_coding.start_task(
            SleepCodingTaskRequest(
                issue_number=int(match.group(1)),
                request_id=state["request_id"],
            )
        )
        state["task_id"] = task.task_id
        state["message"] = (
            f"Sleep coding task {task.task_id} is ready for review. "
            f"Status={task.status}, branch={task.head_branch}."
        )
        return state

    def _token_ledger(self, state: WorkflowState) -> WorkflowState:
        state["token_usage"] = self.ledger.record_request(
            request_id=state["request_id"],
            run_id=state["run_id"],
            user_id=state["user_id"],
            source=state["source"],
            intent=state["intent"],
            content=state["content"],
        )
        return state

    def _response_formatter(self, state: WorkflowState) -> WorkflowState:
        return state
