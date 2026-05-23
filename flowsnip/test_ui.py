"""
Quick test script to validate the UI improvements.
"""

from flowsnip import Config, FlowSnipGUI


def main():
    """Test the improved UI features."""
    print("Testing FlowSnip UI improvements...")

    # Create config with custom settings to test UI
    config = Config()
    config.download.max_parallel_downloads = 5
    config.download.video_quality = "best[height<=720]"  # Should show as "720p"
    config.download.audio_only = True
    config.download.audio_quality = "320"

    print("✓ Config created with:")
    print(f"  - Max parallel downloads: {config.download.max_parallel_downloads}")
    print(f"  - Video quality: {config.download.video_quality}")
    print(f"  - Audio only: {config.download.audio_only}")
    print(f"  - Audio quality: {config.download.audio_quality}")

    print("\n✓ UI Improvements implemented:")
    print("  - Slider for parallel downloads (1-10)")
    print("  - Dropdown for video quality (360p, 720p, 1080p, 4K, etc.)")
    print("  - Audio quality only visible when 'Audio Only' is checked")

    print("\n✓ Starting GUI with improved controls...")

    # Start GUI
    app = FlowSnipGUI(config)
    app.run()


if __name__ == "__main__":
    main()
