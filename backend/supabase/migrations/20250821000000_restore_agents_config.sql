-- Restore Agents Config Structure Migration
-- This migration restores the config column and constraint that was accidentally dropped
-- by the 20250729094718_cleanup_agents_table.sql migration

BEGIN;

-- Re-add the config column to agents table
ALTER TABLE agents ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}'::jsonb;

-- Re-add the config column to agent_versions table
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}'::jsonb;

-- Ensure config is never null
ALTER TABLE agents ALTER COLUMN config SET NOT NULL;
ALTER TABLE agents ALTER COLUMN config SET DEFAULT '{}'::jsonb;

ALTER TABLE agent_versions ALTER COLUMN config SET NOT NULL;
ALTER TABLE agent_versions ALTER COLUMN config SET DEFAULT '{}'::jsonb;

-- Re-add the constraint to ensure config has basic structure
-- Drop existing constraints first to avoid conflicts
ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_config_structure_check;
ALTER TABLE agent_versions DROP CONSTRAINT IF EXISTS agent_versions_config_structure_check;

-- Add the constraints
ALTER TABLE agents ADD CONSTRAINT agents_config_structure_check 
CHECK (
    config ? 'system_prompt' AND 
    config ? 'tools' AND 
    config ? 'metadata'
);

ALTER TABLE agent_versions ADD CONSTRAINT agent_versions_config_structure_check 
CHECK (
    config ? 'system_prompt' AND 
    config ? 'tools'
);

-- Re-create the indexes for efficient config queries
CREATE INDEX IF NOT EXISTS idx_agents_config_system_prompt ON agents USING gin((config->>'system_prompt') gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_agents_config_tools ON agents USING gin((config->'tools'));
CREATE INDEX IF NOT EXISTS idx_agent_versions_config_system_prompt ON agent_versions USING gin((config->>'system_prompt') gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_agent_versions_config_tools ON agent_versions USING gin((config->'tools'));

-- Update existing agents to have proper config structure if they don't already have it
UPDATE agents 
SET config = jsonb_build_object(
    'system_prompt', COALESCE(config->>'system_prompt', ''),
    'tools', COALESCE(
        config->'tools',
        jsonb_build_object(
            'agentpress', '{}'::jsonb,
            'mcp', '[]'::jsonb,
            'custom_mcp', '[]'::jsonb
        )
    ),
    'metadata', COALESCE(
        config->'metadata',
        jsonb_build_object(
            'avatar', avatar,
            'avatar_color', avatar_color
        )
    )
)
WHERE config = '{}'::jsonb OR config IS NULL OR NOT (config ? 'system_prompt' AND config ? 'tools' AND config ? 'metadata');

-- Update existing agent_versions to have proper config structure if they don't already have it
UPDATE agent_versions 
SET config = jsonb_build_object(
    'system_prompt', COALESCE(config->>'system_prompt', ''),
    'tools', COALESCE(
        config->'tools',
        jsonb_build_object(
            'agentpress', '{}'::jsonb,
            'mcp', '[]'::jsonb,
            'custom_mcp', '[]'::jsonb
        )
    )
)
WHERE config = '{}'::jsonb OR config IS NULL OR NOT (config ? 'system_prompt' AND config ? 'tools');

-- Add helpful comments
COMMENT ON COLUMN agents.config IS 'Single source of truth for all agent configuration including system_prompt, tools, and metadata';
COMMENT ON COLUMN agent_versions.config IS 'Single source of truth for versioned agent configuration';

COMMIT;
