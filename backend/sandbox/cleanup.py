"""
Automatic sandbox cleanup functions for maintaining system health.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sandbox.sandbox import delete_sandbox, daytona
from utils.db import DBConnection
from utils.logger import logger

async def cleanup_old_sandboxes(max_age_hours: int = 24) -> int:
    """
    Clean up sandboxes older than the specified age.
    
    Args:
        max_age_hours: Maximum age in hours before a sandbox is considered old
        
    Returns:
        Number of sandboxes cleaned up
    """
    try:
        # Get all sandboxes from Daytona
        sandboxes = await daytona.list()
        old_sandboxes = []
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        for sandbox in sandboxes:
            # Check if sandbox is old (created before cutoff)
            if hasattr(sandbox, 'created_at') and sandbox.created_at:
                created_at = datetime.fromisoformat(sandbox.created_at.replace('Z', '+00:00'))
                if created_at < cutoff_time:
                    old_sandboxes.append(sandbox.id)
        
        if not old_sandboxes:
            logger.info(f"No sandboxes older than {max_age_hours} hours found")
            return 0
        
        logger.info(f"Found {len(old_sandboxes)} sandboxes older than {max_age_hours} hours")
        
        # Delete old sandboxes
        deleted_count = 0
        for sandbox_id in old_sandboxes:
            try:
                success = await delete_sandbox(sandbox_id)
                if success:
                    deleted_count += 1
                    logger.info(f"Deleted old sandbox: {sandbox_id}")
                else:
                    logger.warning(f"Failed to delete old sandbox: {sandbox_id}")
            except Exception as e:
                logger.error(f"Error deleting old sandbox {sandbox_id}: {str(e)}")
        
        logger.info(f"Cleaned up {deleted_count} old sandboxes")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error during old sandbox cleanup: {str(e)}")
        return 0

async def cleanup_failed_agent_sandboxes() -> int:
    """
    Clean up sandboxes associated with failed agent runs.
    
    Returns:
        Number of sandboxes cleaned up
    """
    db = DBConnection()
    client = await db.client
    
    try:
        # Find failed agent runs from the last 24 hours that still have active projects
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        failed_runs = await client.table('agent_runs').select(
            'id, project_id, status, created_at'
        ).eq('status', 'failed').gte('created_at', cutoff_time.isoformat()).execute()
        
        if not failed_runs.data:
            logger.info("No recent failed agent runs found")
            return 0
        
        deleted_count = 0
        for run in failed_runs.data:
            project_id = run['project_id']
            
            # Get the project's sandbox info
            project = await client.table('projects').select('sandbox').eq('project_id', project_id).execute()
            
            if project.data and project.data[0].get('sandbox'):
                sandbox_info = project.data[0]['sandbox']
                sandbox_id = sandbox_info.get('id')
                
                if sandbox_id:
                    try:
                        logger.info(f"Cleaning up sandbox {sandbox_id} from failed run {run['id']}")
                        success = await delete_sandbox(sandbox_id)
                        
                        if success:
                            # Clear the sandbox reference from the project
                            await client.table('projects').update({'sandbox': None}).eq('project_id', project_id).execute()
                            deleted_count += 1
                            logger.info(f"Cleaned up sandbox {sandbox_id} from failed agent run")
                        else:
                            logger.warning(f"Failed to delete sandbox {sandbox_id}")
                            
                    except Exception as e:
                        logger.error(f"Error cleaning up sandbox {sandbox_id}: {str(e)}")
        
        logger.info(f"Cleaned up {deleted_count} sandboxes from failed agent runs")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error during failed agent sandbox cleanup: {str(e)}")
        return 0
    finally:
        await db.close()

async def perform_full_cleanup() -> Dict[str, int]:
    """
    Perform a comprehensive cleanup of all sandbox resources.
    
    Returns:
        Dictionary with cleanup statistics
    """
    logger.info("Starting comprehensive sandbox cleanup")
    
    stats = {
        'orphaned_sandboxes': 0,
        'old_sandboxes': 0,
        'failed_run_sandboxes': 0,
        'stale_project_refs': 0
    }
    
    try:
        # Clean up orphaned sandboxes (exist in Daytona but not in DB)
        db = DBConnection()
        client = await db.client
        
        # Get sandboxes from both sources
        db_result = await client.table('projects').select('sandbox').execute()
        db_sandbox_ids = set()
        project_sandbox_map = {}
        
        for project in db_result.data:
            sandbox_info = project.get('sandbox', {})
            if sandbox_info and isinstance(sandbox_info, dict):
                sandbox_id = sandbox_info.get('id')
                if sandbox_id:
                    db_sandbox_ids.add(sandbox_id)
                    project_sandbox_map[sandbox_id] = project
        
        daytona_sandboxes = await daytona.list()
        daytona_sandbox_ids = {s.id for s in daytona_sandboxes}
        
        # Clean up orphaned sandboxes
        orphaned = daytona_sandbox_ids - db_sandbox_ids
        for sandbox_id in orphaned:
            try:
                success = await delete_sandbox(sandbox_id)
                if success:
                    stats['orphaned_sandboxes'] += 1
            except Exception as e:
                logger.error(f"Failed to delete orphaned sandbox {sandbox_id}: {str(e)}")
        
        # Clean up stale project references
        stale_refs = db_sandbox_ids - daytona_sandbox_ids
        for sandbox_id in stale_refs:
            try:
                project = project_sandbox_map.get(sandbox_id)
                if project:
                    await client.table('projects').update({'sandbox': None}).eq('project_id', project['project_id']).execute()
                    stats['stale_project_refs'] += 1
            except Exception as e:
                logger.error(f"Failed to clean stale reference for sandbox {sandbox_id}: {str(e)}")
        
        await db.close()
        
        # Clean up old sandboxes (older than 24 hours)
        stats['old_sandboxes'] = await cleanup_old_sandboxes(max_age_hours=24)
        
        # Clean up sandboxes from failed runs
        stats['failed_run_sandboxes'] = await cleanup_failed_agent_sandboxes()
        
        total_cleaned = sum(stats.values())
        logger.info(f"Comprehensive cleanup completed: {total_cleaned} total resources cleaned")
        logger.info(f"Stats: {stats}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error during comprehensive cleanup: {str(e)}")
        return stats

# Background task that can be run periodically
async def start_periodic_cleanup(interval_hours: int = 6):
    """
    Start a background task that performs cleanup every interval_hours.
    
    Args:
        interval_hours: How often to run cleanup (in hours)
    """
    logger.info(f"Starting periodic sandbox cleanup every {interval_hours} hours")
    
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)  # Convert hours to seconds
            logger.info("Running periodic sandbox cleanup")
            await perform_full_cleanup()
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {str(e)}")
            # Continue running even if one cleanup fails
            await asyncio.sleep(300)  # Wait 5 minutes before retrying