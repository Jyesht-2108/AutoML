"""
Quick script to check project status in Supabase
"""
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('mcp_server/.env')

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print("\n" + "="*60)
print("📊 CHECKING DATABASE STATUS")
print("="*60 + "\n")

# Get recent projects
print("Recent Projects:")
print("-" * 60)
projects = supabase.table("projects").select("id, name, status, created_at, updated_at").order("created_at", desc=True).limit(5).execute()

for p in projects.data:
    status_emoji = {
        'draft': '📝',
        'pending_dataset': '⏳',
        'pending_training': '🔄',
        'pending_evaluation': '📊',
        'completed': '✅',
        'failed': '❌'
    }.get(p['status'], '❓')
    
    print(f"{status_emoji} {p['name'][:40]}")
    print(f"   ID: {p['id']}")
    print(f"   Status: {p['status']}")
    print(f"   Created: {p['created_at']}")
    print(f"   Updated: {p['updated_at']}")
    print()

# Get recent datasets
print("\nRecent Datasets:")
print("-" * 60)
datasets = supabase.table("datasets").select("project_id, name, size, created_at").order("created_at", desc=True).limit(5).execute()

for d in datasets.data:
    print(f"📦 {d['name']}")
    print(f"   Project ID: {d['project_id']}")
    print(f"   Size: {d['size']}")
    print(f"   Created: {d['created_at']}")
    print()

# Get recent agent logs
print("\nRecent Agent Logs:")
print("-" * 60)
logs = supabase.table("agent_logs").select("agent_name, message, log_level, created_at").order("created_at", desc=True).limit(10).execute()

for log in logs.data:
    level_emoji = {
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '❌',
        'success': '✅'
    }.get(log['log_level'], '📝')
    
    print(f"{level_emoji} [{log['agent_name']}] {log['message'][:60]}")
    print(f"   Time: {log['created_at']}")
    print()

print("="*60)
print("✅ Check complete!")
print("="*60)
