-- Create a minimal agent that satisfies the database constraint
INSERT INTO agents (
    agent_id,
    account_id,
    name,
    description,
    is_default,
    avatar,
    avatar_color,
    version_count,
    config,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    '23da2930-ab0e-402a-90e3-e75848b129a5',
    'Default Research Agent',
    'AI agent with web search capabilities',
    true,
    '🔍',
    '#4F46E5',
    1,
    '{
        "system_prompt": "You are a research assistant with access to web search tools. Use the web_search tool to find current information when users ask research questions.",
        "tools": {
            "agentpress": {
                "web_search_tool": true,
                "sb_browser_tool": true,
                "sb_shell_tool": true,
                "sb_files_tool": true
            },
            "mcp": [],
            "custom_mcp": []
        },
        "metadata": {
            "avatar": "🔍",
            "avatar_color": "#4F46E5"
        }
    }'::jsonb,
    NOW(),
    NOW()
);
