from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from ..domain.entities import (
    AgentVersion, VersionId, AgentId, UserId, VersionNumber,
    SystemPrompt, MCPConfiguration, ToolConfiguration, VersionStatus
)
from ..infrastructure.supabase_repositories import (
    SupabaseVersionRepository, SupabaseAgentRepository
)
from services.supabase import DBConnection
from .exceptions import (
    VersionNotFoundError, AgentNotFoundError, UnauthorizedError,
    InvalidVersionError, VersionConflictError
)


class VersionService:
    def __init__(self, db_connection: Optional[DBConnection] = None):
        if db_connection:
            self.db = db_connection
        else:
            self.db = DBConnection()
    
    async def _get_client(self):
        return await self.db.client
    
    async def _verify_agent_access(self, agent_id: str, user_id: str) -> tuple[bool, bool]:
        if user_id == "system":
            return True, True
            
        client = await self._get_client()
        
        owner_result = await client.table('agents').select('account_id').eq(
            'agent_id', agent_id
        ).eq('account_id', user_id).execute()
        
        is_owner = bool(owner_result.data)
        
        public_result = await client.table('agents').select('is_public').eq(
            'agent_id', agent_id
        ).execute()
        
        is_public = bool(public_result.data and public_result.data[0].get('is_public', False))
        
        return is_owner, is_public
    
    async def create_version(
        self,
        agent_id: AgentId,
        user_id: UserId,
        system_prompt: str,
        configured_mcps: List[Dict[str, Any]],
        custom_mcps: List[Dict[str, Any]],
        agentpress_tools: Dict[str, Any],
        version_name: Optional[str] = None,
        change_description: Optional[str] = None
    ) -> AgentVersion:
        is_owner, is_public = await self._verify_agent_access(agent_id, user_id)
        
        if not is_owner and not is_public:
            raise UnauthorizedError("You don't have permission to create versions for this agent")
        
        client = await self._get_client()
        agent = await SupabaseAgentRepository(client).find_by_id(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        
        version_number = await SupabaseVersionRepository(client).get_next_version_number(agent_id)
        version_name = version_name or str(version_number)
        current_active = await SupabaseVersionRepository(client).find_active_version(agent_id)
        
        version = AgentVersion(
            version_id=VersionId.generate(),
            agent_id=agent_id,
            version_number=version_number,
            version_name=version_name,
            system_prompt=SystemPrompt(system_prompt),
            configured_mcps=[
                MCPConfiguration(
                    name=mcp['name'],
                    type=mcp.get('type', 'sse'),
                    config=mcp.get('config', {}),
                    enabled_tools=mcp.get('enabledTools', [])
                )
                for mcp in configured_mcps
            ],
            custom_mcps=[
                MCPConfiguration(
                    name=mcp['name'],
                    type=mcp.get('type', 'sse'),
                    config=mcp.get('config', {}),
                    enabled_tools=mcp.get('enabledTools', [])
                )
                for mcp in custom_mcps
            ],
            tool_configuration=ToolConfiguration(tools=agentpress_tools),
            status=VersionStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by=user_id,
            change_description=change_description,
            previous_version_id=current_active.version_id if current_active else None
        )
        
        if current_active:
            current_active.deactivate()
            await SupabaseVersionRepository(client).update(current_active)
        
        created_version = await SupabaseVersionRepository(client).create(version)
        
        version_count = await SupabaseVersionRepository(client).count_versions(agent_id)
        await SupabaseAgentRepository(client).update_current_version(
            agent_id, created_version.version_id, version_count
        )
        return created_version
    
    async def get_version(
        self, 
        agent_id: AgentId, 
        version_id: VersionId, 
        user_id: UserId
    ) -> AgentVersion:
        is_owner, is_public = await self._verify_agent_access(agent_id, user_id)
        
        if not is_owner and not is_public:
            raise UnauthorizedError("You don't have permission to view this version")
        
        client = await self._get_client()
        version = await SupabaseVersionRepository(client).find_by_id(version_id)
        if not version or version.agent_id != agent_id:
            raise VersionNotFoundError(f"Version {version_id} not found")
        
        return version
    
    async def get_all_versions(
        self, 
        agent_id: AgentId, 
        user_id: UserId
    ) -> List[AgentVersion]:
        is_owner, is_public = await self._verify_agent_access(agent_id, user_id)
        
        if not is_owner and not is_public:
            raise UnauthorizedError("You don't have permission to view versions")
        
        client = await self._get_client()
        versions = await SupabaseVersionRepository(client).find_by_agent_id(agent_id)
        return sorted(versions, key=lambda v: v.version_number.value, reverse=True)
    
    async def activate_version(
        self,
        agent_id: AgentId,
        version_id: VersionId,
        user_id: UserId
    ) -> None:
        is_owner, is_public = await self._verify_agent_access(agent_id, user_id)
        
        if not is_owner and not is_public:
            raise UnauthorizedError("You don't have permission to activate versions")
        
        client = await self._get_client()
        version = await SupabaseVersionRepository(client).find_by_id(version_id)
        if not version or version.agent_id != agent_id:
            raise VersionNotFoundError(f"Version {version_id} not found")
        
        if version.status == VersionStatus.ARCHIVED:
            raise InvalidVersionError("Cannot activate archived version")
        
        current_active = await SupabaseVersionRepository(client).find_active_version(agent_id)
        if current_active and current_active.version_id != version_id:
            current_active.deactivate()
            await SupabaseVersionRepository(client).update(current_active)
        
        version.activate()
        await SupabaseVersionRepository(client).update(version)
        
        version_count = await SupabaseVersionRepository(client).count_versions(agent_id)
        await SupabaseAgentRepository(client).update_current_version(
            agent_id, version.version_id, version_count
        )
    
    async def compare_versions(
        self,
        agent_id: AgentId,
        version1_id: VersionId,
        version2_id: VersionId,
        user_id: UserId
    ) -> Dict[str, Any]:
        version1 = await self.get_version(agent_id, version1_id, user_id)
        version2 = await self.get_version(agent_id, version2_id, user_id)
        
        differences = self._calculate_differences(version1, version2)
        
        return {
            'version1': version1.to_dict(),
            'version2': version2.to_dict(),
            'differences': differences
        }
    
    def _calculate_differences(
        self, 
        v1: AgentVersion, 
        v2: AgentVersion
    ) -> List[Dict[str, Any]]:
        differences = []
        
        if v1.system_prompt.value != v2.system_prompt.value:
            differences.append({
                'field': 'system_prompt',
                'type': 'modified',
                'old_value': v1.system_prompt.value,
                'new_value': v2.system_prompt.value
            })
        
        v1_tools = set(v1.tool_configuration.tools.keys())
        v2_tools = set(v2.tool_configuration.tools.keys())
        
        for tool in v2_tools - v1_tools:
            differences.append({
                'field': f'tool.{tool}',
                'type': 'added',
                'new_value': v2.tool_configuration.tools[tool]
            })
        
        for tool in v1_tools - v2_tools:
            differences.append({
                'field': f'tool.{tool}',
                'type': 'removed',
                'old_value': v1.tool_configuration.tools[tool]
            })
        
        for tool in v1_tools & v2_tools:
            if v1.tool_configuration.tools[tool] != v2.tool_configuration.tools[tool]:
                differences.append({
                    'field': f'tool.{tool}',
                    'type': 'modified',
                    'old_value': v1.tool_configuration.tools[tool],
                    'new_value': v2.tool_configuration.tools[tool]
                })
        
        return differences
    
    async def rollback_to_version(
        self,
        agent_id: AgentId,
        version_id: VersionId,
        user_id: UserId
    ) -> AgentVersion:
        version_to_restore = await self.get_version(agent_id, version_id, user_id)
        
        is_owner, is_public = await self._verify_agent_access(agent_id, user_id)
        
        if not is_owner and not is_public:
            raise UnauthorizedError("You don't have permission to rollback versions")
        
        new_version = await self.create_version(
            agent_id=agent_id,
            user_id=user_id,
            system_prompt=version_to_restore.system_prompt.value,
            configured_mcps=[
                {
                    'name': mcp.name,
                    'type': mcp.type,
                    'config': mcp.config,
                    'enabledTools': mcp.enabled_tools
                }
                for mcp in version_to_restore.configured_mcps
            ],
            custom_mcps=[
                {
                    'name': mcp.name,
                    'type': mcp.type,
                    'config': mcp.config,
                    'enabledTools': mcp.enabled_tools
                }
                for mcp in version_to_restore.custom_mcps
            ],
            agentpress_tools=version_to_restore.tool_configuration.tools,
            change_description=f"Rolled back to version {version_to_restore.version_name}"
        )
        
        return new_version
    
    async def update_version_details(
        self,
        agent_id: AgentId,
        version_id: VersionId,
        user_id: UserId,
        version_name: Optional[str] = None,
        change_description: Optional[str] = None
    ) -> AgentVersion:
        is_owner, is_public = await self._verify_agent_access(agent_id, user_id)
        
        if not is_owner and not is_public:
            raise UnauthorizedError("You don't have permission to update this version")
        
        client = await self._get_client()
        version = await SupabaseVersionRepository(client).find_by_id(version_id)
        if not version or version.agent_id != agent_id:
            raise VersionNotFoundError(f"Version {version_id} not found")
        
        if version_name is not None:
            version.version_name = version_name
        if change_description is not None:
            version.change_description = change_description
        
        version.updated_at = datetime.utcnow()
        
        updated_version = await SupabaseVersionRepository(client).update(version)
        
        return updated_version 