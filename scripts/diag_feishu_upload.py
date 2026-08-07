"""Diagnose Feishu upload permissions. Reads creds from env, prints each step.

Tests two upload paths so we can tell whether the 1061004 is a scope gap
(read-only drive permission) or a parent_type mismatch.
"""

import os
import sys

import requests

sys.path.insert(0, os.getcwd())

from tools.feishu_office_tool import _build_client_from_env, _get_tenant_access_token


def main():
    client = _build_client_from_env()
    token = _get_tenant_access_token(client)
    print("tenant token prefix:", token[:20], "...")
    domain = client.config.domain.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. root folder meta (proves read scope works)
    r = requests.get(f"{domain}/open-apis/drive/explorer/v2/root_folder/meta", headers=headers, timeout=30)
    print("\n[root_folder/meta] status:", r.status_code)
    print("[root_folder/meta] body:", r.text[:400])
    if r.status_code != 200:
        return
    root_token = r.json().get("data", {}).get("token")
    print("root folder token:", root_token)

    file_path = "apps/desktop/.sample-office/sample.docx"
    with open(file_path, "rb") as f:
        file_content = f.read()
    file_name = os.path.basename(file_path)

    # 2. upload with parent_type=explorer + root folder (standard write path)
    form_a = {
        "file_name": file_name,
        "parent_type": "explorer",
        "parent_node": root_token,
        "size": str(len(file_content)),
    }
    r2 = requests.post(
        f"{domain}/open-apis/drive/v1/files/upload_all",
        headers=headers,
        data=form_a,
        files={"file": (file_name, file_content)},
        timeout=30,
    )
    print("\n[upload_all parent_type=explorer] status:", r2.status_code)
    print("[upload_all parent_type=explorer] body:", r2.text[:500])

    # 3. upload with parent_type=ccm_import_open (import staging, no parent_node)
    form_b = {
        "file_name": file_name,
        "parent_type": "ccm_import_open",
        "size": str(len(file_content)),
    }
    r3 = requests.post(
        f"{domain}/open-apis/drive/v1/files/upload_all",
        headers=headers,
        data=form_b,
        files={"file": (file_name, file_content)},
        timeout=30,
    )
    print("\n[upload_all parent_type=ccm_import_open] status:", r3.status_code)
    print("[upload_all parent_type=ccm_import_open] body:", r3.text[:500])

    # 4. verdict
    print("\n=== VERDICT ===")
    if r2.status_code == 403 and r3.status_code == 403:
        print("Both upload paths return 403. The app has a READ-ONLY drive scope.")
        print("Fix: grant 'drive:drive' (read+write) in Permissions, then publish a new version.")


if __name__ == "__main__":
    main()
