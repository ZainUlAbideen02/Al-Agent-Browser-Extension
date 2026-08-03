// Chrome Extension SidePanel Service Worker
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("Error setting sidePanel behavior:", error));

chrome.runtime.onInstalled.addListener(() => {
  console.log("AI Browser Agent Extension Installed Successfully.");
});
