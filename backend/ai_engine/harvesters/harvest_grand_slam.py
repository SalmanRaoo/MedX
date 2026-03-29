import os
import shutil
import subprocess
import stat
import time

# THE 4 TARGET REPOSITORIES
REPOS = {
    "samagra": "https://github.com/samagra44/Multiple-Disease-Prediction-System.git",
    "karan": "https://github.com/Karanmehra7107/Medical_Diagnosis.git",
    "eda": "https://github.com/edaaydinea/AI-Projects-for-Healthcare.git",
    "venugopal": "https://github.com/venugopalkadamba/Multi_Disease_Predictor.git"
}

# CONFIG
BASE_DIR = "hospital_ai_assets"
DATA_DIR = os.path.join(BASE_DIR, "harvested_data")

# --- WINDOWS PERMISSION FIX ---
# This function forces Windows to allow deletion of read-only .git files
def handle_remove_readonly(func, path, exc):
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink):
        os.chmod(path, stat.S_IWRITE)
        try:
            func(path)
        except Exception:
            pass 
    else:
        raise

def harvest():
    print("🚜 STARTING SMARTER GRAND-SLAM HARVEST...")
    
    # 1. Clean Slate (Force Delete Old Data)
    if os.path.exists(DATA_DIR): 
        shutil.rmtree(DATA_DIR, onerror=handle_remove_readonly)
    os.makedirs(DATA_DIR, exist_ok=True)

    total_files = 0

    for name, url in REPOS.items():
        print(f"\n⬇️  Cloning {name.upper()}...")
        temp_dir = f"temp_{name}"
        
        # Cleanup leftover temp folders from crashed runs
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
        
        try:
            # Clone (Quietly)
            subprocess.run(["git", "clone", url, temp_dir], check=True, stdout=subprocess.DEVNULL)
            
            # Extract CSVs
            repo_count = 0
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith(".csv"):
                        # SMART RENAMING FIX: 
                        # Grab the parent folder to identify the disease (e.g. "Parkinsons")
                        parent_folder = os.path.basename(root).lower().replace(" ", "_")
                        clean_filename = file.lower().replace(" ", "_")
                        
                        # New Name: repo_folder_filename.csv
                        # Example: samagra_parkinsons_data.csv
                        new_name = f"{name}_{parent_folder}_{clean_filename}"
                        
                        src = os.path.join(root, file)
                        dst = os.path.join(DATA_DIR, new_name)
                        
                        try:
                            shutil.copy(src, dst)
                            repo_count += 1
                        except PermissionError:
                            print(f"      ⚠️ Skipped locked file: {file}")
                        
            print(f"   ✅ Extracted {repo_count} datasets.")
            total_files += repo_count
            
        except Exception as e:
            print(f"   ❌ Failed to process {name}: {e}")
        finally:
            # Force Delete Temp Folder
            if os.path.exists(temp_dir):
                time.sleep(1) # Wait for Windows to release file locks
                shutil.rmtree(temp_dir, onerror=handle_remove_readonly)

    print("\n" + "="*50)
    print(f"🎉 HARVEST COMPLETE! Found {total_files} potential datasets.")
    print(f"📂 Location: {DATA_DIR}")
    print("="*50)

if __name__ == "__main__":
    harvest()