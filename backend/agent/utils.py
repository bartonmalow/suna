import json
from typing import Optional
from utils.logger import logger
from services import redis
from sandbox.sandbox import delete_sandbox


async def _cleanup_redis_response_list(agent_run_id: str):
    try:
        response_list_key = f"agent_run:{agent_run_id}:responses"
        await redis.delete(response_list_key)
        logger.debug(f"Cleaned up Redis response list for agent run {agent_run_id}")
    except Exception as e:
        logger.warning(f"Failed to clean up Redis response list for {agent_run_id}: {str(e)}")

async def _cleanup_project_sandbox(client, agent_run_id: str):
    """Clean up the sandbox associated with an agent run's project."""
    try:
        # Get the agent run to find the project_id
        agent_run_result = await client.table('agent_runs').select('project_id').eq('id', agent_run_id).execute()
        
        if not agent_run_result.data or len(agent_run_result.data) == 0:
            logger.warning(f"No agent run found with ID {agent_run_id} for sandbox cleanup")
            return
            
        project_id = agent_run_result.data[0]['project_id']
        
        # Get the project to find the sandbox ID
        project_result = await client.table('projects').select('sandbox').eq('project_id', project_id).execute()
        
        if not project_result.data or len(project_result.data) == 0:
            logger.warning(f"No project found with ID {project_id} for sandbox cleanup")
            return
            
        sandbox_info = project_result.data[0].get('sandbox', {})
        sandbox_id = sandbox_info.get('id')
        
        if not sandbox_id:
            logger.info(f"No sandbox ID found for project {project_id} - skipping cleanup")
            return
            
        # Delete the sandbox
        logger.info(f"Cleaning up sandbox {sandbox_id} for project {project_id}")
        success = await delete_sandbox(sandbox_id)
        
        if success:
            # Update the project to remove sandbox info
            await client.table('projects').update({'sandbox': None}).eq('project_id', project_id).execute()
            logger.info(f"Successfully deleted sandbox {sandbox_id} and updated project {project_id}")
        else:
            logger.error(f"Failed to delete sandbox {sandbox_id} for project {project_id}")
            
    except Exception as e:
        logger.error(f"Error during sandbox cleanup for agent run {agent_run_id}: {str(e)}")
        # Don't re-raise - cleanup failures shouldn't block agent run stopping


async def check_for_active_project_agent_run(client, project_id: str):
    project_threads = await client.table('threads').select('thread_id').eq('project_id', project_id).execute()
    project_thread_ids = [t['thread_id'] for t in project_threads.data]

    if project_thread_ids:
        active_runs = await client.table('agent_runs').select('id').in_('thread_id', project_thread_ids).eq('status', 'running').execute()
        if active_runs.data and len(active_runs.data) > 0:
            return active_runs.data[0]['id']
    return None


async def stop_agent_run(db, agent_run_id: str, error_message: Optional[str] = None):
    logger.info(f"Stopping agent run: {agent_run_id}")
    client = await db.client
    final_status = "failed" if error_message else "stopped"

    response_list_key = f"agent_run:{agent_run_id}:responses"
    all_responses = []
    try:
        all_responses_json = await redis.lrange(response_list_key, 0, -1)
        all_responses = [json.loads(r) for r in all_responses_json]
        logger.info(f"Fetched {len(all_responses)} responses from Redis for DB update on stop/fail: {agent_run_id}")
    except Exception as e:
        logger.error(f"Failed to fetch responses from Redis for {agent_run_id} during stop/fail: {e}")

    update_success = await update_agent_run_status(
        client, agent_run_id, final_status, error=error_message, responses=all_responses
    )

    if not update_success:
        logger.error(f"Failed to update database status for stopped/failed run {agent_run_id}")

    global_control_channel = f"agent_run:{agent_run_id}:control"
    try:
        await redis.publish(global_control_channel, "STOP")
        logger.debug(f"Published STOP signal to global channel {global_control_channel}")
    except Exception as e:
        logger.error(f"Failed to publish STOP signal to global channel {global_control_channel}: {str(e)}")

    try:
        instance_keys = await redis.keys(f"active_run:*:{agent_run_id}")
        logger.debug(f"Found {len(instance_keys)} active instance keys for agent run {agent_run_id}")

        for key in instance_keys:
            parts = key.split(":")
            if len(parts) == 3:
                instance_id_from_key = parts[1]
                instance_control_channel = f"agent_run:{agent_run_id}:control:{instance_id_from_key}"
                try:
                    await redis.publish(instance_control_channel, "STOP")
                    logger.debug(f"Published STOP signal to instance channel {instance_control_channel}")
                except Exception as e:
                    logger.warning(f"Failed to publish STOP signal to instance channel {instance_control_channel}: {str(e)}")
            else:
                 logger.warning(f"Unexpected key format found: {key}")

        await _cleanup_redis_response_list(agent_run_id)

    except Exception as e:
        logger.error(f"Failed to find or signal active instances for {agent_run_id}: {str(e)}")

    # 🔧 FIX: Add sandbox cleanup when agent run stops/fails
    await _cleanup_project_sandbox(client, agent_run_id)

    logger.info(f"Successfully initiated stop process for agent run: {agent_run_id}") 