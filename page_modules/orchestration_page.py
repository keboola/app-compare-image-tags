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
import requests
from utils.keboola_client import KeboolaAPIClient
from utils.comparison_engine import ComparisonEngine


def add_log(step_key: str, message: str, level: str = "info"):
    """
    Add a log message to session state for a specific step.

    Args:
        step_key: Key for the step (e.g., 'branch_creation')
        message: Message to log
        level: Message level ('info', 'success', 'warning', 'error')
    """
    if f'{step_key}_logs' not in st.session_state:
        st.session_state[f'{step_key}_logs'] = []

    st.session_state[f'{step_key}_logs'].append({
        'message': message,
        'level': level,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    })


def display_logs(step_key: str):
    """Display all logged messages for a step."""
    logs = st.session_state.get(f'{step_key}_logs', [])
    if logs:
        with st.expander(f"📋 Step Log ({len(logs)} messages)", expanded=False):
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


def create_orchestration_page():
    """Create and display the orchestration page."""
    st.title("⚙️ Execution & Monitoring")

    # Ensure we have required inputs
    if not st.session_state.get('config_id') or not st.session_state.get('user_token'):
        st.warning("⚠️ Please complete the Input phase first")
        return

    # Extract KBC URL from config input
    kbc_url = None
    config_input = st.session_state.get('config_input', '')
    if config_input and config_input.startswith('http'):
        parts = config_input.split('/')
        if len(parts) >= 3:
            kbc_url = f"{parts[0]}//{parts[2]}"

    client = KeboolaAPIClient(token_override=st.session_state.get('user_token'), kbc_url_override=kbc_url)

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
    auto_run_enabled = st.session_state.get('auto_run', False)

    with st.expander("Step 1: Development Branches", expanded=not (st.session_state.get('production_branch_id') and st.session_state.get('test_branch_id'))):
        if st.session_state.get('production_branch_id') and st.session_state.get('test_branch_id'):
            st.success(f"✅ Production branch ready (ID: {st.session_state['production_branch_id']})")
            st.success(f"✅ Test branch ready (ID: {st.session_state['test_branch_id']})")

            # Show preserved logs from branch creation
            display_logs('branch_creation')
        else:
            st.info("Creating two development branches to isolate outputs")

            if not auto_run_enabled:
                st.info("""
                **Note:** Using the admin token provided on the input page.
                If branch creation fails, ensure your token has the required permissions.
                """)

            # Auto-run or manual button trigger
            trigger_branch_creation = auto_run_enabled or st.button("Create or Reuse Development Branches", type="primary")

            if trigger_branch_creation:
                # Clear any stale branch IDs from previous runs
                st.session_state.pop('production_branch_id', None)
                st.session_state.pop('test_branch_id', None)
                st.session_state.pop('production_config_updated', None)
                st.session_state.pop('test_config_updated', None)
                st.session_state.pop('branch_creation_logs', None)
                with st.spinner("Setting up development branches..."):
                    try:
                        # Use the admin token from input page (already stored in client)
                        branch_client = client

                        # First check if we can list branches
                        add_log('branch_creation', "Checking branch access...")
                        existing_branches = branch_client.list_branches()
                        add_log('branch_creation', f"Branch feature accessible (found {len(existing_branches)} existing branches)", 'success')

                        # Create production branch
                        add_log('branch_creation', f"Getting or creating production branch: {st.session_state['branch_name']}-production")
                        prod_branch = branch_client.get_or_create_branch(f"{st.session_state['branch_name']}-production")

                        # Debug: Show full branch response
                        with st.expander("🔧 Debug: Production Branch Response", expanded=True):
                            st.json(prod_branch)

                        prod_branch_id = prod_branch.get('id') or prod_branch.get('branchId')

                        # Check if branch already existed (has configs)
                        # Use the branch object returned by get_or_create_branch
                        prod_configs_exist = prod_branch.get('metadata', {}).get('configsCount', 0) > 0

                        add_log('branch_creation', f"Production branch: '{prod_branch.get('name')}' (ID: {prod_branch_id}, Configs: {prod_branch.get('metadata', {}).get('configsCount', 0)})", 'success')

                        # Create test branch
                        add_log('branch_creation', f"Getting or creating test branch: {st.session_state['branch_name']}-test")
                        test_branch = branch_client.get_or_create_branch(f"{st.session_state['branch_name']}-test")

                        # Debug: Show full branch response
                        with st.expander("🔧 Debug: Test Branch Response", expanded=True):
                            st.json(test_branch)

                        test_branch_id = test_branch.get('id') or test_branch.get('branchId')

                        # Check if branch already existed (has configs)
                        # Use the branch object returned by get_or_create_branch
                        test_configs_exist = test_branch.get('metadata', {}).get('configsCount', 0) > 0

                        add_log('branch_creation', f"Test branch: '{test_branch.get('name')}' (ID: {test_branch_id}, Configs: {test_branch.get('metadata', {}).get('configsCount', 0)})", 'success')

                        # Give the API a moment to become consistent after branch creation
                        # This helps avoid eventual consistency issues
                        add_log('branch_creation', "Waiting 2 seconds for API consistency...")
                        time.sleep(2)

                        # Only poll if branches were just created (no configs yet)
                        skip_polling = prod_configs_exist and test_configs_exist

                        if skip_polling:
                            add_log('branch_creation', f"Both branches already have configurations - skipping readiness check", 'success')
                            add_log('branch_creation', f"Production: {prod_branch.get('metadata', {}).get('configsCount', 0)} configs")
                            add_log('branch_creation', f"Test: {test_branch.get('metadata', {}).get('configsCount', 0)} configs")
                        else:
                            add_log('branch_creation', "New branches detected - waiting for configurations to be copied...")
                            add_log('branch_creation', "Branch objects received, proceeding to configuration polling...")

                        import datetime
                        start_time = datetime.datetime.now()

                        if not skip_polling:
                            with st.spinner("Waiting for branch configurations to be copied..."):
                                elapsed_display = st.empty()
                                progress_bar = st.progress(0)

                                max_wait = 900  # 15 minutes - large projects with 1000+ configs need more time
                                poll_interval = 10  # Check every 10 seconds
                                attempts = 0
                                max_attempts = max_wait // poll_interval

                                both_ready = False
                                while attempts < max_attempts:
                                    elapsed = (datetime.datetime.now() - start_time).total_seconds()
                                    elapsed_display.caption(f"⏱️ Elapsed: {int(elapsed // 60)}m {int(elapsed % 60)}s | Attempt {attempts + 1}/{max_attempts}")

                                    # Check if both branches have configurations
                                    try:
                                        with st.expander(f"🔍 Debug: Polling attempt {attempts + 1}", expanded=False):
                                            st.write(f"Checking production branch {prod_branch_id}...")

                                            try:
                                                prod_config = branch_client.get_configuration_in_branch(
                                                    component_id=st.session_state['component_id'],
                                                    config_id=st.session_state['config_id'],
                                                    branch_id=prod_branch_id
                                                )
                                                st.write(f"✅ Production config found!")
                                                prod_ready = True
                                            except requests.exceptions.HTTPError as e:
                                                if e.response.status_code == 404:
                                                    st.write(f"⏳ Production config not copied yet (404)")
                                                    prod_ready = False
                                                else:
                                                    st.write(f"❌ Production config error: {e.response.status_code} - {e}")
                                                    raise  # Real error, don't continue

                                            st.write(f"Checking test branch {test_branch_id}...")

                                            try:
                                                test_config = branch_client.get_configuration_in_branch(
                                                    component_id=st.session_state['component_id'],
                                                    config_id=st.session_state['config_id'],
                                                    branch_id=test_branch_id
                                                )
                                                st.write(f"✅ Test config found!")
                                                test_ready = True
                                            except requests.exceptions.HTTPError as e:
                                                if e.response.status_code == 404:
                                                    st.write(f"⏳ Test config not copied yet (404)")
                                                    test_ready = False
                                                else:
                                                    st.write(f"❌ Test config error: {e.response.status_code} - {e}")
                                                    raise  # Real error, don't continue

                                        if prod_ready and test_ready:
                                            both_ready = True
                                            st.info("✅ Configurations found in both branches!")
                                            break

                                    except requests.exceptions.HTTPError as e:
                                        # Only non-404 errors reach here
                                        st.error(f"❌ Configuration check failed: {str(e)}")
                                        raise
                                    except Exception as e:
                                        # Unexpected errors
                                        with st.expander(f"⚠️ Unexpected error in attempt {attempts + 1}", expanded=True):
                                            st.write(f"**Error:** {str(e)}")
                                            st.write(f"**Error type:** {type(e).__name__}")
                                            st.exception(e)
                                        # Continue polling anyway

                                    time.sleep(poll_interval)
                                    attempts += 1
                                    progress_bar.progress(min(attempts / max_attempts, 0.99))

                                if both_ready:
                                    msg = f"Both branches are ready! (took {int(elapsed // 60)}m {int(elapsed % 60)}s)"
                                    st.success(f"✅ {msg}")
                                    add_log('branch_creation', msg, 'success')
                                else:
                                    msg = "Branches taking longer than expected. If configurations exist, proceeding anyway..."
                                    st.warning(f"⚠️ {msg}")
                                    add_log('branch_creation', msg, 'warning')

                        # Store branch IDs
                        st.session_state.production_branch_id = prod_branch_id
                        st.session_state.test_branch_id = test_branch_id

                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        error_msg = f"Failed to create branches: {str(e)}"
                        st.error(f"❌ {error_msg}")
                        st.exception(e)
                        add_log('branch_creation', error_msg, 'error')

    # Step 2: Production Configuration (with production tag)
    if st.session_state.get('production_branch_id') and st.session_state.get('test_branch_id'):
        with st.expander("Step 2: Update Production Branch Config", expanded=not st.session_state.get('production_config_updated')):
            st.info(f"""
            **Note:** When branches are created, they automatically copy all configurations from production.
            We'll update the existing configuration in the production branch to use tag: **{st.session_state['production_image_tag']}**
            """)

            if st.session_state.get('production_config_updated'):
                st.success(f"✅ Production config updated in branch (Config ID: {st.session_state['config_id']})")

                # Show preserved logs from config update
                display_logs('config_production')
            else:
                # Auto-run or manual button trigger
                trigger_prod_update = auto_run_enabled or st.button("Update Production Branch Config", type="primary", key="update_prod_config")

                if trigger_prod_update:
                    with st.spinner("Updating production configuration in branch..."):
                        try:
                            # Debug info
                            add_log('config_production', f"Updating config ID: {st.session_state['config_id']}")
                            add_log('config_production', f"In branch ID: {st.session_state['production_branch_id']}")
                            add_log('config_production', f"Component: {st.session_state['component_id']}")
                            add_log('config_production', f"Setting tag to: {st.session_state['production_image_tag']}")

                            # Update the existing config (auto-copied from main) in the branch
                            prod_config = client.update_configuration_tag(
                                component_id=st.session_state['component_id'],
                                config_id=st.session_state['config_id'],
                                config_data=st.session_state['original_config']['configuration'],
                                new_tag=st.session_state['production_image_tag'],
                                branch_id=st.session_state['production_branch_id']
                            )

                            # Verify the update by reading back from the branch
                            add_log('config_production', "Verifying update in production branch...")
                            verified_config = client.get_configuration_in_branch(
                                component_id=st.session_state['component_id'],
                                config_id=st.session_state['config_id'],
                                branch_id=st.session_state['production_branch_id']
                            )

                            verified_tag = verified_config.get('configuration', {}).get('runtime', {}).get('image_tag', 'NOT SET')

                            if verified_tag == st.session_state['production_image_tag']:
                                add_log('config_production', f"Production config updated in branch - Verified tag: {verified_tag}", 'success')
                                st.session_state.production_config_updated = True
                            else:
                                add_log('config_production', f"Verification failed! Expected tag: {st.session_state['production_image_tag']}, Got: {verified_tag}", 'error')

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
                            error_msg = f"Failed to update production configuration: {str(e)}"
                            add_log('config_production', error_msg, 'error')
                            st.error(f"❌ {error_msg}")
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

                # Show preserved logs from config update
                display_logs('config_test')
            else:
                # Auto-run or manual button trigger
                trigger_test_update = auto_run_enabled or st.button("Update Test Branch Config", type="primary", key="update_test_config")

                if trigger_test_update:
                    with st.spinner("Updating test configuration in branch..."):
                        try:
                            # Debug info
                            add_log('config_test', f"Updating config ID: {st.session_state['config_id']}")
                            add_log('config_test', f"In branch ID: {st.session_state['test_branch_id']}")
                            add_log('config_test', f"Setting tag to: {st.session_state['test_image_tag']}")

                            # Update the existing config (auto-copied from main) in the branch
                            test_config = client.update_configuration_tag(
                                component_id=st.session_state['component_id'],
                                config_id=st.session_state['config_id'],
                                config_data=st.session_state['original_config']['configuration'],
                                new_tag=st.session_state['test_image_tag'],
                                branch_id=st.session_state['test_branch_id']
                            )

                            # Verify the update by reading back from the branch
                            add_log('config_test', "Verifying update in test branch...")
                            verified_config = client.get_configuration_in_branch(
                                component_id=st.session_state['component_id'],
                                config_id=st.session_state['config_id'],
                                branch_id=st.session_state['test_branch_id']
                            )

                            verified_tag = verified_config.get('configuration', {}).get('runtime', {}).get('image_tag', 'NOT SET')

                            if verified_tag == st.session_state['test_image_tag']:
                                add_log('config_test', f"Test config updated in branch - Verified tag: {verified_tag}", 'success')
                                st.session_state.test_config_updated = True
                            else:
                                add_log('config_test', f"Verification failed! Expected tag: {st.session_state['test_image_tag']}, Got: {verified_tag}", 'error')

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
                            error_msg = f"Failed to update test configuration: {str(e)}"
                            add_log('config_test', error_msg, 'error')
                            st.error(f"❌ {error_msg}")
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

    # Auto-run or manual button trigger
    auto_run_enabled = st.session_state.get('auto_run', False)
    trigger_jobs = auto_run_enabled or st.button("Start Comparison Runs", type="primary", use_container_width=True)

    if trigger_jobs:
        with st.spinner("Triggering jobs..."):
            try:
                # Show debug info
                with st.expander("Debug Info", expanded=False):
                    st.write("Component ID:", st.session_state['component_id'])
                    st.write("Config ID:", st.session_state['config_id'])
                    st.write("Production Branch ID:", st.session_state['production_branch_id'])
                    st.write("Test Branch ID:", st.session_state['test_branch_id'])

                # Trigger production run (production branch with production tag)
                add_log('job_execution', f"Triggering production job in branch {st.session_state['production_branch_id']}...")
                prod_job = client.run_component(
                    st.session_state['component_id'],
                    st.session_state['config_id'],
                    branch_id=st.session_state['production_branch_id']
                )
                st.session_state.production_job_id = prod_job['id']
                st.session_state.production_job_status = 'waiting'
                add_log('job_execution', f"Production job triggered (ID: {prod_job['id']})", 'success')

                # Trigger test run (test branch with test tag)
                add_log('job_execution', f"Triggering test job in branch {st.session_state['test_branch_id']}...")
                test_job = client.run_component(
                    st.session_state['component_id'],
                    st.session_state['config_id'],
                    branch_id=st.session_state['test_branch_id']
                )
                st.session_state.test_job_id = test_job['id']
                st.session_state.test_job_status = 'waiting'
                add_log('job_execution', f"Test job triggered (ID: {test_job['id']})", 'success')

                add_log('job_execution', "Both jobs triggered successfully!", 'success')
                time.sleep(1)
                st.rerun()

            except Exception as e:
                error_msg = f"Failed to trigger jobs: {str(e)}"
                add_log('job_execution', error_msg, 'error')
                st.error(f"❌ {error_msg}")
                st.exception(e)


def monitoring_phase(client: KeboolaAPIClient):
    """
    Monitoring phase: Poll and display job status.

    Args:
        client: Keboola API client
    """
    st.subheader("📊 Job Monitoring")

    # Show preserved logs from job execution
    if st.session_state.get('job_execution_logs'):
        with st.expander("📋 Job Execution Log", expanded=False):
            display_logs('job_execution')

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

    # Log status updates
    if not st.session_state.get(f'job_monitoring_logged_{prod_status}_{test_status}'):
        add_log('job_monitoring', f"Production: {prod_status.upper()}, Test: {test_status.upper()}")
        st.session_state[f'job_monitoring_logged_{prod_status}_{test_status}'] = True

    # Auto-refresh every 5 seconds if jobs still running
    if prod_status in ['created', 'waiting', 'processing'] or test_status in ['created', 'waiting', 'processing']:
        st.info("⏳ Jobs are still running... Page will auto-refresh")
        time.sleep(5)
        st.rerun()

    # Both complete - proceed to comparison
    if prod_status == 'success' and test_status == 'success':
        st.markdown("---")
        st.success("✅ Both jobs completed successfully!")

        # Only log completion once
        if not st.session_state.get('jobs_completion_logged'):
            add_log('job_monitoring', "Both jobs completed successfully!", 'success')
            st.session_state.jobs_completion_logged = True

        # Show monitoring logs
        display_logs('job_monitoring')

        # Auto-run or manual button trigger
        auto_run_enabled = st.session_state.get('auto_run', False)

        # Prevent multiple comparison triggers
        if not st.session_state.get('comparison_triggered'):
            trigger_comparison = auto_run_enabled or st.button("Proceed to Comparison", type="primary", use_container_width=True)

            if trigger_comparison:
                st.session_state.comparison_triggered = True
                start_comparison(client)
        else:
            st.info("🔄 Comparison in progress or completed...")

    # Handle errors
    elif prod_status in ['error', 'cancelled', 'terminated'] or test_status in ['error', 'cancelled', 'terminated']:
        st.markdown("---")
        st.error("❌ One or more jobs failed or were terminated")
        add_log('job_monitoring', f"Job failure - Production: {prod_status}, Test: {test_status}", 'error')

        # Show monitoring logs
        display_logs('job_monitoring')

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
            add_log('comparison', "Starting comparison engine...")
            engine = ComparisonEngine(client)

            add_log('comparison', f"Comparing production branch {st.session_state['production_branch_id']} vs test branch {st.session_state['test_branch_id']}...")
            # Compare outputs from two separate branches
            results = engine.compare_outputs(
                production_branch=st.session_state['production_branch_id'],
                test_branch_id=st.session_state['test_branch_id']
            )

            st.session_state.comparison_results = results
            add_log('comparison', "Comparison completed successfully!", 'success')

            st.success("✅ Comparison complete!")
            st.info("👉 Navigate to **📊 Results** in the sidebar to view comparison")

            time.sleep(2)
            st.rerun()

        except Exception as e:
            error_msg = f"Comparison failed: {str(e)}"
            add_log('comparison', error_msg, 'error')
            st.error(f"❌ {error_msg}")
            st.exception(e)
