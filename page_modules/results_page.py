"""
Results Page - Multi-tab display of comparison results.

This page displays comparison results in three tabs:
1. Summary - Executive overview with key metrics and findings
2. Structure & Metadata - Bucket, table, and metadata comparison
3. Row Differences - Detailed row-level differences with export
"""

import streamlit as st

from utils.visualization import (
    display_bucket_comparison,
    display_log_comparison,
    display_metadata_differences,
    display_row_differences,
    display_summary_metrics,
    display_table_comparison,
)


def create_results_page():
    """Create and display the results page."""
    st.title("📊 Comparison Results")

    show_advanced = st.session_state.get("show_advanced", False)

    results = st.session_state.get("comparison_results")

    if not results:
        st.warning("⚠️ No comparison results available. Please complete the execution phase.")
        return

    # Add rerun comparison button at the top
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Rerun Comparison", width="stretch"):
            # Clear current results and trigger rerun
            st.session_state.comparison_results = None
            st.session_state.comparison_triggered = False

            # For config mode, also clear job IDs to retrigger jobs
            if st.session_state.get("comparison_mode") == "config":
                st.session_state.pop("production_job_id", None)
                st.session_state.pop("test_job_id", None)
                st.session_state.pop("production_job_status", None)
                st.session_state.pop("test_job_status", None)
                st.session_state.pop("jobs_completion_logged", None)
                # Clear comparison logs
                st.session_state.pop("comparison_logs", None)
                st.session_state.pop("job_execution_logs", None)
                st.session_state.pop("job_monitoring_logs", None)

            st.rerun()

    # Display comparison execution log if available
    if show_advanced and st.session_state.get("comparison_logs"):
        with st.expander("📋 Comparison Execution Log", expanded=False):
            logs = st.session_state.get("comparison_logs", [])
            for log in logs:
                timestamp = log["timestamp"]
                message = log["message"]
                level = log["level"]

                if level == "success":
                    st.success(f"[{timestamp}] {message}")
                elif level == "warning":
                    st.warning(f"[{timestamp}] {message}")
                elif level == "error":
                    st.error(f"[{timestamp}] {message}")
                else:
                    st.info(f"[{timestamp}] {message}")

    # Debug: Show raw results structure
    if show_advanced:
        with st.expander("🔧 Debug: Raw Comparison Results", expanded=False):
            st.json(results)

    # Display comparison details based on mode
    comparison_mode = st.session_state.get("comparison_mode")

    with st.expander("ℹ️ Comparison Details", expanded=False):
        if comparison_mode == "config":
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Production Configuration:**")
                st.text(f"Config ID: {st.session_state.get('config_id')}")
                st.text(f"Image Tag: {st.session_state.get('production_image_tag')}")
                st.text(f"Branch: {st.session_state.get('branch_name')}-production")
            with col2:
                st.markdown("**Test Configuration:**")
                st.text(f"Config ID: {st.session_state.get('config_id')}")
                st.text(f"Image Tag: {st.session_state.get('test_image_tag')}")
                st.text(f"Branch: {st.session_state.get('branch_name')}-test")

        elif comparison_mode == "tables":
            st.markdown("**Comparison Mode:** Table Comparison")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Production Branch:**")
                st.text(f"Name: {st.session_state.get('production_branch_name')}")
                st.text(f"ID: {st.session_state.get('production_branch_id')}")
            with col2:
                st.markdown("**Test Branch:**")
                st.text(f"Name: {st.session_state.get('test_branch_name')}")
                st.text(f"ID: {st.session_state.get('test_branch_id')}")

            st.markdown(f"**Tables Compared:** {len(st.session_state.get('table_ids_to_compare', []))}")
            with st.expander("View table list"):
                for table_id in st.session_state.get("table_ids_to_compare", []):
                    st.text(f"  • {table_id}")

        elif comparison_mode == "buckets":
            st.markdown("**Comparison Mode:** Bucket Comparison")
            bucket_pairs = st.session_state.get("bucket_pairs", [])
            if bucket_pairs:
                # New URL-based format
                st.markdown(f"**Bucket Pairs Compared:** {len(bucket_pairs)}")
                with st.expander("View bucket pairs"):
                    for idx, pair in enumerate(bucket_pairs):
                        bucket_a = pair["bucket_a"]
                        bucket_b = pair["bucket_b"]
                        branch_a = f"Branch {bucket_a['branch_id']}" if bucket_a["branch_id"] else "Production"
                        branch_b = f"Branch {bucket_b['branch_id']}" if bucket_b["branch_id"] else "Production"
                        st.markdown(f"**Pair {idx + 1}:**")
                        st.text(f"  🔵 {branch_a}: {bucket_a['canonical_bucket_id']}")
                        st.text(f"  🟢 {branch_b}: {bucket_b['canonical_bucket_id']}")
            else:
                # Legacy format fallback
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Production Branch:**")
                    st.text(f"Name: {st.session_state.get('production_branch_name')}")
                    st.text(f"ID: {st.session_state.get('production_branch_id')}")
                with col2:
                    st.markdown("**Test Branch:**")
                    st.text(f"Name: {st.session_state.get('test_branch_name')}")
                    st.text(f"ID: {st.session_state.get('test_branch_id')}")

                bucket_ids = st.session_state.get("bucket_ids_to_compare") or []
                st.markdown(f"**Buckets Compared:** {len(bucket_ids)}")
                with st.expander("View bucket list"):
                    for bucket_id in bucket_ids:
                        st.text(f"  • {bucket_id}")

    st.markdown("---")

    # Tab navigation - conditionally add Log Comparison tab for config mode
    log_comparison_available = results.get("log_comparison") is not None

    if log_comparison_available:
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📋 Summary", "🗂️ Structure & Metadata", "🔍 Row Differences", "📝 Log Comparison"]
        )
    else:
        tab1, tab2, tab3 = st.tabs(["📋 Summary", "🗂️ Structure & Metadata", "🔍 Row Differences"])

    with tab1:
        display_summary_tab(results)

    with tab2:
        display_structure_tab(results)

    with tab3:
        display_differences_tab(results)

    if log_comparison_available:
        with tab4:
            display_log_comparison_tab(results)


def display_summary_tab(results: dict):
    """
    Display executive summary of comparison.

    Args:
        results: Full comparison results dictionary
    """
    # Safety check for summary
    if "summary" not in results:
        st.error("❌ Summary data missing from comparison results")
        return

    summary = results["summary"]

    # Debug: Show summary structure
    if st.session_state.get("show_advanced", False):
        with st.expander("🔧 Debug: Summary Data", expanded=False):
            st.json(summary)

    # Overall status banner
    if summary.get("overall_status") == "match":
        st.success("✅ Outputs match perfectly!")
        st.balloons()
    else:
        st.warning("⚠️ Differences detected between production and test outputs")

    st.markdown("---")

    # Key metrics
    st.subheader("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Buckets", summary.get("total_buckets", 0))
    with col2:
        st.metric("Matching Buckets", summary.get("matching_buckets", 0))
    with col3:
        st.metric("Total Tables", summary.get("total_tables", 0))
    with col4:
        st.metric("Matching Tables", summary.get("matching_tables", 0))

    # Difference breakdown
    if summary["overall_status"] != "match":
        st.markdown("---")
        st.subheader("Difference Breakdown")
        display_summary_metrics(summary)

    # Key findings
    st.markdown("---")
    st.subheader("Key Findings")

    for i, finding in enumerate(summary["key_findings"], 1):
        st.markdown(f"{i}. {finding}")


def display_structure_tab(results: dict):
    """
    Display bucket, table, and metadata comparison.

    Args:
        results: Full comparison results dictionary
    """
    st.subheader("🪣 Bucket Comparison")
    display_bucket_comparison(results["bucket_comparison"])

    st.markdown("---")

    st.subheader("📊 Table Comparison")
    if results["table_comparison"]:
        display_table_comparison(results["table_comparison"])
    else:
        st.info("No common buckets to compare tables")

    st.markdown("---")

    st.subheader("📋 Metadata Comparison")
    if results["metadata_comparison"]:
        display_metadata_differences(results["metadata_comparison"])
    else:
        st.info("No common tables to compare metadata")


def display_differences_tab(results: dict):
    """
    Display row-level differences viewer.

    Args:
        results: Full comparison results dictionary
    """
    row_diffs = results["row_differences"]

    if not row_diffs:
        st.info("No row-level comparison data available")
        return

    # DEBUG: Show all table statuses
    with st.expander("🔧 DEBUG: Row Comparison Status for All Tables", expanded=False):
        st.write("**All row comparison results:**")
        for table_id, diff_data in row_diffs.items():
            status = diff_data.get("status", "UNKNOWN")
            prod_count = diff_data.get("production_row_count", "N/A")
            test_count = diff_data.get("test_row_count", "N/A")
            diff_count = diff_data.get("differing_rows", "N/A")

            st.markdown(f"**{table_id}**")
            st.write(f"  - Status: `{status}`")
            st.write(f"  - Production rows: {prod_count}")
            st.write(f"  - Test rows: {test_count}")
            st.write(f"  - Differing rows: {diff_count}")

            if status in ["error", "skipped"]:
                st.write(f"  - Reason/Error: {diff_data.get('reason', diff_data.get('error', 'N/A'))}")

            st.write(f"  - Full data: {diff_data}")
            st.markdown("---")

    # Filter tables with differences
    tables_with_diffs = [table for table, diff in row_diffs.items() if diff.get("status") == "differ"]

    if not tables_with_diffs:
        st.success("✅ No row-level differences found!")
        st.info("All rows in compared tables match perfectly.")
        return

    st.subheader(f"🔍 Row-Level Differences ({len(tables_with_diffs)} tables)")

    # Table selector
    selected_table = st.selectbox("Select table to view differences:", options=tables_with_diffs, index=0)

    if selected_table:
        st.markdown(f"### {selected_table}")
        st.markdown("---")
        display_row_differences(row_diffs[selected_table])

    # Show summary of all tables with differences
    st.markdown("---")
    st.subheader("Summary of All Tables with Differences")

    summary_data = []
    for table in tables_with_diffs:
        diff = row_diffs[table]
        summary_data.append(
            {
                "Table": table,
                "Total Rows": diff.get("total_rows_compared", 0),
                "Differing Rows": diff.get("differing_rows", 0),
                "Differing Columns": len(diff.get("column_differences", {})),
            }
        )

    if summary_data:
        import pandas as pd

        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, width="stretch")


def display_log_comparison_tab(results: dict):
    """
    Display job log comparison tab.

    Args:
        results: Full comparison results dictionary
    """
    log_comparison = results.get("log_comparison")

    if not log_comparison:
        st.info("ℹ️ Log comparison not available for this comparison mode")
        return

    # Show job IDs
    st.markdown("### Job Information")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Production Job**")
        st.code(log_comparison.get("production_job_id", "N/A"))

    with col2:
        st.markdown("**Test Job**")
        st.code(log_comparison.get("test_job_id", "N/A"))

    st.markdown("---")

    # Display log comparison
    display_log_comparison(log_comparison)
