"""
Keboola Component Output Comparison Tool - Main Application

This is the main entry point for the Streamlit data app that compares
component outputs between two different image tags to validate upgrades.
"""

import streamlit as st
from page_modules import input_page, orchestration_page, results_page


def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="Component Output Comparison", page_icon="🔍", layout="wide", initial_sidebar_state="expanded"
    )

    # Initialize session state
    initialize_session_state()

    # Sidebar navigation
    st.sidebar.title("🔍 Output Comparison")
    st.sidebar.markdown("---")

    # Determine current phase based on session state (for suggested navigation)
    current_phase = determine_current_phase()

    # Page selection - preserve user's choice, only auto-navigate on phase transitions
    page_options = ["📝 Input", "⚙️ Execution", "📊 Results"]
    phase_to_index = {"input": 0, "execution": 1, "results": 2}

    # Initialize or update navigation state
    if "current_nav_page" not in st.session_state:
        st.session_state.current_nav_page = phase_to_index[current_phase]
    elif st.session_state.get("last_phase") != current_phase:
        # Only auto-navigate when phase actually changes (e.g., comparison completes)
        st.session_state.current_nav_page = phase_to_index[current_phase]
        # Also update the radio widget's stored value so Streamlit uses the new index
        st.session_state.nav_radio = page_options[phase_to_index[current_phase]]
    st.session_state.last_phase = current_phase

    page = st.sidebar.radio(
        "Navigation",
        page_options,
        index=st.session_state.current_nav_page,
        key="nav_radio",
        on_change=lambda: setattr(st.session_state, "current_nav_page", page_options.index(st.session_state.nav_radio)),
    )

    # Display current status in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Status")

    # Show comparison mode
    mode = st.session_state.get("comparison_mode")
    if mode == "config":
        st.sidebar.info("📋 Mode: Configuration")
    elif mode == "tables":
        st.sidebar.info("📊 Mode: Table Comparison")
    elif mode == "buckets":
        st.sidebar.info("🗂️ Mode: Bucket Comparison")

    # Show input validation status
    if st.session_state.get("input_validated"):
        st.sidebar.success("✅ Input validated")
    else:
        st.sidebar.info("⏳ Awaiting input")

    if st.session_state.get("production_job_id"):
        prod_status = st.session_state.get("production_job_status", "unknown")
        if prod_status == "success":
            st.sidebar.success("✅ Production run complete")
        elif prod_status in ["waiting", "processing"]:
            st.sidebar.info(f"⏳ Production run: {prod_status}")
        elif prod_status == "error":
            st.sidebar.error("❌ Production run failed")

    if st.session_state.get("test_job_id"):
        test_status = st.session_state.get("test_job_status", "unknown")
        if test_status == "success":
            st.sidebar.success("✅ Test run complete")
        elif test_status in ["waiting", "processing"]:
            st.sidebar.info(f"⏳ Test run: {test_status}")
        elif test_status == "error":
            st.sidebar.error("❌ Test run failed")

    if st.session_state.get("comparison_results"):
        st.sidebar.success("✅ Comparison complete")

    # View options
    st.sidebar.markdown("---")
    st.sidebar.markdown("### View")
    st.sidebar.checkbox(
        "Show advanced details",
        value=st.session_state.get("show_advanced", False),
        key="show_advanced",
        help="Show debug panels, raw data, and detailed logs.",
    )

    # Reset button
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Start New Comparison", width="stretch"):
        # Clear all session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    # Route to appropriate page
    if page == "📝 Input":
        input_page.create_input_page()
    elif page == "⚙️ Execution":
        orchestration_page.create_orchestration_page()
    elif page == "📊 Results":
        results_page.create_results_page()


def initialize_session_state():
    """Initialize all session state variables with defaults."""
    defaults = {
        # Comparison mode ('config', 'tables', 'buckets')
        "comparison_mode": None,
        "input_validated": False,
        # Common fields
        "user_token": None,
        "kbc_url": None,
        "auto_run": False,
        # Config mode fields
        "config_id": None,
        "config_input": None,
        "production_image_tag": "latest",
        "test_image_tag": None,
        "branch_name": "comparison-test",
        "job_mode": "run",
        "component_id": None,
        "original_config": None,
        # Tables/Buckets mode fields
        "production_branch_name": None,
        "test_branch_name": None,
        "table_ids_to_compare": None,
        "bucket_ids_to_compare": None,
        # Execution state
        "production_branch_id": None,
        "test_branch_id": None,
        "production_config_updated": False,
        "test_config_updated": False,
        "production_job_id": None,
        "test_job_id": None,
        "production_job_status": None,
        "test_job_status": None,
        # Results
        "comparison_results": None,
        # UI preferences
        "show_advanced": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def determine_current_phase() -> str:
    """
    Determine current workflow phase based on session state.

    Returns:
        Current phase: 'input', 'execution', or 'results'
    """
    if not st.session_state.get("input_validated"):
        return "input"
    elif not st.session_state.get("comparison_results"):
        return "execution"
    else:
        return "results"


if __name__ == "__main__":
    main()
