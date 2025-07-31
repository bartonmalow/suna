#!/usr/bin/env python3
"""
Emergency script to clean up orphaned sandboxes that are consuming resources.
Run this to fix "Failed to create sandbox" errors.

Usage:
    python scripts/cleanup_orphaned_sandboxes.py --dry-run  # See what would be deleted
    python scripts/cleanup_orphaned_sandboxes.py           # Actually delete orphaned sandboxes
"""

import asyncio
import argparse
import logging
from typing import List, Dict, Any
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox.sandbox import delete_sandbox
from utils.db import DBConnection
from utils.logger import logger

async def get_database_sandboxes(client) -> Dict[str, str]:
    """Get all sandbox IDs from the database with their project IDs."""
    try:
        result = await client.table('projects').select('project_id, sandbox').execute()
        
        db_sandboxes = {}
        for project in result.data:
            sandbox_info = project.get('sandbox', {})
            if sandbox_info and isinstance(sandbox_info, dict):
                sandbox_id = sandbox_info.get('id')
                if sandbox_id:
                    db_sandboxes[sandbox_id] = project['project_id']
                    
        logger.info(f"Found {len(db_sandboxes)} sandboxes in database")
        return db_sandboxes
        
    except Exception as e:
        logger.error(f"Failed to get database sandboxes: {str(e)}")
        return {}

async def get_daytona_sandboxes() -> List[str]:
    """Get all sandbox IDs from Daytona."""
    try:
        from sandbox.sandbox import daytona
        
        # List all sandboxes in Daytona
        sandboxes = await daytona.list()
        sandbox_ids = [s.id for s in sandboxes]
        
        logger.info(f"Found {len(sandbox_ids)} sandboxes in Daytona")
        return sandbox_ids
        
    except Exception as e:
        logger.error(f"Failed to get Daytona sandboxes: {str(e)}")
        return []

async def cleanup_orphaned_sandboxes(dry_run: bool = True) -> int:
    """Clean up sandboxes that exist in Daytona but not in the database."""
    db = DBConnection()
    client = await db.client
    
    try:
        # Get sandboxes from both sources
        db_sandboxes = await get_database_sandboxes(client)
        daytona_sandboxes = await get_daytona_sandboxes()
        
        # Find orphaned sandboxes (in Daytona but not in DB)
        orphaned_sandboxes = []
        for sandbox_id in daytona_sandboxes:
            if sandbox_id not in db_sandboxes:
                orphaned_sandboxes.append(sandbox_id)
        
        logger.info(f"Found {len(orphaned_sandboxes)} orphaned sandboxes")
        
        if not orphaned_sandboxes:
            logger.info("No orphaned sandboxes found - system is clean!")
            return 0
            
        if dry_run:
            logger.info("DRY RUN - Would delete the following orphaned sandboxes:")
            for sandbox_id in orphaned_sandboxes:
                logger.info(f"  - {sandbox_id}")
            logger.info(f"Run without --dry-run to actually delete {len(orphaned_sandboxes)} sandboxes")
            return len(orphaned_sandboxes)
        
        # Actually delete orphaned sandboxes
        deleted_count = 0
        failed_count = 0
        
        for sandbox_id in orphaned_sandboxes:
            try:
                logger.info(f"Deleting orphaned sandbox: {sandbox_id}")
                success = await delete_sandbox(sandbox_id)
                
                if success:
                    deleted_count += 1
                    logger.info(f"✅ Successfully deleted sandbox {sandbox_id}")
                else:
                    failed_count += 1
                    logger.error(f"❌ Failed to delete sandbox {sandbox_id}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Error deleting sandbox {sandbox_id}: {str(e)}")
        
        logger.info(f"Cleanup completed: {deleted_count} deleted, {failed_count} failed")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Cleanup process failed: {str(e)}")
        return 0
    finally:
        await db.close()

async def cleanup_stale_projects(dry_run: bool = True) -> int:
    """Clean up database projects that reference non-existent sandboxes."""
    db = DBConnection()
    client = await db.client
    
    try:
        db_sandboxes = await get_database_sandboxes(client)
        daytona_sandboxes = await get_daytona_sandboxes()
        
        # Find projects with sandbox IDs that don't exist in Daytona
        stale_projects = []
        for sandbox_id, project_id in db_sandboxes.items():
            if sandbox_id not in daytona_sandboxes:
                stale_projects.append((project_id, sandbox_id))
        
        logger.info(f"Found {len(stale_projects)} projects with stale sandbox references")
        
        if not stale_projects:
            logger.info("No stale project references found!")
            return 0
            
        if dry_run:
            logger.info("DRY RUN - Would clean up the following project sandbox references:")
            for project_id, sandbox_id in stale_projects:
                logger.info(f"  - Project {project_id} -> Sandbox {sandbox_id}")
            return len(stale_projects)
        
        # Actually clean up stale references
        cleaned_count = 0
        for project_id, sandbox_id in stale_projects:
            try:
                await client.table('projects').update({'sandbox': None}).eq('project_id', project_id).execute()
                cleaned_count += 1
                logger.info(f"✅ Cleaned stale sandbox reference for project {project_id}")
            except Exception as e:
                logger.error(f"❌ Failed to clean project {project_id}: {str(e)}")
        
        logger.info(f"Cleaned {cleaned_count} stale project references")
        return cleaned_count
        
    except Exception as e:
        logger.error(f"Stale project cleanup failed: {str(e)}")
        return 0
    finally:
        await db.close()

async def main():
    parser = argparse.ArgumentParser(description="Clean up orphaned Suna sandboxes")
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be cleaned up without actually doing it')
    parser.add_argument('--stale-projects', action='store_true',
                       help='Also clean up database projects with non-existent sandbox references')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    else:
        logger.info("🧹 CLEANUP MODE - Will delete orphaned resources")
    
    try:
        # Clean up orphaned sandboxes
        deleted_sandboxes = await cleanup_orphaned_sandboxes(dry_run=args.dry_run)
        
        # Clean up stale project references if requested
        cleaned_projects = 0
        if args.stale_projects:
            cleaned_projects = await cleanup_stale_projects(dry_run=args.dry_run)
        
        if args.dry_run:
            logger.info(f"🎯 Summary: Found {deleted_sandboxes} orphaned sandboxes" + 
                       (f" and {cleaned_projects} stale project references" if args.stale_projects else ""))
            logger.info("Run without --dry-run to perform actual cleanup")
        else:
            logger.info(f"✅ Cleanup complete: {deleted_sandboxes} sandboxes deleted" +
                       (f", {cleaned_projects} project references cleaned" if args.stale_projects else ""))
            
    except KeyboardInterrupt:
        logger.info("Cleanup interrupted by user")
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())