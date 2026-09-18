import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('/Users/prince/Downloads/AutoML MP/mcp_server/.env')
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

response = supabase.table('models').select('id, name, project_id, metadata').execute()
for m in response.data:
    meta = m.get('metadata') or {}
    print(f"Model: {m['name']} (Project: {m['project_id']})")
    print(f"  Architecture: {meta.get('architecture')}")
    print(f"  Classes: {meta.get('num_classes')}")
    print(f"  Labels in metadata: {'Yes' if 'class_labels' in meta else 'No'}")
