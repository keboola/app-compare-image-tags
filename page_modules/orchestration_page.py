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
    if not st.session_state.get('config_id') or not st.session_state.get('user_token'):
        st.warning("⚠️ Please complete the Input phase first")
        return

    client = KeboolaAPIClient(token_override=st.session_state.get('user_token'))

    # Phase 1: Setup (create branches and update configs)
    if not (st.session_state.get('production_config_updated') and st.session_state.get('test_config_updated')):
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

    # Step 1: Development Branches (one for each config to avoid data collision)
    with st.expander("Step 1: Development Branches", expanded=not (st.session_state.get('production_branch_id') and st.session_state.get('test_branch_id'))):
        if st.session_state.get('production_branch_id') and st.session_state.get('test_branch_id'):
            st.success(f"✅ Production branch ready (ID: {st.session_state['production_branch_id']})")
            st.success(f"✅ Test branch ready (ID: {st.session_state['test_branch_id']})")
        else:
            st.info("Creating two development branches to isolate outputs")

            st.warning("""
            **Note:** Branch creation requires admin token permissions.
            If you don't have admin access, provide a token with branch creation permissions below.
            """)

            # Optional admin token input
            admin_token = st.text_input(
                "Admin Token (optional)",
                type="password",
                help="Provide a token with branch creation permissions if your current user doesn't have admin access",
                key="admin_token_input"
            )

            if st.button("Create Development Branches", type="primary"):
                with st.spinner("Setting up development branches..."):
                    try:
                        # Use admin token if provided, otherwise use default client
                        branch_client = client
                        if admin_token:
                            from utils.keboola_client import KeboolaAPIClient
                            branch_client = KeboolaAPIClient(token_override=admin_token)
                            st.info("Using provided admin token for branch operations")

                        # First check if we can list branches
                        st.info("Checking branch access...")
                        existing_branches = branch_client.list_branches()
                        st.success(f"✅ Branch feature accessible (found {len(existing_branches)} existing branches)")

                        # Create production branch
                        st.info("Creating production branch...")
                        prod_branch = branch_client.get_or_create_branch(f"{st.session_state['branch_name']}-production")
                        prod_branch_id = prod_branch.get('id') or prod_branch.get('branchId')
                        st.success(f"✅ Production branch created (ID: {prod_branch_id})")

                        # Create test branch
                        st.info("Creating test branch...")
                        test_branch = branch_client.get_or_create_branch(f"{st.session_state['branch_name']}-test")
                        test_branch_id = test_branch.get('id') or test_branch.get('branchId')
                        st.success(f"✅ Test branch created (ID: {test_branch_id})")

                        # Wait for branches to be ready (especially with many configurations)
                        st.info("⏳ Waiting for branches to be ready (this may take several minutes with 1000+ configurations)...")

                        import datetime
                        start_time = datetime.datetime.now()

                        with st.spinner("Polling branch status..."):
                            elapsed_display = st.empty()
                            progress_bar = st.progress(0)

                            max_wait = 600  # 10 minutes
                            poll_interval = 10  # Check every 10 seconds
                            attempts = 0
                            max_attempts = max_wait // poll_interval

                            both_ready = False
                            while attempts < max_attempts:
                                elapsed = (datetime.datetime.now() - start_time).total_seconds()
                                elapsed_display.caption(f"⏱️ Elapsed time: {int(elapsed // 60)}m {int(elapsed % 60)}s")

                                # Check if both branches are ready
                                try:
                                    prod_ready = branch_client.get_branch(prod_branch_id) is not None
                                    test_ready = branch_client.get_branch(test_branch_id) is not None

                                    if prod_ready and test_ready:
                                        both_ready = True
                                        break
                                except:
                                    pass

                                time.sleep(poll_interval)
                                attempts += 1
                                progress_bar.progress(min(attempts / max_attempts, 0.99))

                            if both_ready:
                                st.success(f"✅ Both branches are ready! (took {int(elapsed // 60)}m {int(elapsed % 60)}s)")
                            else:
                                st.warning("⚠️ Branches taking longer than expected, but continuing...")

                        # Store branch IDs
                        st.session_state.production_branch_id = prod_branch_id
                        st.session_state.test_branch_id = test_branch_id

                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to create branches: {str(e)}")
                        st.exception(e)

    # Step 2: Production Configuration (with production tag)
    if st.session_state.get('production_branch_id') and st.session_state.get('test_branch_id'):
        with st.expander("Step 2: Update Production Branch Config", expanded=not st.session_state.get('production_config_updated')):
            st.info(f"""
            **Note:** When branches are created, they automatically copy all configurations from production.
            We'll update the existing configuration in the production branch to use tag: **{st.session_state['production_image_tag']}**
            """)

            if st.session_state.get('production_config_updated'):
                st.success(f"✅ Production config updated in branch (Config ID: {st.session_state['config_id']})")
            elif st.button("Update Production Branch Config", type="primary", key="update_prod_config"):
                with st.spinner("Updating production configuration in branch..."):
                    try:
                        # Debug info
                        st.info(f"Updating config ID: {st.session_state['config_id']}")
                        st.info(f"In branch ID: {st.session_state['production_branch_id']}")
                        st.info(f"Component: {st.session_state['component_id']}")
                        st.info(f"Setting tag to: {st.session_state['production_image_tag']}")

                        # Update the existing config (auto-copied from main) in the branch
                        prod_config = client.update_configuration_tag(
                            component_id=st.session_state['component_id'],
                            config_id=st.session_state['config_id'],
                            config_data=st.session_state['original_config']['configuration'],
                            new_tag=st.session_state['production_image_tag'],
                            branch_id=st.session_state['production_branch_id']
                        )

                        # Verify the update by reading back from the branch
                        st.info("Verifying update in production branch...")
                        verified_config = client.get_configuration_in_branch(
                            component_id=st.session_state['component_id'],
                            config_id=st.session_state['config_id'],
                            branch_id=st.session_state['production_branch_id']
                        )

                        verified_tag = verified_config.get('configuration', {}).get('runtime', {}).get('image_tag', 'NOT SET')

                        if verified_tag == st.session_state['production_image_tag']:
                            st.success(f"✅ Production config updated in branch - Verified tag: {verified_tag}")
                            st.session_state.production_config_updated = True
                        else:
                            st.error(f"❌ Verification failed! Expected tag: {st.session_state['production_image_tag']}, Got: {verified_tag}")

                        # Debug: Show full config response
                        with st.expander("Debug: Production Config Details", expanded=True):
                            st.write("**API Headers Used:**")
                            st.json({
                                "X-KBC-BranchId": str(st.session_state['production_branch_id']),
                                "URL": f"/v2/storage/components/{st.session_state['component_id']}/configs/{st.session_state['config_id']}"
                            })
                            st.write("**Update Response:**")
                            st.json(prod_config)
                            st.write("**Verified Config from Branch:**")
                            st.json(verified_config)
                            if 'configuration' in verified_config:
                                st.write("**Runtime Settings (Verified):**")
                                st.json(verified_config['configuration'].get('runtime', {}))

                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to update production configuration: {str(e)}")
                        st.exception(e)

    # Step 3: Test Configuration (with test tag)
    if st.session_state.get('production_config_updated'):
        with st.expander("Step 3: Update Test Branch Config", expanded=not st.session_state.get('test_config_updated')):
            st.info(f"""
            **Note:** The configuration was auto-copied to the test branch as well.
            We'll update it to use tag: **{st.session_state['test_image_tag']}**
            """)

            if st.session_state.get('test_config_updated'):
                st.success(f"✅ Test config updated in branch (Config ID: {st.session_state['config_id']})")
            elif st.button("Update Test Branch Config", type="primary", key="update_test_config"):
                with st.spinner("Updating test configuration in branch..."):
                    try:
                        # Debug info
                        st.info(f"Updating config ID: {st.session_state['config_id']}")
                        st.info(f"In branch ID: {st.session_state['test_branch_id']}")
                        st.info(f"Setting tag to: {st.session_state['test_image_tag']}")

                        # Update the existing config (auto-copied from main) in the branch
                        test_config = client.update_configuration_tag(
                            component_id=st.session_state['component_id'],
                            config_id=st.session_state['config_id'],
                            config_data=st.session_state['original_config']['configuration'],
                            new_tag=st.session_state['test_image_tag'],
                            branch_id=st.session_state['test_branch_id']
                        )

                        # Verify the update by reading back from the branch
                        st.info("Verifying update in test branch...")
                        verified_config = client.get_configuration_in_branch(
                            component_id=st.session_state['component_id'],
                            config_id=st.session_state['config_id'],
                            branch_id=st.session_state['test_branch_id']
                        )

                        verified_tag = verified_config.get('configuration', {}).get('runtime', {}).get('image_tag', 'NOT SET')

                        if verified_tag == st.session_state['test_image_tag']:
                            st.success(f"✅ Test config updated in branch - Verified tag: {verified_tag}")
                            st.session_state.test_config_updated = True
                        else:
                            st.error(f"❌ Verification failed! Expected tag: {st.session_state['test_image_tag']}, Got: {verified_tag}")

                        # Debug: Show full config response
                        with st.expander("Debug: Test Config Details", expanded=True):
                            st.write("**API Headers Used:**")
                            st.json({
                                "X-KBC-BranchId": str(st.session_state['test_branch_id']),
                                "URL": f"/v2/storage/components/{st.session_state['component_id']}/configs/{st.session_state['config_id']}"
                            })
                            st.write("**Update Response:**")
                            st.json(test_config)
                            st.write("**Verified Config from Branch:**")
                            st.json(verified_config)
                            if 'configuration' in verified_config:
                                st.write("**Runtime Settings (Verified):**")
                                st.json(verified_config['configuration'].get('runtime', {}))

                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to update test configuration: {str(e)}")
                        st.exception(e)


def execution_phase(client: KeboolaAPIClient):
    """
    Execution phase: Trigger parallel jobs.

    Args:
        client: Keboola API client
    """
    st.subheader("🚀 Triggering Jobs")

    st.markdown("""
    Ready to run the same configuration in parallel with different tags:
    - **Production** (tag: {prod_tag}): Config {config_id} in branch {prod_branch}
    - **Test** (tag: {test_tag}): Config {config_id} in branch {test_branch}
    """.format(
        prod_tag=st.session_state['production_image_tag'],
        test_tag=st.session_state['test_image_tag'],
        config_id=st.session_state['config_id'],
        prod_branch=f"{st.session_state['branch_name']}-production",
        test_branch=f"{st.session_state['branch_name']}-test"
    ))

    st.markdown("---")

    if st.button("Start Comparison Runs", type="primary", use_container_width=True):
        with st.spinner("Triggering jobs..."):
            try:
                # Show debug info
                with st.expander("Debug Info", expanded=False):
                    st.write("Component ID:", st.session_state['component_id'])
                    st.write("Config ID:", st.session_state['config_id'])
                    st.write("Production Branch ID:", st.session_state['production_branch_id'])
                    st.write("Test Branch ID:", st.session_state['test_branch_id'])

                # Trigger production run (production branch with production tag)
                st.info("Triggering production job...")
                prod_job = client.run_component(
                    st.session_state['component_id'],
                    st.session_state['config_id'],
                    branch_id=st.session_state['production_branch_id']
                )
                st.session_state.production_job_id = prod_job['id']
                st.session_state.production_job_status = 'waiting'

                # Trigger test run (test branch with test tag)
                st.info("Triggering test job...")
                test_job = client.run_component(
                    st.session_state['component_id'],
                    st.session_state['config_id'],
                    branch_id=st.session_state['test_branch_id']
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
    if prod_status in ['created', 'waiting', 'processing'] or test_status in ['created', 'waiting', 'processing']:
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
            'created': '🆕',
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
        if status in ['created', 'waiting', 'processing']:
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
    # Clear Streamlit cache to ensure fresh data
    st.cache_data.clear()

    with st.spinner("Comparing outputs... This may take a few moments"):
        try:
            engine = ComparisonEngine(client)

            # Compare outputs from two separate branches
            results = engine.compare_outputs(
                production_branch=st.session_state['production_branch_id'],
                test_branch_id=st.session_state['test_branch_id']
            )

            st.session_state.comparison_results = results

            st.info("👉 Navigate to **📊 Results** in the sidebar to view comparison")

            time.sleep(2)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Comparison failed: {str(e)}")
            st.exception(e)
