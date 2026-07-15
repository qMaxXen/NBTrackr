import requests
import os
import tempfile
import tarfile
import sys

GITHUB_API = "https://api.github.com/repos/qMaxXen/NBTrackr/releases/latest"

def get_latest_github_release_version():
    try:
        response = requests.get(GITHUB_API, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("tag_name")
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response is not None
            and e.response.status_code == 403
        ):
            print("[Version Check] rate limit hit, skipping update check.")
            return None
        print(f"[Version Check Error] {e}")
        return None


def check_for_update(current_version):
    latest_version = get_latest_github_release_version()
    if latest_version and latest_version != current_version:
        return latest_version
    return None


def check_and_update(current_version, script_dir):
    try:
        resp = requests.get(GITHUB_API, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        latest = data["tag_name"]
        if latest == current_version:
            return
        asset_name = f"NBTrackr-imgpin-{latest}.tar.xz"
        folder_name = asset_name.replace(".tar.xz", "")
        parent_dir = os.path.dirname(script_dir)
        folder_path = os.path.join(parent_dir, folder_name)
        if os.path.exists(folder_path):
            print(f"[Updater] Latest version ({latest}) is already downloaded.")
            print("[Updater] Please navigate to the following folder to continue:")
            print(f"    {folder_path}")
            print("[Updater] Then run the script again from the new version.")
            sys.exit(0)
        download_url = next(
            (
                a["browser_download_url"]
                for a in data["assets"]
                if a["name"] == asset_name
            ),
            None,
        )
        if not download_url:
            print(f"[Updater] Couldn't find asset {asset_name} in release {latest}.")
            return
        print(f"[Updater] Downloading {asset_name} …")
        tmpdir = tempfile.mkdtemp()
        archive_path = os.path.join(tmpdir, asset_name)
        with requests.get(download_url, stream=True, timeout=10) as dl:
            dl.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in dl.iter_content(8192):
                    f.write(chunk)
        print(f"[Updater] Extracting to {parent_dir} …")
        with tarfile.open(archive_path, "r:xz") as tar:
            tar.extractall(path=parent_dir, filter=lambda tarinfo, memberpath: tarinfo)
        os.remove(archive_path)
        body = data.get("body", "").strip()
        if body:
            print("\n[Updater] What's new:")
            print("-" * 40)
            print(body)
            print("-" * 40)
        print("\n[Updater] Update completed. New version extracted to:")
        print(f"    {folder_path}")
        print("[Updater] To finish setup, navigate to the new folder and run:")
        print("    chmod +x install.sh")
        print("    ./install.sh")
        sys.exit(0)
    except Exception as e:
        print(f"[Updater] Update failed: {e}")
