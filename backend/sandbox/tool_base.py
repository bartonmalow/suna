from typing import Optional
import uuid
import asyncio

from agentpress.thread_manager import ThreadManager
from agentpress.tool import Tool
from daytona_sdk import AsyncSandbox
from sandbox.sandbox import get_or_start_sandbox, create_sandbox, delete_sandbox
from utils.logger import logger
from utils.files_utils import clean_path
from utils.config import config

class SandboxToolsBase(Tool):
    """Base class for all sandbox tools that provides project-based sandbox access."""
    
    # Class variable to track if sandbox URLs have been printed
    _urls_printed = False
    
    def __init__(self, project_id: str, thread_manager: Optional[ThreadManager] = None):
        super().__init__()
        self.project_id = project_id
        self.thread_manager = thread_manager
        self.workspace_path = "/workspace"
        self._sandbox = None
        self._sandbox_id = None
        self._sandbox_pass = None

    async def _ensure_sandbox(self) -> AsyncSandbox:
        """Ensure we have a valid sandbox instance, retrieving it from the project if needed.

        If the project does not yet have a sandbox, create it lazily and persist
        the metadata to the `projects` table so subsequent calls can reuse it.
        """
        logger.info(f"[ENSURE_SANDBOX] Starting sandbox initialization for project: {self.project_id}")
        
        if self._sandbox is None:
            try:
                # Step 1: Get database client
                logger.info(f"[ENSURE_SANDBOX] Step 1: Getting database client...")
                client = await self.thread_manager.db.client
                logger.info(f"[ENSURE_SANDBOX] ✅ Database client obtained successfully")
                
                # Step 2: Get project data
                logger.info(f"[ENSURE_SANDBOX] Step 2: Fetching project data for ID: {self.project_id}")
                project = await client.table('projects').select('*').eq('project_id', self.project_id).execute()
                logger.info(f"[ENSURE_SANDBOX] Project query result: {len(project.data) if project.data else 0} records found")
                
                if not project.data or len(project.data) == 0:
                    logger.error(f"[ENSURE_SANDBOX] ❌ Project not found: {self.project_id}")
                    raise ValueError(f"Project {self.project_id} not found in database. Please verify project exists.")
                
                project_data = project.data[0]
                logger.info(f"[ENSURE_SANDBOX] Project data keys: {list(project_data.keys())}")
                
                # Step 3: Extract sandbox info
                logger.info(f"[ENSURE_SANDBOX] Step 3: Extracting sandbox information...")
                sandbox_info = project_data.get('sandbox', {})
                logger.info(f"[ENSURE_SANDBOX] Sandbox info: {sandbox_info}")
                
                if not sandbox_info.get('id'):
                    logger.error(f"[ENSURE_SANDBOX] ❌ No sandbox ID found for project {self.project_id}")
                    logger.error(f"[ENSURE_SANDBOX] Sandbox info content: {sandbox_info}")
                    raise ValueError(f"No sandbox found for project {self.project_id}")
                
                # Step 4: Store sandbox info
                logger.info(f"[ENSURE_SANDBOX] Step 4: Storing sandbox information...")
                self._sandbox_id = sandbox_info['id']
                self._sandbox_pass = sandbox_info.get('pass')
                logger.info(f"[ENSURE_SANDBOX] Sandbox ID: {self._sandbox_id}")
                logger.info(f"[ENSURE_SANDBOX] Sandbox pass: {'***set***' if self._sandbox_pass else 'not set'}")
                
                # Step 5: Get or start the sandbox
                logger.info(f"[ENSURE_SANDBOX] Step 5: Getting or starting sandbox...")
                self._sandbox = await get_or_start_sandbox(self._sandbox_id)
                logger.info(f"[ENSURE_SANDBOX] ✅ Sandbox instance obtained successfully")
                
                # # Log URLs if not already printed
                # if not SandboxToolsBase._urls_printed:
                #     vnc_link = self._sandbox.get_preview_link(6080)
                #     website_link = self._sandbox.get_preview_link(8080)
                    
                #     vnc_url = vnc_link.url if hasattr(vnc_link, 'url') else str(vnc_link)
                #     website_url = website_link.url if hasattr(website_link, 'url') else str(website_link)
                    
                #     print("\033[95m***")
                #     print(f"VNC URL: {vnc_url}")
                #     print(f"Website URL: {website_url}")
                #     print("***\033[0m")
                #     SandboxToolsBase._urls_printed = True
                
            except Exception as e:
                logger.error(f"[ENSURE_SANDBOX] ❌ FATAL ERROR during sandbox initialization: {str(e)}", exc_info=True)
                logger.error(f"[ENSURE_SANDBOX] Error type: {type(e).__name__}")
                logger.error(f"[ENSURE_SANDBOX] Error args: {e.args}")
                logger.error(f"[ENSURE_SANDBOX] Project ID: {self.project_id}")
                
                if "not found" in str(e).lower():
                    logger.error(f"[ENSURE_SANDBOX] Project not found error")
                    raise ValueError(f"Project {self.project_id} not found in database. Please verify project exists.")
                elif "sandbox" in str(e).lower():
                    logger.error(f"[ENSURE_SANDBOX] Sandbox-specific error")
                    raise ValueError(f"Sandbox initialization failed for project {self.project_id}: {str(e)}")
                else:
                    logger.error(f"[ENSURE_SANDBOX] General database/service error")
                    raise ValueError(f"Database or sandbox service error for project {self.project_id}: {str(e)}")
        else:
            logger.info(f"[ENSURE_SANDBOX] Sandbox already initialized for project: {self.project_id}")
        
        logger.info(f"[ENSURE_SANDBOX] ✅ Sandbox ready - returning instance")
        return self._sandbox

    @property
    def sandbox(self) -> AsyncSandbox:
        """Get the sandbox instance, ensuring it exists."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not initialized. Call _ensure_sandbox() first.")
        return self._sandbox

    @property
    def sandbox_id(self) -> str:
        """Get the sandbox ID, ensuring it exists."""
        if self._sandbox_id is None:
            raise RuntimeError("Sandbox ID not initialized. Call _ensure_sandbox() first.")
        return self._sandbox_id

    def clean_path(self, path: str) -> str:
        """Clean and normalize a path to be relative to /workspace."""
        cleaned_path = clean_path(path, self.workspace_path)
        logger.debug(f"Cleaned path: {path} -> {cleaned_path}")
        return cleaned_path