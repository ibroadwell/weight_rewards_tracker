# Weight Rewards Tracker

A simple PyQt6 desktop tracker for weekly Saturday weight entries, reward thresholds, and reward item selection backed by SQLite.

## Run locally

Activate the virtual environment and launch the app:

```powershell
cd c:\Users\sr115\Desktop\repos\weight_rewards_tracker
.\app_env\Scripts\python.exe .\main.py
```

## Packaging as a Windows executable

The repo includes `build_exe.bat`, which uses `PyInstaller` to create a distributable Windows folder.

### Steps

1. Open a terminal in the repo folder.
2. Run:

```powershell
.\app_env\Scripts\python.exe .\build_exe.bat
```

3. The output will appear in `dist\main\`.
4. The executable is `dist\main\main.exe`.

### Important notes

- The build uses `--onedir` mode, so the packaged app runs from a folder rather than a single single-file exe.
- `weight_rewards.db` is included alongside the executable when it exists at build time.
- The app is configured to use the database file next to the executable when packaged.
- This means data will persist between runs as long as the `dist\main\weight_rewards.db` file remains in the same folder as `main.exe`.

## Redistributing

To share with someone who does not have Python installed:

1. Zip the entire `dist\main\` folder.
2. Send the zip file.
3. The recipient can extract and run `main.exe` directly.

## Troubleshooting

- If the executable cannot find the database, make sure `weight_rewards.db` is in the same folder as `main.exe`.
- If the app is missing packages, rerun `build_exe.bat` in the repo's virtual environment to install `PyInstaller` and rebuild.
