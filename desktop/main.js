const { app, BrowserWindow, shell, Menu, nativeTheme } = require("electron");
const path = require("path");

nativeTheme.themeSource = "dark";

// URL of the deployed web app — override with SHIKHBO_URL env var for local dev
const SHIKHBO_URL = process.env.SHIKHBO_URL || "https://shikhbo.up.railway.app";

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 860,
    minHeight: 600,
    title: "Shikhbo — AI Study Partner",
    backgroundColor: "#0e1012",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: path.join(__dirname, "assets", "icon.png"),
  });

  win.loadURL(SHIKHBO_URL);

  // Open external links in default browser, not in-app
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(SHIKHBO_URL)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  // Simple menu
  const menu = Menu.buildFromTemplate([
    {
      label: "File",
      submenu: [
        { label: "New Chat", accelerator: "CmdOrCtrl+N", click: () => win.webContents.executeJavaScript("newChat && newChat()") },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    { label: "Edit", submenu: [{ role: "undo" }, { role: "redo" }, { type: "separator" }, { role: "cut" }, { role: "copy" }, { role: "paste" }] },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "window", submenu: [{ role: "minimize" }, { role: "zoom" }] },
  ]);
  Menu.setApplicationMenu(menu);
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
