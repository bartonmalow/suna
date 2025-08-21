-- Create a simple agent with web_search tools for the test user
-- Updated for new config-based schema
INSERT INTO agents (
    agent_id,
    account_id,
    name,
    description,
    is_default,
    is_public,
    avatar,
    avatar_color,
    created_at,
    updated_at,
    version_count,
    config
) VALUES (
    gen_random_uuid(),
    '23da2930-ab0e-402a-90e3-e75848b129a5',
    'Research Agent',
    'AI agent with web search capabilities for comprehensive research',
    true,
    false,
    '🔍',
    '#4F46E5',
    NOW(),
    NOW(),
    1,
    '{
        "system_prompt": "You are a research assistant with access to web search tools. Use the web_search tool to find current information when users ask research questions.",
        "tools": {
            "agentpress": {"web_search_tool": true, "sb_browser_tool": true, "sb_shell_tool": true},
            "mcp": [],
            "custom_mcp": []
        },
        "metadata": {
            "avatar": "🔍",
            "avatar_color": "#4F46E5"
        }
    }'::jsonb
) ON CONFLICT (account_id, is_default) WHERE is_default = true DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    config = EXCLUDED.config,
    avatar = EXCLUDED.avatar,
    avatar_color = EXCLUDED.avatar_color,
    updated_at = NOW();
