import os
import zipfile
import tempfile
from supabase import create_client
from google.cloud import storage
from dotenv import load_dotenv

load_dotenv('/Users/prince/Downloads/AutoML MP/mcp_server/.env')
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
storage_client = storage.Client.from_service_account_json(os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))

models = supabase.table('models').select('id, project_id, metadata').execute()

for m in models.data:
    meta = m.get('metadata') or {}
    if 'class_labels' not in meta or not meta['class_labels']:
        print(f"Fixing model {m['id']} for project {m['project_id']}...")
        
        # Get dataset URL
        dataset = supabase.table('datasets').select('gcs_url').eq('project_id', m['project_id']).execute()
        if not dataset.data:
            print("  No dataset found.")
            continue
            
        gcs_url = dataset.data[0]['gcs_url']
        if not gcs_url:
            continue
            
        print(f"  Downloading dataset zip: {gcs_url}")
        bucket_name = gcs_url.replace("gs://", "").split("/")[0]
        blob_path = "/".join(gcs_url.replace("gs://", "").split("/")[1:])
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        with tempfile.NamedTemporaryFile(suffix='.zip') as temp_zip:
            blob.download_to_filename(temp_zip.name)
            
            # Read zip structure
            try:
                with zipfile.ZipFile(temp_zip.name, 'r') as z:
                    # Look for folders in train/ or dataset-name/train/
                    paths = z.namelist()
                    
                    # Find the train directory prefix
                    train_prefix = None
                    for p in paths:
                        if '/train/' in p.lower() or p.lower().startswith('train/'):
                            train_prefix = p[:p.lower().find('train/') + 6]
                            break
                    
                    if not train_prefix:
                        print("  Could not find train/ directory in zip.")
                        continue
                        
                    # Extract class names
                    classes = set()
                    for p in paths:
                        if p.startswith(train_prefix) and p != train_prefix:
                            rel_path = p[len(train_prefix):]
                            if '/' in rel_path:
                                cls_name = rel_path.split('/')[0]
                                if cls_name:
                                    classes.add(cls_name)
                                    
                    class_labels = sorted(list(classes))
                    print(f"  Found {len(class_labels)} classes: {class_labels[:5]}...")
                    
                    # Update DB
                    meta['class_labels'] = class_labels
                    supabase.table('models').update({'metadata': meta}).eq('id', m['id']).execute()
                    print("  Updated database!")
            except Exception as e:
                print(f"  Error reading zip: {e}")

