# OBS Indicator 🎥

**NVIDIA ShadowPlay-style indicators - now for OBS!** Clean, customizable icons and effects that show you when you're recording, paused, or saving a replay. Never second-guess if you're capturing again.

> Made for OBS users who miss the simple status indicators from ShadowPlay.

<p align="center">
  <img src="https://img.shields.io/badge/OBS Studio-28+-brightgreen?logo=obs-studio" alt="OBS Version">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python" alt="Python Version">
</p>

## ❤️ Key Features

- **Feels like ShadowPlay**: Familiar, intuitive icons for recording and replay saving.
- **Always on Top**: Stays visible over your games.
- **Flash on Save**: Get a visual confirmation with a screen flash when you save a replay.
- **Customizable Borders**: Add optional borders around your screen that change color to indicate recording, pause, or replay buffer status.
- **Save Sound**: Play a custom sound when a replay is saved, with adjustable volume.
- **Lightweight & Simple**: Minimal system impact and a clear, step-by-step setup guide.

> [!WARNING]  
> The functionality to display over **exclusive full-screen** applications is not implemented **and will not be implemented**. It requires deep knowledge in DirectX hooking, as well as certifcation (so that anti-cheat systems do not perceive indicators as cheats).
> 
> Indicators can be added to OBS **officially**  if you [**vote here**](https://ideas.obsproject.com/posts/2454/obs-visual-rec-pause-stop-indicator).
> 
> Use **windowed full-screen mode**.

## ⚙️ Installation & Setup

Just follow these 3 steps to get up and running.

### Step 1: Download the Script
1.  Go to the [**Releases Page**](https://github.com/ineedmypills/OBS-Indicator/releases).
2.  Download the latest version of the `OBSIndicator.py` file and any associated assets (like `Saved.wav`).

### Step 2: Install Python for OBS
1.  **Download the dedicated Python build:** Head over to the [**OBS-Python repository**](https://github.com/ineedmypills/OBS-Python).
2.  Follow the installation instructions provided on that page. This build includes all necessary dependencies.

### Step 3: Add the Script to OBS
1.  Go back to the **Tools → Scripts** window in OBS.
2.  In the **Scripts** tab, click the `+` (Add Script) icon in the bottom left.
3.  Select the `OBSIndicator.py` file you downloaded earlier.

That's it! The script is now installed and ready to go.

## 🎨 Customization

You can customize every aspect of the indicators directly within the OBS script settings.

1.  Go to **Tools → Scripts**.
2.  Select `OBS Indicator` from the list of loaded scripts.
3.  A panel with customization options will appear on the right.

### General Settings
-   **Screen Position**: Choose which corner of the screen to display the icon in.
-   **Padding**: Fine-tune the icon's exact position with pixel offsets.
-   **Opacity**: Make the icon more or less transparent.

### Effects & Animations
-   **Flash on Save**: Enable a screen flash when a replay is saved.
    -   **Flash Color**: Set the color of the flash.
    -   **Flash Duration**: Control how long the flash effect lasts.
    -   The flash has a built-in "ease-out" animation for a smooth fade.

### Recording Indicator
-   **Enable Recording Border**: A persistent border that appears while recording.
    -   **Recording Color**: The color of the border during normal recording.
    -   **Paused Color**: The color the border changes to when recording is paused.
-   **Enable Pause Border (if main is off)**: A temporary, animated border that smoothly appears only when you pause recording (and the main border is disabled).

### Replay Buffer Indicator
-   **Enable Replay Buffer Border**: A persistent border that shows when the replay buffer is active.
    -   **Active Color**: The color of the border when the buffer is on.
    -   **Saved Color**: The color the border briefly changes to when a replay is saved.
-   **Enable Save Border (if main is off)**: A temporary, animated border that appears briefly when you save a replay (and the main buffer border is disabled).
-   **Save Sound Path**: Set a path to a custom sound file to play on save.
    -   Defaults to `Saved.wav` in the same folder as the script.
-   **Save Sound Volume**: Adjust the volume of the save sound from 0% to 200%.

> [!IMPORTANT] 
> If the indicator disappears after you change its settings, you'll need to restart OBS Studio for the changes to take effect.

## ❓ Help and Support

If you encounter any issues, have questions, or wish to contribute to the development of OBS Indicator, here's how you can get help or assist the project:

### Reporting Issues

If you come across a bug, unusual behavior, or have a suggestion for improvement, please create an **Issue** on the project's GitHub page.

1.  Go to the project's [Issues page](https://github.com/ineedmypills/OBS-Indicator/issues).
2.  Click the **"New issue"** button.
3.  Describe your problem in as much detail as possible:
    * Provide steps to reproduce the error.
    * Attach screenshots or videos if they are helpful.
    * Specify the OBS Studio and Python versions you are using.

### Pull Requests

All improvements and fixes are welcome! If you have programming skills and wish to contribute:

1.  **Fork** the repository.
2.  Create a new branch for your changes.
3.  Implement your changes in the code.
4.  Submit a **Pull Request** to the main repository. Please ensure your code adheres to the existing project style and is well-documented.

### General Inquiries

For general questions or discussions that aren't bug reports or pull requests, you can also use the [Issues section](https://github.com/ineedmypills/OBS-Indicator/issues) or reach out to the OBS community on relevant forums.
