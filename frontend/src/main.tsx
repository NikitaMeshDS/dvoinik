import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";
function render() {
  createRoot(document.getElementById("root")!).render(<App />);
}
if (import.meta.env.VITE_SHOWCASE) {
  void import("./showcase/backend").then(({ install }) =>
    install().then(render),
  );
} else {
  render();
}
