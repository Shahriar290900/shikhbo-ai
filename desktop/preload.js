// Minimal preload — nothing extra exposed to renderer
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("shikhboDesktop", {
  platform: process.platform,
  version: process.env.npm_package_version || "1.0.0",
});
