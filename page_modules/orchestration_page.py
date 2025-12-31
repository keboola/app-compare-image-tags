"""
Orchestration Page - Configuration creation, job execution, and monitoring.

This page handles the orchestration of:
1. Development branch creation
2. Test configuration creation
3. Parallel job execution
4. Job monitoring with progress tracking
5. Triggering comparison once jobs complete
"""

import time
from datetime import datetime
import streamlit as st
from utils.keboola_client import KeboolaAPIClient
from utils.comparison_engine import ComparisonEngine


def create_orchestration_page():
    """Create and display the orchestration page."""
    st.title("⚙️ Execution & Monitoring")

    # Ensure we have required inputs
    if not st.session_state.get('config_id'):
        st.warning("⚠️ Please complete the Input phase first")
        return

    client = KeboolaAPIClient()

    # Phase 1: Setup (create test config, ensure branch exists)
    if not st.session_state.get('test_config_id'):
        setup_phase(client)

    # Phase 2: Execute jobs
    elif not st.session_state.get('production_job_id'):
        execution_phase(client)

    # Phase 3: Monitor progress
    else:
        monitoring_phase(client)


def setup_phase(client: KeboolaAPIClient):
    """
    Setup phase: Create branch and test configuration.

    Args:
        client: Keboola API client
    """
    st.subheader("📋 Setup Phase")

    st.markdown("""
    Before running the comparison, we need to:
    1. Create or select a development branch
    2. Create a test configuration with the new image tag
    """)

    st.markdown("---")

    # Step 1: Development Branch
    with st.expander("Step 1: Development Branch", expanded=not st.session_state.get('branch_id')):
        if st.session_state.get('branch_id'):
            st.success(f"✅ Branch ready: {st.session_state.get('branch_name')} (ID: {st.session_state['branch_id']})")
        else:
            st.info(f"Creating or selecting branch: **{st.session_state['branch_name']}**")

            if st.button("Create/Select Development Branch", type="primary"):
                with st.spinner("Setting up development branch..."):
                    try:
                        branch = client.get_or_create_branch(st.session_state['branch_name'])
                        st.session_state.branch_id = branch['id']
                        st.success(f"✅ Branch ready: {branch['name']} (ID: {branch['id']})")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to create/select branch: {str(e)}")
                        st.exception(e)

    # Step 2: Test Configuration
    if st.session_state.get('branch_id'):
        with st.expander("Step 2: Test Configuration", expanded=True):
            st.info(f"Creating test configuration with tag: **{st.session_state['test_image_tag']}**")

            if st.button("Create Test Configuration", type="primary"):
                with st.spinner("Creating test configuration..."):
                    try:
                        test_config = client.duplicate_configuration_with_tag(
                            st.session_state['original_config'],
                            st.session_state['test_image_tag']
                        )
                        st.session_state.test_config_id = test_config['id']
                        st.success(f"✅ Test config created: {test_config['name']}")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to create test configuration: {str(e)}")
                        st.exception(e)


def execution_phase(client: KeboolaAPIClient):
    """
    Execution phase: Trigger parallel jobs.

    Args:
        client: Keboola API client
    """
    st.subheader("🚀 Triggering Jobs")

    st.markdown("""
    Ready to run both configurations in parallel:
    - **Production**: Config {prod_id} in default branch
    - **Test**: Config {test_id} in branch {branch}
    """.format(
        prod_id=st.session_state['config_id'],
        test_id=st.session_state['test_config_id'],
        branch=st.session_state['branch_name']
    ))

    st.markdown("---")

    if st.button("Start Comparison Runs", type="primary", use_container_width=True):
        with st.spinner("Triggering jobs..."):
            try:
                # Trigger production run (default branch)
                prod_job = client.run_component(
                    st.session_state['component_id'],
                    st.session_state['config_id'],
                    branch_id=None  # Default branch
                )
                st.session_state.production_job_id = prod_job['id']
                st.session_state.production_job_status = 'waiting'

                # Trigger test run (dev branch)
                test_job = client.run_component(
                    st.session_state['component_id'],
                    st.session_state['test_config_id'],
                    branch_id=st.session_state['branch_id']
                )
                st.session_state.test_job_id = test_job['id']
                st.session_state.test_job_status = 'waiting'

                st.success("✅ Both jobs triggered successfully!")
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.error(f"❌ Failed to trigger jobs: {str(e)}")
                st.exception(e)


def monitoring_phase(client: KeboolaAPIClient):
    """
    Monitoring phase: Poll and display job status.

    Args:
        client: Keboola API client
    """
    st.subheader("📊 Job Monitoring")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Production Run")
        prod_status = display_job_status(
            client,
            st.session_state['production_job_id'],
            "production"
        )

    with col2:
        st.markdown("### Test Run")
        test_status = display_job_status(
            client,
            st.session_state['test_job_id'],
            "test"
        )

    # Store current statuses
    st.session_state.production_job_status = prod_status
    st.session_state.test_job_status = test_status

    # Auto-refresh every 5 seconds if jobs still running
    if prod_status in ['waiting', 'processing'] or test_status in ['waiting', 'processing']:
        st.info("⏳ Jobs are still running... Page will auto-refresh")
        time.sleep(5)
        st.rerun()

    # Both complete - proceed to comparison
    if prod_status == 'success' and test_status == 'success':
        st.markdown("---")
        st.success("✅ Both jobs completed successfully!")

        if st.button("Proceed to Comparison", type="primary", use_container_width=True):
            start_comparison(client)

    # Handle errors
    elif prod_status in ['error', 'cancelled', 'terminated'] or test_status in ['error', 'cancelled', 'terminated']:
        st.markdown("---")
        st.error("❌ One or more jobs failed or were terminated")

        if st.button("🔄 Retry Jobs"):
            # Clear job IDs to restart execution phase
            st.session_state.pop('production_job_id', None)
            st.session_state.pop('test_job_id', None)
            st.session_state.pop('production_job_status', None)
            st.session_state.pop('test_job_status', None)
            st.rerun()


def display_job_status(client: KeboolaAPIClient, job_id: str, label: str) -> str:
    """
    Display job status with progress indicator.

    Args:
        client: Keboola API client
        job_id: Job ID to monitor
        label: Label for display

    Returns:
        Current job status
    """
    try:
        status_data = client.get_job_status(job_id)

        status_icon = {
            'waiting': '⏳',
            'processing': '⚙️',
            'success': '✅',
            'error': '❌',
            'cancelled': '🚫',
            'terminated': '🛑'
        }

        status = status_data['status']
        st.markdown(f"{status_icon.get(status, '❓')} **Status:** {status.upper()}")

        # Show progress bar for running jobs
        if status in ['waiting', 'processing']:
            progress = status_data.get('progress', {})
            if isinstance(progress, dict):
                progress_pct = progress.get('percentage', 0)
            else:
                progress_pct = 0

            st.progress(progress_pct / 100 if progress_pct > 0 else 0.1)

            # Show elapsed time
            if 'createdTime' in status_data:
                created = datetime.fromisoformat(status_data['createdTime'].replace('Z', '+00:00'))
                elapsed = datetime.now(created.tzinfo) - created
                st.caption(f"Elapsed: {elapsed.seconds // 60}m {elapsed.seconds % 60}s")

        # Show error details
        if status == 'error':
            result = status_data.get('result', {})
            error_msg = result.get('message', 'Unknown error')
            st.error(f"Error: {error_msg}")

        # Show job details in expander
        with st.expander("Job Details"):
            st.json(status_data)

        return status

    except Exception as e:
        st.error(f"❌ Failed to get job status: {str(e)}")
        return 'error'


def start_comparison(client: KeboolaAPIClient):
    """
    Trigger comparison engine and transition to results.

    Args:
        client: Keboola API client
    """
    with st.spinner("Comparing outputs... This may take a few moments"):
        try:
            engine = ComparisonEngine(client)
            results = engine.compare_outputs(
                production_branch=None,  # Default branch
                test_branch_id=st.session_state['branch_id']
            )

            st.session_state.comparison_results = results
            st.success("✅ Comparison complete!")

            st.info("👉 Navigate to **📊 Results** in the sidebar to view comparison")

            time.sleep(2)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Comparison failed: {str(e)}")
            st.exception(e)
