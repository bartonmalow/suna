import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from uuid import uuid4

from services.supabase import DBConnection
from utils.logger import logger

ConfigType = Dict[str, Any]
ProfileId = str
QualifiedName = str

@dataclass(frozen=True)
class MCPRequirementValue:
    qualified_name: str
    display_name: str
    enabled_tools: List[str] = field(default_factory=list)
    required_config: List[str] = field(default_factory=list)
    custom_type: Optional[str] = None
    
    def is_custom(self) -> bool:
        if self.qualified_name.startswith('pipedream:'):
            return False
        return self.custom_type is not None and self.qualified_name.startswith('custom_')

@dataclass(frozen=True)
class AgentTemplate:
    template_id: str
    creator_id: str
    name: str
    config: ConfigType
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    is_public: bool = False
    marketplace_published_at: Optional[datetime] = None
    download_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    avatar: Optional[str] = None
    avatar_color: Optional[str] = None
    metadata: ConfigType = field(default_factory=dict)
    
    def with_public_status(self, is_public: bool, published_at: Optional[datetime] = None) -> 'AgentTemplate':
        return AgentTemplate(
            **{**self.__dict__, 
               'is_public': is_public, 
               'marketplace_published_at': published_at}
        )
    
    @property
    def system_prompt(self) -> str:
        return self.config.get('system_prompt', '')
    
    @property
    def agentpress_tools(self) -> Dict[str, Any]:
        return self.config.get('tools', {}).get('agentpress', {})
    
    @property
    def mcp_requirements(self) -> List[MCPRequirementValue]:
        requirements = []
        
        mcps = self.config.get('tools', {}).get('mcp', [])
        for mcp in mcps:
            if isinstance(mcp, dict) and mcp.get('name'):
                qualified_name = mcp.get('qualifiedName', mcp['name'])
                
                requirements.append(MCPRequirementValue(
                    qualified_name=qualified_name,
                    display_name=mcp.get('display_name') or mcp['name'],
                    enabled_tools=mcp.get('enabledTools', []),
                    required_config=mcp.get('requiredConfig', [])
                ))
        
        custom_mcps = self.config.get('tools', {}).get('custom_mcp', [])
        for mcp in custom_mcps:
            if isinstance(mcp, dict) and mcp.get('name'):
                mcp_type = mcp.get('type', 'sse')
                mcp_name = mcp['name']
                
                if mcp_type == 'pipedream':
                    app_slug = mcp.get('config', {}).get('headers', {}).get('x-pd-app-slug')
                    if not app_slug:
                        app_slug = mcp_name.lower().replace(' ', '').replace('(', '').replace(')', '')
                    qualified_name = f"pipedream:{app_slug}"
                    required_config = []
                else:
                    safe_name = mcp_name.replace(' ', '_').lower()
                    qualified_name = f"custom_{mcp_type}_{safe_name}"
                    
                    if mcp_type in ['http', 'sse', 'json']:
                        required_config = ['url']
                    else:
                        required_config = mcp.get('requiredConfig', ['url'])
                
                requirements.append(MCPRequirementValue(
                    qualified_name=qualified_name,
                    display_name=mcp.get('display_name') or mcp_name,
                    enabled_tools=mcp.get('enabledTools', []),
                    required_config=required_config,
                    custom_type=mcp_type
                ))
        
        return requirements

@dataclass
class TemplateCreationRequest:
    agent_id: str
    creator_id: str
    make_public: bool = False
    tags: Optional[List[str]] = None

class TemplateNotFoundError(Exception):
    pass

class TemplateAccessDeniedError(Exception):
    pass

class SunaDefaultAgentTemplateError(Exception):
    pass

class TemplateService:
    def __init__(self, db_connection: DBConnection):
        self._db = db_connection
    
    async def create_from_agent(
        self,
        agent_id: str,
        creator_id: str,
        make_public: bool = False,
        tags: Optional[List[str]] = None
    ) -> str:
        logger.info(f"Creating template from agent {agent_id} for user {creator_id}")
        
        agent = await self._get_agent_by_id(agent_id)
        if not agent:
            raise TemplateNotFoundError("Agent not found")
        
        if agent['account_id'] != creator_id:
            raise TemplateAccessDeniedError("You can only create templates from your own agents")
        
        if self._is_suna_default_agent(agent):
            raise SunaDefaultAgentTemplateError("Cannot create template from Suna default agent")
        
        version_config = await self._get_agent_version_config(agent)
        if not version_config:
            raise TemplateNotFoundError("Agent has no version configuration")
        
        sanitized_config = await self._sanitize_config_for_template(version_config)
        
        template = AgentTemplate(
            template_id=str(uuid4()),
            creator_id=creator_id,
            name=agent['name'],
            description=agent.get('description'),
            config=sanitized_config,
            tags=tags or [],
            is_public=make_public,
            marketplace_published_at=datetime.now(timezone.utc) if make_public else None,
            avatar=agent.get('avatar'),
            avatar_color=agent.get('avatar_color'),
            metadata=agent.get('metadata', {})
        )
        
        await self._save_template(template)
        
        logger.info(f"Created template {template.template_id} from agent {agent_id}")
        return template.template_id
    
    async def get_template(self, template_id: str) -> Optional[AgentTemplate]:
        client = await self._db.client
        result = await client.table('agent_templates').select('*')\
            .eq('template_id', template_id)\
            .maybe_single()\
            .execute()
        
        if not result.data:
            return None
        
        return self._map_to_template(result.data)
    
    async def get_user_templates(self, creator_id: str) -> List[AgentTemplate]:
        client = await self._db.client
        result = await client.table('agent_templates').select('*')\
            .eq('creator_id', creator_id)\
            .order('created_at', desc=True)\
            .execute()
        
        return [self._map_to_template(data) for data in result.data]
    
    async def get_public_templates(self) -> List[AgentTemplate]:
        client = await self._db.client
        result = await client.table('agent_templates').select('*')\
            .eq('is_public', True)\
            .order('download_count', desc=True)\
            .order('marketplace_published_at', desc=True)\
            .execute()
        
        return [self._map_to_template(data) for data in result.data]
    
    async def publish_template(self, template_id: str, creator_id: str) -> bool:
        logger.info(f"Publishing template {template_id}")
        
        client = await self._db.client
        result = await client.table('agent_templates').update({
            'is_public': True,
            'marketplace_published_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('template_id', template_id)\
          .eq('creator_id', creator_id)\
          .execute()
        
        success = len(result.data) > 0
        if success:
            logger.info(f"Published template {template_id}")
        
        return success
    
    async def unpublish_template(self, template_id: str, creator_id: str) -> bool:
        logger.info(f"Unpublishing template {template_id}")
        
        client = await self._db.client
        result = await client.table('agent_templates').update({
            'is_public': False,
            'marketplace_published_at': None,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('template_id', template_id)\
          .eq('creator_id', creator_id)\
          .execute()
        
        success = len(result.data) > 0
        if success:
            logger.info(f"Unpublished template {template_id}")
        
        return success
    
    async def increment_download_count(self, template_id: str) -> None:
        client = await self._db.client
        await client.rpc('increment_template_download_count', {
            'template_id_param': template_id
        }).execute()
    
    async def validate_access(self, template: AgentTemplate, user_id: str) -> None:
        if template.creator_id != user_id and not template.is_public:
            raise TemplateAccessDeniedError("Access denied to template")
    
    async def _get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        client = await self._db.client
        result = await client.table('agents').select('*')\
            .eq('agent_id', agent_id)\
            .maybe_single()\
            .execute()
        
        return result.data
    
    async def _get_agent_version_config(self, agent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        version_id = agent.get('current_version_id')
        if version_id:
            client = await self._db.client
            result = await client.table('agent_versions').select('config')\
                .eq('version_id', version_id)\
                .maybe_single()\
                .execute()
            
            if result.data and result.data['config']:
                return result.data['config']
        
        return {}
    
    async def _sanitize_config_for_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
        client = await self._db.client
        result = await client.rpc('sanitize_config_for_template', {
            'input_config': config
        }).execute()
        
        if result.data:
            return result.data
        
        return self._fallback_sanitize_config(config)
    
    def _fallback_sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {
            'system_prompt': config.get('system_prompt', ''),
            'tools': {
                'agentpress': config.get('tools', {}).get('agentpress', {}),
                'mcp': config.get('tools', {}).get('mcp', []),
                'custom_mcp': []
            },
            'metadata': {
                'avatar': config.get('metadata', {}).get('avatar'),
                'avatar_color': config.get('metadata', {}).get('avatar_color')
            }
        }
        
        custom_mcps = config.get('tools', {}).get('custom_mcp', [])
        for mcp in custom_mcps:
            if isinstance(mcp, dict):
                sanitized_mcp = {
                    'name': mcp.get('name'),
                    'type': mcp.get('type'),
                    'display_name': mcp.get('display_name') or mcp.get('name'),
                    'enabledTools': mcp.get('enabledTools', [])
                }
                
                if mcp.get('type') == 'pipedream':
                    original_config = mcp.get('config', {})
                    sanitized_mcp['config'] = {
                        'url': original_config.get('url'),
                        'headers': {k: v for k, v in original_config.get('headers', {}).items() 
                                  if k != 'profile_id'}
                    }
                else:
                    sanitized_mcp['config'] = {}
                
                sanitized['tools']['custom_mcp'].append(sanitized_mcp)
        
        return sanitized
    
    def _is_suna_default_agent(self, agent: Dict[str, Any]) -> bool:
        metadata = agent.get('metadata', {})
        return metadata.get('is_suna_default', False)
    
    async def _save_template(self, template: AgentTemplate) -> None:
        client = await self._db.client
        
        template_data = {
            'template_id': template.template_id,
            'creator_id': template.creator_id,
            'name': template.name,
            'description': template.description,
            'config': template.config,
            'tags': template.tags,
            'is_public': template.is_public,
            'marketplace_published_at': template.marketplace_published_at.isoformat() if template.marketplace_published_at else None,
            'download_count': template.download_count,
            'created_at': template.created_at.isoformat(),
            'updated_at': template.updated_at.isoformat(),
            'avatar': template.avatar,
            'avatar_color': template.avatar_color,
            'metadata': template.metadata
        }
        
        await client.table('agent_templates').insert(template_data).execute()
    
    def _map_to_template(self, data: Dict[str, Any]) -> AgentTemplate:
        return AgentTemplate(
            template_id=data['template_id'],
            creator_id=data['creator_id'],
            name=data['name'],
            description=data.get('description'),
            config=data.get('config', {}),
            tags=data.get('tags', []),
            is_public=data.get('is_public', False),
            marketplace_published_at=datetime.fromisoformat(data['marketplace_published_at'].replace('Z', '+00:00')) if data.get('marketplace_published_at') else None,
            download_count=data.get('download_count', 0),
            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00')),
            avatar=data.get('avatar'),
            avatar_color=data.get('avatar_color'),
            metadata=data.get('metadata', {})
        )

def get_template_service(db_connection: DBConnection) -> TemplateService:
    return TemplateService(db_connection) 