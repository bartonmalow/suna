"""
API endpoints for workspace cleanup operations.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import asyncio
from datetime import datetime, timedelta
import logging

from sandbox.cleanup import cleanup_old_sandboxes, perform_full_cleanup
from sandbox.sandbox import delete_sandbox
from utils.auth_utils import get_current_user, UserClaims
from utils.logger import logger

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])

class CleanupRequest(BaseModel):
    """Request model for cleanup operations"""
    sandbox_ids: Optional[List[str]] = None
    conversation_ids: Optional[List[str]] = None
    max_age_hours: Optional[int] = None
    force: bool = False

class CleanupResult(BaseModel):
    """Result model for cleanup operations"""
    success: bool
    sandbox_id: str
    error: Optional[str] = None

class CleanupResponse(BaseModel):
    """Response model for cleanup operations"""
    total_requested: int
    successful: int
    failed: int
    results: List[CleanupResult]
    summary: str

@router.post("/sandboxes", response_model=CleanupResponse)
async def cleanup_sandboxes(
    request: CleanupRequest,
    user: UserClaims = Depends(get_current_user)
):
    """
    Clean up specific sandboxes by ID.
    """
    if not request.sandbox_ids:
        raise HTTPException(status_code=400, detail="No sandbox IDs provided")
    
    logger.info(f"User {user.id} requested cleanup of {len(request.sandbox_ids)} sandboxes")
    
    results = []
    successful = 0
    failed = 0
    
    for sandbox_id in request.sandbox_ids:
        try:
            success = await delete_sandbox(sandbox_id)
            if success:
                results.append(CleanupResult(success=True, sandbox_id=sandbox_id))
                successful += 1
                logger.info(f"Successfully deleted sandbox {sandbox_id}")
            else:
                results.append(CleanupResult(
                    success=False, 
                    sandbox_id=sandbox_id, 
                    error="Delete operation returned false"
                ))
                failed += 1
        except Exception as e:
            error_msg = str(e)
            results.append(CleanupResult(
                success=False, 
                sandbox_id=sandbox_id, 
                error=error_msg
            ))
            failed += 1
            logger.error(f"Failed to delete sandbox {sandbox_id}: {error_msg}")
    
    summary = f"Cleaned up {successful} of {len(request.sandbox_ids)} sandboxes"
    if failed > 0:
        summary += f" ({failed} failed)"
    
    return CleanupResponse(
        total_requested=len(request.sandbox_ids),
        successful=successful,
        failed=failed,
        results=results,
        summary=summary
    )

@router.post("/conversations", response_model=CleanupResponse)
async def cleanup_conversations(
    request: CleanupRequest,
    user: UserClaims = Depends(get_current_user)
):
    """
    Clean up sandboxes associated with conversation IDs.
    This endpoint maps conversation IDs to sandbox IDs and cleans them up.
    """
    if not request.conversation_ids:
        raise HTTPException(status_code=400, detail="No conversation IDs provided")
    
    logger.info(f"User {user.id} requested conversation cleanup for {len(request.conversation_ids)} conversations")
    
    from services.supabase import DBConnection
    
    results = []
    successful = 0
    failed = 0
    
    db = DBConnection()
    client = await db.client
    
    try:
        # Look up sandbox IDs associated with conversation IDs
        # This assumes there's a mapping table or field that tracks conversation->sandbox relationships
        sandbox_ids = []
        
        for conversation_id in request.conversation_ids:
            try:
                # Query projects table for sandboxes associated with conversation
                # You may need to adjust this query based on your schema
                result = await client.table('projects').select('sandbox').eq('conversation_id', conversation_id).execute()
                
                for project in result.data:
                    sandbox_info = project.get('sandbox', {})
                    if sandbox_info and isinstance(sandbox_info, dict):
                        sandbox_id = sandbox_info.get('id')
                        if sandbox_id:
                            sandbox_ids.append(sandbox_id)
                            
            except Exception as e:
                logger.warning(f"Failed to find sandbox for conversation {conversation_id}: {e}")
        
        # Clean up the found sandboxes
        for sandbox_id in sandbox_ids:
            try:
                success = await delete_sandbox(sandbox_id)
                if success:
                    results.append(CleanupResult(success=True, sandbox_id=sandbox_id))
                    successful += 1
                    logger.info(f"Successfully deleted sandbox {sandbox_id}")
                else:
                    results.append(CleanupResult(
                        success=False, 
                        sandbox_id=sandbox_id, 
                        error="Delete operation returned false"
                    ))
                    failed += 1
            except Exception as e:
                error_msg = str(e)
                results.append(CleanupResult(
                    success=False, 
                    sandbox_id=sandbox_id, 
                    error=error_msg
                ))
                failed += 1
                logger.error(f"Failed to delete sandbox {sandbox_id}: {error_msg}")
        
        summary = f"Found {len(sandbox_ids)} sandboxes for {len(request.conversation_ids)} conversations, cleaned up {successful}"
        if failed > 0:
            summary += f" ({failed} failed)"
            
    finally:
        await db.close()
    
    return CleanupResponse(
        total_requested=len(sandbox_ids),
        successful=successful,
        failed=failed,
        results=results,
        summary=summary
    )

@router.post("/old", response_model=CleanupResponse)
async def cleanup_old_sandboxes_endpoint(
    request: CleanupRequest,
    user: UserClaims = Depends(get_current_user)
):
    """
    Clean up sandboxes older than specified age.
    """
    max_age_hours = request.max_age_hours or 24
    
    logger.info(f"User {user.id} requested cleanup of sandboxes older than {max_age_hours} hours")
    
    try:
        deleted_count = await cleanup_old_sandboxes(max_age_hours)
        
        return CleanupResponse(
            total_requested=deleted_count,
            successful=deleted_count,
            failed=0,
            results=[],
            summary=f"Cleaned up {deleted_count} sandboxes older than {max_age_hours} hours"
        )
        
    except Exception as e:
        logger.error(f"Failed to cleanup old sandboxes: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

@router.post("/full", response_model=dict)
async def full_cleanup(
    request: CleanupRequest,
    user: UserClaims = Depends(get_current_user)
):
    """
    Perform comprehensive cleanup of all sandbox resources.
    """
    logger.info(f"User {user.id} requested full cleanup")
    
    try:
        stats = await perform_full_cleanup()
        
        logger.info(f"Full cleanup completed: {stats}")
        
        return {
            "success": True,
            "statistics": stats,
            "summary": f"Full cleanup completed: {sum(stats.values())} total resources cleaned"
        }
        
    except Exception as e:
        logger.error(f"Full cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Full cleanup failed: {str(e)}")

@router.get("/stats")
async def cleanup_stats(user: UserClaims = Depends(get_current_user)):
    """
    Get cleanup statistics and current sandbox counts.
    """
    from sandbox.sandbox import daytona
    from services.supabase import DBConnection
    
    try:
        # Get sandbox counts from Daytona
        daytona_sandboxes = await daytona.list()
        daytona_count = len(daytona_sandboxes)
        
        # Get database sandbox references
        db = DBConnection()
        client = await db.client
        
        try:
            result = await client.table('projects').select('sandbox').execute()
            db_sandbox_count = sum(1 for project in result.data if project.get('sandbox'))
        finally:
            await db.close()
        
        # Calculate ages of current sandboxes
        now = datetime.utcnow()
        ages = []
        for sandbox in daytona_sandboxes:
            if hasattr(sandbox, 'created_at') and sandbox.created_at:
                try:
                    created_at = datetime.fromisoformat(sandbox.created_at.replace('Z', '+00:00'))
                    age_hours = (now - created_at).total_seconds() / 3600
                    ages.append(age_hours)
                except:
                    pass
        
        stats = {
            "daytona_sandboxes": daytona_count,
            "database_references": db_sandbox_count,
            "orphaned_sandboxes": max(0, daytona_count - db_sandbox_count),
            "average_age_hours": sum(ages) / len(ages) if ages else 0,
            "oldest_sandbox_hours": max(ages) if ages else 0,
            "sandboxes_over_24h": sum(1 for age in ages if age > 24),
            "sandboxes_over_12h": sum(1 for age in ages if age > 12),
            "sandboxes_over_6h": sum(1 for age in ages if age > 6)
        }
        
        return {
            "success": True,
            "statistics": stats,
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get cleanup stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")