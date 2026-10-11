"""Operator UI. Approval is always revalidated by the backend."""
import httpx
import json
import streamlit as st


def render(base, page):
    token = st.sidebar.text_input("Local operator token", type="password", help="Required for operations; never stored in experiment records.")
    def call(path, body=None):
        try:
            with httpx.Client(timeout=90, trust_env=False) as client:
                response = client.get(base + path) if body is None else client.post(base + path, json=body, headers={"Authorization": "Bearer " + token})
                if response.status_code >= 400:
                    st.error(response.json().get("detail", "Request rejected"))
                    return None
                return response.json()
        except (httpx.HTTPError, ValueError):
            st.error("Backend unavailable or invalid response")
            return None
    st.title(page)
    status = call("/api/agents/status")
    if not status:
        return
    st.caption("Real recorded events only. AI explanations are hypotheses; execution and verification are deterministic.")
    a, b, c = st.columns(3)
    a.metric("Analysis agent", status.get("analysis", "Unknown"))
    b.metric("Execution worker", "Connected" if status.get("worker_alive") else "Offline / unknown")
    c.metric("Kill switch", "Active" if status.get("kill_switch") else "Clear")
    st.info("Chaos execution: " + status.get("chaos", "Unknown"))
    with st.expander("Agent status and safety details"):
        st.json({key: value for key, value in status.items() if key != "timeline"}, expanded=False)
    st.button("Refresh recorded state")
    if page == "Chaos Engineering":
        recommendations = call("/api/chaos/recommendations") or []
        if recommendations:
            selected = st.selectbox("Analysis Agent recommendation", recommendations, format_func=lambda r: f"{r['component']}: {r['finding_id']}")
            st.json(selected, expanded=False)
            targets = st.multiselect("Explicit target services", [s["name"] for s in call("/api/services") or []], default=[selected["component"]])
            fault = st.selectbox("Fault adapter", status["supported_faults"] + status["unsupported_faults"])
            duration = st.number_input("Duration in seconds", min_value=1, max_value=60, value=15)
            if st.button("Prepare proposal (does not approve)"):
                result = call("/api/chaos/experiments/plan", {"source_finding_id": selected["finding_id"], "targets": targets, "fault_type": fault, "duration_seconds": duration})
                if result:
                    st.success("Proposal persisted. Review its exact contents below.")
        experiments = call("/api/chaos/experiments") or []
        for experiment in experiments:
            with st.expander(f"{experiment['id']} | {experiment['state']}"):
                st.json(experiment["proposal"])
                st.code(experiment["proposal_hash"], language=None)
                st.caption("All affected components need authorized readiness, dependency and functional baseline probes. Watchdog and rollback must be verified before execution.")
                confirmed = st.checkbox("I approve this exact proposal and its blast radius in the authorized disposable environment", key="confirm-" + experiment["id"])
                if st.button("Approve and Execute", key="approve-" + experiment["id"], disabled=not confirmed or experiment["state"] != "AWAIT_USER_APPROVAL"):
                    approved = call(f"/api/chaos/experiments/{experiment['id']}/approve", {"proposal_hash": experiment["proposal_hash"], "confirmation": "I APPROVE THIS EXACT EXPERIMENT"})
                    if approved:
                        queued = call(f"/api/chaos/experiments/{experiment['id']}/execute", {})
                        if queued:
                            st.success("Approved experiment queued for the separate worker")
                if st.button("Reject", key="reject-" + experiment["id"], disabled=experiment["state"] not in {"AWAIT_USER_APPROVAL", "APPROVED"}):
                    call(f"/api/chaos/experiments/{experiment['id']}/reject", {})
                if st.button("Cancel / Emergency Stop", key="abort-" + experiment["id"]):
                    call(f"/api/chaos/experiments/{experiment['id']}/abort", {})
                st.json(experiment["execution"], expanded=False)
    elif page == "Self-Healing":
        st.subheader("Incidents and recovery leases")
        st.json(call("/api/healing/incidents") or [])
        st.subheader("Allowed playbooks")
        st.json(call("/api/healing/actions") or [])
        st.subheader("Observed recovery verification")
        st.json(call("/api/healing/history") or [])
    elif page == "Agent Collaboration":
        st.markdown("**Analysis Agent → Chaos Agent → User approval → Deterministic executor → Observation → Self-Healing Agent → Verification → Analysis feedback**")
        st.json(status["timeline"])
        st.json(call("/api/llm-usage") or {})
    else:
        st.subheader("Experiment history")
        experiments = call("/api/chaos/experiments") or []
        states = st.multiselect("Filter experiment states", sorted({e["state"] for e in experiments}))
        visible = [e for e in experiments if not states or e["state"] in states]
        st.dataframe([{"experiment": e["id"], "state": e["state"], "fault": e["proposal"]["fault_type"], "targets": ", ".join(e["proposal"]["targets"]), "duration_seconds": e["proposal"]["duration_seconds"]} for e in visible], width="stretch")
        for experiment in visible:
            with st.expander(experiment["id"]):
                st.json(experiment)
        st.subheader("Final reports")
        reports = call("/api/chaos/reports") or []
        st.json(reports)
        st.download_button("Download recorded reports", json.dumps(reports, indent=2), file_name="pfia-experiment-reports.json", mime="application/json")
