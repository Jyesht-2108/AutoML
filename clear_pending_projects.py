#!/usr/bin/env python3
"""
Script to clear pending projects from the database
"""
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

# Initialize Supabase
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
)

# Get all pending projects
response = supabase.table("projects").select("*").eq("status", "pending_dataset").execute()

if response.data:
    print(f"Found {len(response.data)} pending projects:")
    for project in response.data:
        print(f"  - {project['name']} ({project['id']})")
    
    choice = input("\nDo you want to mark these as 'cancelled'? (yes/no): ")
    
    if choice.lower() == 'yes':
        for project in response.data:
            supabase.table("projects").update({
                "status": "cancelled"
            }).eq("id", project["id"]).execute()
            print(f"✅ Cancelled: {project['name']}")
        print("\n✅ All pending projects have been cancelled")
    else:
        print("No changes made")
else:
    print("No pending projects found")
