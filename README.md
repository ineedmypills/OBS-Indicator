# OBS Indicator 🎥

**NVIDIA ShadowPlay-style indicators - now for OBS!** Clean, customizable icons that show you when you're recording or saving a replay. Never second-guess if you're capturing again.

> Made for OBS users who miss the simple status indicators from ShadowPlay.

<p align="center">
  <img src="https://img.shields.io/badge/OBS Studio-28+-brightgreen?logo=obs-studio" alt="OBS Version">
  <img src="https://img.shields.io/badge/Python-3.6+-blue?logo=python" alt="Python Version">
</p>

## ❤️ Key Features

- **Feels like ShadowPlay**: Familiar, intuitive icons for recording and replay saving.
- **Always on Top**: Stays visible over your games ~~and full-screen applications~~.
- **Simple Setup**: A clear, step-by-step guide to get you started in minutes.
- **Lightweight**: Minimal system impact. It won't slow down your stream or recording.
- **Fully Customizable**: Adjust the position, style, and opacity to match your preference.
> [!WARNING]  
> This script **CANNOT** display indicators in **exclusive full-screen applications**, *but this may be fixed in the future*...
> 
> It is *almost* impossible to implement this feature in a simple Python script....
> 
> Use **windowed full-screen mode**!
## ⚙️ Installation & Setup

Just follow these 3 steps to get up and running.

### Step 1: Download the Script

1.  Go to the [**Releases Page**](https://github.com/ineedmypills/OBS-Indicator/releases).
2.  Download the latest version of the `OBSIndicator.py` file.

### Step 2: Install the Dependency (PyQt5)

The script uses the `PyQt5` library to display the icons.

1. Open OBS Studio.
2. Go to **Tools → Scripts**.
3. Click the **Python Settings** tab and make sure your Python Install Path is set. If it's empty, you may need to install Python from [this repo for example](https://github.com/zooba/obs-python) and point OBS to it.
4. Open **Command Prompt (CMD)** or **PowerShell as an Administrator**.
5. Navigate to your OBS Python folder
6. Install PyQt5 using pip:
    ```bash
    {path to python.exe} -m pip install PyQt5
    ```

### Step 3: Add the Script to OBS

1.  Go back to the **Tools → Scripts** window in OBS.
2.  In the **Scripts** tab, click the `+` (Add Script) icon in the bottom left.
3.  Select the `OBSIndicator.py` file you downloaded earlier.

That's it! The script is now installed and ready to go.

## 🚀 Usage

Once installed, the script works automatically:

-   An **icon appears** when you start recording or save a replay buffer.
-   The **icon disappears** when you stop recording.

## 🎨 Customization

You can customize the indicator's appearance directly within OBS.

1.  Go to **Tools → Scripts**.
2.  Select `OBS Indicator` from the list of loaded scripts.
3.  A panel with customization options will appear on the right:
    -   **Screen Position**: Choose which corner of the screen to display the icon in.
    -   **Padding**: Fine-tune the icon's exact position with pixel offsets.
    -   **Opacity**: Make the icon more or less transparent.

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
