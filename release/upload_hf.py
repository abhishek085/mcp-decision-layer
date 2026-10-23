"""Upload the model (GGUF) and the two datasets to Hugging Face. Token is read from the HF_TOKEN environment variable only. Refuses to touch an existing repo."""
import os, sys
from huggingface_hub import HfApi
api = HfApi(token=os.environ["HF_TOKEN"]); me = api.whoami()["name"]; assert me == "abhishek085", me
jobs = [("dataset", "abhishek085/spark-s1-mcp-router-train", "release/datasets/spark-s1-mcp-router-train"),
        ("dataset", "abhishek085/mcp-decision-layer-bench", "release/datasets/mcp-decision-layer-bench"),
        ("model", "abhishek085/spark-s1-mcp-router-4b-r1", "release/hf_model_stage")]
for kind, rid, folder in jobs:
    if api.repo_exists(rid, repo_type=kind):
        files = [f for f in api.list_repo_files(rid, repo_type=kind) if f != ".gitattributes"]
        if files:
            print("EXISTS with content - skipping (not touching):", rid, files[:5], flush=True); continue
        print("exists but EMPTY (created by an earlier attempt of this script) - filling:", rid, flush=True)
    else:
        api.create_repo(rid, repo_type=kind, private=False)
        print("created", kind, rid, flush=True)
    api.upload_folder(folder_path=folder, repo_id=rid, repo_type=kind, commit_message="Initial upload")
    print("uploaded", rid, "from", folder, flush=True)
print("ALL DONE", flush=True)
