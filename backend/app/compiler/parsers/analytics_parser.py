"""Analytics Parser Sub-Parser Module (Section 9).

Parses Analytics Events & Telemetry KPIs:
  workflow_started, workflow_completed, workflow_failed, workflow_abandoned,
  step_completed, clarification_requested, escalation_triggered, KPIs.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import AnalyticsMetadata, AnalyticsEvent

logger = logging.getLogger("compiler.parser.analytics")


class AnalyticsParser:
    """Parses Section 9: Analytics Events."""

    @staticmethod
    def parse(markdown_text: str) -> AnalyticsMetadata:
        """Parses Section 9 analytics metadata."""
        an_dict: Dict[str, Any] = {}

        # 1. Check :::analytics block
        directive_match = re.search(r":::analytics\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            try:
                parsed_yaml = yaml.safe_load(directive_match.group(1))
                if isinstance(parsed_yaml, dict):
                    an_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse :::analytics block: {exc}")

        # 2. Check '# Analytics Events' section
        sec_match = re.search(r"#\s*(?:9\s*)?Analytics\s*(?:Events)?\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    an_dict[k.strip().lower().replace(" ", "_")] = v.strip().strip('"\'')

        events: List[AnalyticsEvent] = []
        default_events = [
            ("workflow_started", "SESSION_INIT", ["cycle_time_start"]),
            ("step_completed", "STEP_ACTION_CONFIRMED", ["step_execution_time"]),
            ("escalation_triggered", "SAFETY_OR_RETRY_BREACH", ["escalation_rate"]),
            ("workflow_completed", "TERMINAL_STATE_REACHED", ["total_completion_time"]),
        ]

        raw_events = an_dict.get("events")
        if isinstance(raw_events, list):
            for ev in raw_events:
                if isinstance(ev, dict):
                    events.append(
                        AnalyticsEvent(
                            event_name=str(ev.get("name") or ev.get("event_name")),
                            event_trigger=str(ev.get("trigger") or ev.get("event_trigger")),
                            kpis=[str(k).strip() for k in ev.get("kpis", [])],
                        )
                    )
        else:
            for name, trig, kpis in default_events:
                events.append(AnalyticsEvent(event_name=name, event_trigger=trig, kpis=kpis))

        def parse_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            if isinstance(val, str) and val.strip():
                return [x.strip() for x in val.split(",") if x.strip()]
            return ["first_pass_yield", "average_handling_time", "compliance_rate"]

        return AnalyticsMetadata(
            events=events,
            kpis=parse_list(an_dict.get("kpis")),
        )
