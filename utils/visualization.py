"""
Reusable visualization components for displaying comparison results.

This module provides functions for displaying comparison data in various formats:
metrics, charts, tables, and status indicators.
"""

from typing import Dict, List, Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def display_status_indicator(status: str) -> str:
    """
    Get status indicator emoji and color.

    Args:
        status: Status string ('match', 'differ', 'error', 'skipped')

    Returns:
        Emoji string
    """
    status_map = {
        'match': '✅',
        'differ': '⚠️',
        'error': '❌',
        'skipped': '⏭️'
    }
    return status_map.get(status, '❓')


def display_bucket_comparison(comparison: Dict[str, Any]):
    """
    Display bucket-level comparison results.

    Args:
        comparison: Bucket comparison dictionary
    """
    st.markdown(f"**Status:** {display_status_indicator(comparison['status'])} {comparison['status'].upper()}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Common Buckets", len(comparison['common']))
        if comparison['common']:
            with st.expander("View common buckets"):
                for bucket in comparison['common']:
                    st.text(f"✅ {bucket}")

    with col2:
        st.metric("Production Only", len(comparison['production_only']))
        if comparison['production_only']:
            with st.expander("View production-only buckets"):
                for bucket in comparison['production_only']:
                    st.text(f"🔵 {bucket}")

    with col3:
        st.metric("Test Only", len(comparison['test_only']))
        if comparison['test_only']:
            with st.expander("View test-only buckets"):
                for bucket in comparison['test_only']:
                    st.text(f"🟢 {bucket}")


def display_table_comparison(comparison: Dict[str, Any]):
    """
    Display table-level comparison results.

    Args:
        comparison: Table comparison dictionary (per bucket)
    """
    for bucket, tables in comparison.items():
        with st.expander(f"📂 {bucket} - {display_status_indicator(tables['status'])} {tables['status'].upper()}"):
            if not tables['common'] and not tables['production_only'] and not tables['test_only']:
                st.info("No tables in this bucket")
                continue

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Common Tables**")
                if tables['common']:
                    for table in tables['common']:
                        st.text(f"✅ {table}")
                else:
                    st.text("None")

            with col2:
                st.markdown("**Production Only**")
                if tables['production_only']:
                    for table in tables['production_only']:
                        st.text(f"🔵 {table}")
                else:
                    st.text("None")

            with col3:
                st.markdown("**Test Only**")
                if tables['test_only']:
                    for table in tables['test_only']:
                        st.text(f"🟢 {table}")
                else:
                    st.text("None")


def display_metadata_differences(comparison: Dict[str, Any]):
    """
    Display metadata comparison differences.

    Args:
        comparison: Metadata comparison dictionary (per table)
    """
    # Filter tables with differences
    differing_tables = {
        table_id: meta
        for table_id, meta in comparison.items()
        if meta.get('status') == 'differ'
    }

    if not differing_tables:
        st.success("✅ All table metadata matches perfectly!")
        return

    st.warning(f"⚠️ {len(differing_tables)} table(s) have metadata differences")

    for table_id, meta in differing_tables.items():
        with st.expander(f"📊 {table_id}"):
            # Primary Keys
            if not meta['primary_keys']['match']:
                st.markdown("**Primary Keys Differ:**")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("*Production:*")
                    st.code(', '.join(meta['primary_keys']['production']) or 'None')
                with col2:
                    st.markdown("*Test:*")
                    st.code(', '.join(meta['primary_keys']['test']) or 'None')

            # Columns
            if not meta['columns']['match']:
                st.markdown("**Column Differences:**")
                col1, col2 = st.columns(2)
                with col1:
                    if meta['columns']['production_only']:
                        st.markdown("*Production Only:*")
                        for col in meta['columns']['production_only']:
                            st.text(f"🔵 {col}")
                with col2:
                    if meta['columns']['test_only']:
                        st.markdown("*Test Only:*")
                        for col in meta['columns']['test_only']:
                            st.text(f"🟢 {col}")

            # Data Types
            if not meta['data_types']['match']:
                st.markdown("**Data Type Differences:**")
                type_df = pd.DataFrame([
                    {'Column': col, 'Production Type': prod_type, 'Test Type': test_type}
                    for col, (prod_type, test_type) in meta['data_types']['differences'].items()
                ])
                st.dataframe(type_df, use_container_width=True)

            # Row Count
            if not meta['row_count']['match']:
                st.markdown("**Row Count Difference:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Production", meta['row_count']['production'])
                with col2:
                    st.metric("Test", meta['row_count']['test'])
                with col3:
                    diff = meta['row_count']['test'] - meta['row_count']['production']
                    st.metric("Difference", diff, delta=diff)


def display_row_differences(differences: Dict[str, Any]):
    """
    Display row-level differences for a single table.

    Args:
        differences: Row differences dictionary for one table
    """
    if differences.get('status') == 'skipped':
        st.info(f"ℹ️ Row comparison skipped: {differences.get('reason')}")
        return

    if differences.get('status') == 'error':
        st.error(f"❌ Error comparing rows: {differences.get('error')}")
        return

    if differences.get('status') == 'match':
        st.success("✅ All rows match perfectly!")
        return

    # Display summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Rows Compared", differences['total_rows_compared'])
    with col2:
        st.metric("Identical Rows", differences['identical_rows'])
    with col3:
        st.metric("Differing Rows", differences['differing_rows'])

    st.markdown("---")

    # Column differences chart
    if differences['column_differences']:
        st.markdown("### Differences by Column")

        df = pd.DataFrame([
            {'Column': col, 'Differing Rows': count}
            for col, count in differences['column_differences'].items()
        ]).sort_values('Differing Rows', ascending=False)

        fig = px.bar(
            df,
            x='Column',
            y='Differing Rows',
            title='Number of Differing Rows per Column',
            color='Differing Rows',
            color_continuous_scale='Reds'
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # Sample differences table
    if differences['sample_differences']:
        st.markdown("### Sample Differences")
        st.caption(f"Showing first {len(differences['sample_differences'])} differences")

        # Convert to DataFrame for display
        sample_df = pd.DataFrame(differences['sample_differences'])

        # Format primary key as string
        if 'primary_key' in sample_df.columns:
            sample_df['primary_key'] = sample_df['primary_key'].apply(
                lambda pk: ', '.join([f"{k}={v}" for k, v in pk.items()])
            )

        st.dataframe(sample_df, use_container_width=True)

        # Export option
        csv = sample_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Differences as CSV",
            data=csv,
            file_name="row_differences.csv",
            mime="text/csv"
        )
    else:
        st.info("No sample differences available")


def display_summary_metrics(summary: Dict[str, Any]):
    """
    Display summary metrics in a grid layout.

    Args:
        summary: Summary dictionary
    """
    # Additional metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        if summary['tables_with_metadata_differences'] > 0:
            st.metric(
                "Tables with Metadata Differences",
                summary['tables_with_metadata_differences'],
                delta=None
            )

    with col2:
        if summary['tables_with_row_differences'] > 0:
            st.metric(
                "Tables with Row Differences",
                summary['tables_with_row_differences'],
                delta=None
            )

    with col3:
        match_rate = (summary['matching_tables'] / summary['total_tables'] * 100) if summary['total_tables'] > 0 else 0
        st.metric(
            "Table Match Rate",
            f"{match_rate:.1f}%"
        )


def display_comparison_progress(production_status: str, test_status: str):
    """
    Display job comparison progress with visual indicators.

    Args:
        production_status: Production job status
        test_status: Test job status
    """
    status_icons = {
        'waiting': '⏳',
        'processing': '⚙️',
        'success': '✅',
        'error': '❌',
        'cancelled': '🚫',
        'terminated': '🛑'
    }

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### Production Run")
        st.markdown(f"{status_icons.get(production_status, '❓')} **{production_status.upper()}**")

    with col2:
        st.markdown(f"### Test Run")
        st.markdown(f"{status_icons.get(test_status, '❓')} **{test_status.upper()}**")
