"""
Results Page - Multi-tab display of comparison results.

This page displays comparison results in three tabs:
1. Summary - Executive overview with key metrics and findings
2. Structure & Metadata - Bucket, table, and metadata comparison
3. Row Differences - Detailed row-level differences with export
"""

import streamlit as st
from utils.visualization import (
    display_summary_metrics,
    display_bucket_comparison,
    display_table_comparison,
    display_metadata_differences,
    display_row_differences
)


def create_results_page():
    """Create and display the results page."""
    st.title("📊 Comparison Results")

    results = st.session_state.get('comparison_results')

    if not results:
        st.warning("⚠️ No comparison results available. Please complete the execution phase.")
        return

    # Add rerun comparison button at the top
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Rerun Comparison", use_container_width=True):
            # Clear current results and trigger rerun
            st.session_state.comparison_results = None
            st.session_state.comparison_triggered = False
            st.rerun()

    # Display comparison execution log if available
    if st.session_state.get('comparison_logs'):
        with st.expander("📋 Comparison Execution Log", expanded=False):
            logs = st.session_state.get('comparison_logs', [])
            for log in logs:
                timestamp = log['timestamp']
                message = log['message']
                level = log['level']

                if level == 'success':
                    st.success(f"[{timestamp}] {message}")
                elif level == 'warning':
                    st.warning(f"[{timestamp}] {message}")
                elif level == 'error':
                    st.error(f"[{timestamp}] {message}")
                else:
                    st.info(f"[{timestamp}] {message}")

    # Debug: Show raw results structure
    with st.expander("🔧 Debug: Raw Comparison Results", expanded=False):
        st.json(results)

    # Display configuration info at the top
    with st.expander("ℹ️ Comparison Details", expanded=False):
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

    st.markdown("---")

    # Tab navigation
    tab1, tab2, tab3 = st.tabs([
        "📋 Summary",
        "🗂️ Structure & Metadata",
        "🔍 Row Differences"
    ])

    with tab1:
        display_summary_tab(results)

    with tab2:
        display_structure_tab(results)

    with tab3:
        display_differences_tab(results)


def display_summary_tab(results: dict):
    """
    Display executive summary of comparison.

    Args:
        results: Full comparison results dictionary
    """
    # Safety check for summary
    if 'summary' not in results:
        st.error("❌ Summary data missing from comparison results")
        return

    summary = results['summary']

    # Debug: Show summary structure
    with st.expander("🔧 Debug: Summary Data", expanded=False):
        st.json(summary)

    # Overall status banner
    if summary.get('overall_status') == 'match':
        st.success("✅ Outputs match perfectly!")
        st.balloons()
    else:
        st.warning("⚠️ Differences detected between production and test outputs")

    st.markdown("---")

    # Key metrics
    st.subheader("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Buckets", summary.get('total_buckets', 0))
    with col2:
        st.metric("Matching Buckets", summary.get('matching_buckets', 0))
    with col3:
        st.metric("Total Tables", summary.get('total_tables', 0))
    with col4:
        st.metric("Matching Tables", summary.get('matching_tables', 0))

    # Difference breakdown
    if summary['overall_status'] != 'match':
        st.markdown("---")
        st.subheader("Difference Breakdown")
        display_summary_metrics(summary)

    # Key findings
    st.markdown("---")
    st.subheader("Key Findings")

    for i, finding in enumerate(summary['key_findings'], 1):
        st.markdown(f"{i}. {finding}")


def display_structure_tab(results: dict):
    """
    Display bucket, table, and metadata comparison.

    Args:
        results: Full comparison results dictionary
    """
    st.subheader("🪣 Bucket Comparison")
    display_bucket_comparison(results['bucket_comparison'])

    st.markdown("---")

    st.subheader("📊 Table Comparison")
    if results['table_comparison']:
        display_table_comparison(results['table_comparison'])
    else:
        st.info("No common buckets to compare tables")

    st.markdown("---")

    st.subheader("📋 Metadata Comparison")
    if results['metadata_comparison']:
        display_metadata_differences(results['metadata_comparison'])
    else:
        st.info("No common tables to compare metadata")


def display_differences_tab(results: dict):
    """
    Display row-level differences viewer.

    Args:
        results: Full comparison results dictionary
    """
    row_diffs = results['row_differences']

    if not row_diffs:
        st.info("No row-level comparison data available")
        return

    # Filter tables with differences
    tables_with_diffs = [
        table for table, diff in row_diffs.items()
        if diff.get('status') == 'differ'
    ]

    if not tables_with_diffs:
        st.success("✅ No row-level differences found!")
        st.info("All rows in compared tables match perfectly.")
        return

    st.subheader(f"🔍 Row-Level Differences ({len(tables_with_diffs)} tables)")

    # Table selector
    selected_table = st.selectbox(
        "Select table to view differences:",
        options=tables_with_diffs,
        index=0
    )

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
        summary_data.append({
            'Table': table,
            'Total Rows': diff.get('total_rows_compared', 0),
            'Differing Rows': diff.get('differing_rows', 0),
            'Differing Columns': len(diff.get('column_differences', {}))
        })

    if summary_data:
        import pandas as pd
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True)
