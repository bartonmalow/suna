const { createClient } = require('@supabase/supabase-js')

const supabaseUrl = 'https://rabdclxfdfxwpwibcuuj.supabase.co'
const serviceKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJhYmRjbHhmZGZ4d3B3aWJjdXVqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MzczNTk1NSwiZXhwIjoyMDY5MzExOTU1fQ.DZbm39Whc7MMhO7VjN-8V1JPEmda52TnG7-CDR4DcVk'

async function createAgent() {
    const supabase = createClient(supabaseUrl, serviceKey)
    
    const userId = '23da2930-ab0e-402a-90e3-e75848b129a5'
    
    // First, check if user already has a default agent
    const { data: existingAgents } = await supabase
        .from('agents')
        .select('*')
        .eq('account_id', userId)
        .eq('is_default', true)
    
    if (existingAgents && existingAgents.length > 0) {
        console.log('✅ User already has a default agent:', existingAgents[0].agent_id)
        return existingAgents[0].agent_id
    }
    
    // Create agent with minimal required fields
    const agentData = {
        account_id: userId,
        name: 'Research Agent',
        description: 'AI agent with web search capabilities',
        system_prompt: 'You are a research assistant with access to web search tools. Use the web_search tool to find current information.',
        agentpress_tools: JSON.stringify({
            "web_search_tool": true,
            "sb_browser_tool": true,
            "sb_shell_tool": true
        }),
        configured_mcps: JSON.stringify([]),
        custom_mcps: JSON.stringify([]),
        is_default: true,
        is_public: false,
        avatar: '🔍',
        avatar_color: '#4F46E5',
        version_count: 1
    }
    
    console.log('Creating agent with data:', JSON.stringify(agentData, null, 2))
    
    const { data, error } = await supabase
        .from('agents')
        .insert(agentData)
        .select()
    
    if (error) {
        console.error('❌ Error creating agent:', error)
        return null
    }
    
    console.log('✅ Agent created successfully:', data[0].agent_id)
    return data[0].agent_id
}

createAgent().catch(console.error)
