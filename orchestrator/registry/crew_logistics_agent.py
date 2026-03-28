#!/usr/bin/env python3
"""
TPP Logistics Crew Agent — AetherEdge Registry Script

Simulates a CrewAI-style multi-agent logistics analysis crew running on the edge node.
Uses a MockLLM so it runs without any API key.

To upgrade to real CrewAI + Claude:
  1. pip install crewai langchain-anthropic
  2. Set ANTHROPIC_API_KEY in your environment
  3. Replace the MockCrew section below with the "# REAL CREWAI" block
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

# ── Simulated shipment data ───────────────────────────────────────────────────
# In production this would be fetched from TPP_API_ENDPOINT/shipments/pending
MOCK_SHIPMENTS = [
    {"id": "SHP-001", "origin": "Mumbai",  "destination": "Delhi",     "status": "in_transit", "delay_hours": 2},
    {"id": "SHP-002", "origin": "Chennai", "destination": "Bangalore", "status": "delayed",    "delay_hours": 8},
    {"id": "SHP-003", "origin": "Kolkata", "destination": "Hyderabad", "status": "on_time",    "delay_hours": 0},
    {"id": "SHP-004", "origin": "Pune",    "destination": "Mumbai",    "status": "delayed",    "delay_hours": 14},
]


# ── Mock Crew (no API key needed) ─────────────────────────────────────────────

class _MockAgent:
    def __init__(self, role: str, goal: str, backstory: str):
        self.role = role
        self.goal = goal
        self.backstory = backstory

    def __repr__(self):
        return f"Agent(role={self.role!r})"


class _MockTask:
    def __init__(self, description: str, agent: _MockAgent, expected_output: str):
        self.description = description
        self.agent = agent
        self.expected_output = expected_output


class _MockCrew:
    """
    Mimics CrewAI's Crew.kickoff() interface.
    Replace with real CrewAI when ANTHROPIC_API_KEY is available.
    """

    def __init__(self, agents: list, tasks: list):
        self.agents = agents
        self.tasks = tasks

    def kickoff(self) -> str:
        # ── Analyst agent logic (mocked) ──────────────────────────────────────
        delayed     = [s for s in MOCK_SHIPMENTS if s["status"] == "delayed"]
        on_time     = [s for s in MOCK_SHIPMENTS if s["status"] == "on_time"]
        in_transit  = [s for s in MOCK_SHIPMENTS if s["status"] == "in_transit"]

        avg_delay = (
            sum(s["delay_hours"] for s in delayed) / len(delayed)
            if delayed else 0
        )

        # ── Reporter agent logic (mocked) ─────────────────────────────────────
        if avg_delay >= 10:
            severity = "HIGH"
            recommendation = "Escalate to operations team. Arrange expedited carriers for critical routes."
        elif avg_delay >= 4:
            severity = "MEDIUM"
            recommendation = "Notify affected customers. Monitor closely for further delays."
        else:
            severity = "LOW"
            recommendation = "Operations nominal. Continue standard monitoring."

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "node_id": os.environ.get("AETHER_NODE_ID", "unknown"),
            "summary": {
                "total_shipments": len(MOCK_SHIPMENTS),
                "on_time":         len(on_time),
                "in_transit":      len(in_transit),
                "delayed":         len(delayed),
                "avg_delay_hours": round(avg_delay, 1),
                "severity":        severity,
            },
            "delayed_shipments": [
                {
                    "id":           s["id"],
                    "route":        f"{s['origin']} → {s['destination']}",
                    "delay_hours":  s["delay_hours"],
                }
                for s in delayed
            ],
            "recommendation": recommendation,
            "agents_used": [a.role for a in self.agents],
            "llm_mode": "mock — set ANTHROPIC_API_KEY to enable real CrewAI",
        }

        return json.dumps(report, indent=2)


# ── REAL CREWAI (uncomment when ANTHROPIC_API_KEY is set) ────────────────────
# from crewai import Agent, Task, Crew
# from langchain_anthropic import ChatAnthropic
#
# llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0.2)
#
# def _build_real_crew():
#     analyst = Agent(
#         role="Logistics Analyst",
#         goal="Analyse pending shipments and identify delays and bottlenecks.",
#         backstory="Expert in supply chain analytics with 10 years in logistics.",
#         llm=llm, verbose=False,
#     )
#     reporter = Agent(
#         role="Operations Reporter",
#         goal="Summarise findings into a concise JSON report for the operator.",
#         backstory="Specialist in turning raw data into actionable business intelligence.",
#         llm=llm, verbose=False,
#     )
#     analyse_task = Task(
#         description=f"Analyse these shipments and flag delays: {json.dumps(MOCK_SHIPMENTS)}",
#         agent=analyst,
#         expected_output="Bullet-point summary of delays and root causes.",
#     )
#     report_task = Task(
#         description="Produce a JSON report with summary stats and a recommendation.",
#         agent=reporter,
#         expected_output="Valid JSON with keys: summary, delayed_shipments, recommendation.",
#     )
#     return Crew(agents=[analyst, reporter], tasks=[analyse_task, report_task])
# ─────────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  TPP Logistics Crew Agent")
    print("  AetherEdge Sovereign AI Worker")
    print("=" * 60)

    # ── Build crew ────────────────────────────────────────────────────────────
    analyst = _MockAgent(
        role="Logistics Analyst",
        goal="Analyse pending shipments and identify delays.",
        backstory="Expert in supply chain analytics.",
    )
    reporter = _MockAgent(
        role="Operations Reporter",
        goal="Produce a concise JSON report for the operator.",
        backstory="Specialist in actionable business intelligence.",
    )
    analyse_task = _MockTask(
        description="Analyse shipments and flag delays.",
        agent=analyst,
        expected_output="Delay summary with severity.",
    )
    report_task = _MockTask(
        description="Produce a JSON operations report.",
        agent=reporter,
        expected_output="JSON with summary and recommendation.",
    )

    crew = _MockCrew(agents=[analyst, reporter], tasks=[analyse_task, report_task])

    print(f"\n[Crew] Agents: {[a.role for a in crew.agents]}")
    print(f"[Crew] Tasks : {len(crew.tasks)}")
    print("\n[Crew] Kickoff...\n")

    result = crew.kickoff()

    print("[Crew] Report:")
    print(result)
    print("\n[Crew] Done.")


if __name__ == "__main__":
    main()
