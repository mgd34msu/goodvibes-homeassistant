const ICON_URL = "/goodvibes_static/gv-icon-sidebar.svg";

let cachedHomeIcon;

async function loadHomeIcon() {
  if (cachedHomeIcon) {
    return cachedHomeIcon;
  }
  const response = await fetch(ICON_URL);
  const svgText = await response.text();
  const svg = new DOMParser().parseFromString(svgText, "image/svg+xml");
  const path = svg.querySelector("path");
  const root = svg.querySelector("svg");
  cachedHomeIcon = {
    path: path ? path.getAttribute("d") : "",
    viewBox: root ? root.getAttribute("viewBox") || "0 0 600 600" : "0 0 600 600",
  };
  return cachedHomeIcon;
}

window.customIconsets = window.customIconsets || {};
window.customIconsets.goodvibes = async (name) => {
  if (name !== "home") {
    return undefined;
  }
  return loadHomeIcon();
};
