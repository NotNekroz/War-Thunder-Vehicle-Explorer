import io
import urllib.error
import urllib.request
from PIL import Image


def fetch_and_show_vehicle_image(vehicle_id: str) -> bool:
    clean_id = vehicle_id.strip().lower()

    # Candidate ID formats to check on the CDN
    candidates = [
        clean_id,
        clean_id.replace("_", "-"),
        clean_id.replace("-", "_"),
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    }

    for cand in candidates:
        url = f"https://static.encyclopedia.warthunder.com/images/{cand}.png"
        print(f"Testing URL: {url}")

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    image_bytes = response.read()
                    img = Image.open(io.BytesIO(image_bytes))

                    print(
                        f"\n[Success] Found image for '{cand}'"
                        f" ({img.size[0]}x{img.size[1]}px)!"
                    )
                    img.show()  # Opens image in default OS Viewer
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            print(f"[Error] HTTP {e.code} when accessing {url}")
        except Exception as e:
            print(f"[Error] Connection failed: {e}")

    print(f"\n[Failed] No image found on CDN for Vehicle ID '{vehicle_id}'.")
    return False


if __name__ == "__main__":
    print("=== War Thunder CDN Vehicle Image Tester ===\n")
    while True:
        v_id = input(
            "Enter Vehicle ID (e.g., 'rafale_c_f3', 'ef_2000_block_10') or 'q'"
            " to quit: "
        ).strip()
        if not v_id or v_id.lower() == "q":
            break
        fetch_and_show_vehicle_image(v_id)